// The embedded terminal's PTY host: shell resolution, env scrubbing, session
// registry, and the shiina:terminal:* IPC surface. Extracted from main.ts; the
// factory owns the session map and returns the dispose helpers main.ts needs
// for SSH teardown. findOnPath / logging / connection routing stay injected.
import { execFile } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

import { app, ipcMain } from 'electron'
import nodePty from 'node-pty'

import { resolveTerminalConnectionForSender } from './connection-apply'
import { ensureSpawnHelperExecutable } from './spawn-helper-perms'
import { buildInteractiveSshArgs } from './ssh-connection'
import { createTerminalOutputGate } from './terminal-output-gate'
import { buildWindowsInteractiveCommand } from './windows-remote-lifecycle'

export interface TerminalIpcDeps {
  isWindows: boolean
  findOnPath: (command: string) => null | string
  rememberLog: (line: string) => void
  activeSshTerminalTarget: (webContentsId: number) => unknown
  ensureBackend: (webContentsId: number) => Promise<unknown>
  getSshConnectionState: (scope: string) => undefined | { remotePlatform?: string }
}

export interface TerminalShellSpec {
  args: string[]
  command: string
  name: string
  /** How the shell was picked — surfaced to the renderer so the tab can say
   *  *why* this shell is running, not just which one. */
  source: TerminalShellSource
  /** The raw SHIINA_DESKTOP_SHELL/$SHELL value that failed to resolve, when
   *  `source` is 'fallback'. Lets the renderer print an actionable notice
   *  instead of silently running a shell the user didn't ask for. */
  requested?: string
}

/** How the embedded terminal's shell was chosen. */
export type TerminalShellSource = 'auto' | 'fallback' | 'login-shell' | 'override'

export interface ShellResolutionInput {
  SHIINA_DESKTOP_SHELL?: string
  SHELL?: string
  isWindows: boolean
  findOnPath: (command: string) => null | string
  isExecutableFile: (filePath: string) => boolean
  /** Platform-default detection (Windows PowerShell chain); injected so the
   *  pure resolver stays testable without touching the registry/disk. */
  windowsDefault: () => { args: string[]; command: string; name: string }
  posixCandidates?: string[]
}

// Bare `sh` when nothing better is installed — always present on POSIX.
const POSIX_FALLBACK_SHELL = '/bin/sh'

const DEFAULT_POSIX_CANDIDATES = ['/bin/zsh', '/bin/bash', '/bin/sh']

function posixShellSpec(shellPath: string): { args: string[]; command: string; name: string } {
  const shellName = path.basename(shellPath)
  const interactiveArgs = shellName.includes('zsh') || shellName.includes('bash') ? ['-il'] : ['-i']

  return { args: interactiveArgs, command: shellPath, name: shellName }
}

/** Pure shell resolution: override → login shell → platform default →
 *  bare fallback. Exported for unit tests; `terminalShellCommand` below
 *  delegates with the live environment. */
export function resolveTerminalShell({
  SHIINA_DESKTOP_SHELL = '',
  SHELL = '',
  isWindows,
  findOnPath,
  isExecutableFile,
  windowsDefault,
  posixCandidates = DEFAULT_POSIX_CANDIDATES
}: ShellResolutionInput): TerminalShellSpec {
  // SHIINA_DESKTOP_SHELL is the cross-platform escape hatch (a path or a bare
  // name on PATH); $SHELL is honored on POSIX, where it's the user's canonical
  // choice, but ignored on Windows, where it's usually a stray MSYS/Git path
  // node-pty can't spawn natively.
  const explicitOverride = SHIINA_DESKTOP_SHELL.trim()
  const loginShell = isWindows ? '' : SHELL.trim()

  for (const [requested, source] of [
    [explicitOverride, 'override'],
    [loginShell, 'login-shell']
  ] as const) {
    if (!requested) {
      continue
    }

    const resolved = isExecutableFile(requested) ? requested : findOnPath(requested)

    if (resolved) {
      return { ...shellSpecForPath(resolved), source }
    }

    // Requested but unresolvable: remember it, keep falling through, and mark
    // the eventual pick as a fallback so the renderer can say so.
    const fallback = isWindows
      ? { ...windowsDefault(), source: 'fallback' as const, requested }
      : { ...posixShellSpec(resolvePosixDefault(posixCandidates, isExecutableFile)), source: 'fallback' as const, requested }

    return fallback
  }

  if (isWindows) {
    return { ...windowsDefault(), source: 'auto' }
  }

  return { ...posixShellSpec(resolvePosixDefault(posixCandidates, isExecutableFile)), source: 'auto' }
}

function resolvePosixDefault(candidates: string[], isExecutableFile: (filePath: string) => boolean): string {
  return candidates.find(candidate => isExecutableFile(candidate)) || POSIX_FALLBACK_SHELL
}

// Map a resolved shell path to its spawn spec, picking interactive flags by
// family: PowerShell drops its logo banner (so the prompt sits flush like the
// POSIX shells), cmd needs nothing, and everything else (zsh/bash/fish/sh…)
// gets POSIX interactive-login flags.
function shellSpecForPath(shellPath: string): { args: string[]; command: string; name: string } {
  const name = path.basename(shellPath).toLowerCase()

  if (name.startsWith('pwsh') || name.startsWith('powershell')) {
    return { args: ['-NoLogo'], command: shellPath, name }
  }

  if (name.startsWith('cmd')) {
    return { args: [], command: shellPath, name }
  }

  return posixShellSpec(shellPath)
}

export interface TerminalIpcApi {
  disposeTerminalSession: (id: string) => boolean
  disposeTerminalSessionsForSshScope: (scope: string) => void
  disposeAllTerminalSessions: () => void
}

// macOS accepts the bare charset name "UTF-8" as a locale; glibc does not, so
// every Linux pane would print `bash: warning: setlocale: LC_CTYPE: cannot
// change locale (UTF-8)`. Reuse the user's LANG there, else the glibc-guaranteed
// C.UTF-8. Pure: the platform arrives as data so tests need not fake the host.
export function terminalLcCtype(
  env: { LANG?: string; LC_CTYPE?: string },
  platform: NodeJS.Platform = process.platform
): string {
  if (env.LC_CTYPE) {
    return env.LC_CTYPE
  }

  return platform === 'darwin' ? 'UTF-8' : env.LANG || 'C.UTF-8'
}

export function registerTerminalIpc({
  isWindows,
  findOnPath,
  rememberLog,
  activeSshTerminalTarget,
  ensureBackend,
  getSshConnectionState
}: TerminalIpcDeps): TerminalIpcApi {
  const terminalSessions = new Map()

  function isExecutableFile(filePath) {
    if (!filePath || !path.isAbsolute(filePath)) {
      return false
    }

    try {
      fs.accessSync(filePath, fs.constants.X_OK)

      return true
    } catch {
      return false
    }
  }

  // Windows PowerShell 5.1 ships at a fixed System32 path on every Windows box;
  // prefer it only after PowerShell 7+ (`pwsh`).
  function windowsPowerShellPath() {
    const systemRoot = process.env.SystemRoot || process.env.windir || 'C:\\Windows'
    const builtin = path.join(systemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')

    return isExecutableFile(builtin) ? builtin : findOnPath('powershell.exe')
  }

  // Best installed Windows shell: PowerShell 7+ (`pwsh`), then Windows PowerShell
  // 5.1, then comspec/cmd.exe as the universal fallback.
  function windowsShellSpec() {
    const command =
      findOnPath('pwsh.exe') || findOnPath('pwsh') || windowsPowerShellPath() || process.env.COMSPEC || 'cmd.exe'

    return shellSpecForPath(command)
  }

  // Resolve the interactive shell for the embedded terminal, tracking *how* it
  // was picked so the renderer can explain a fallback instead of silently
  // running a shell the user didn't ask for.
  function terminalShellCommand(): TerminalShellSpec {
    return resolveTerminalShell({
      SHELL: process.env.SHELL,
      SHIINA_DESKTOP_SHELL: process.env.SHIINA_DESKTOP_SHELL,
      findOnPath,
      isExecutableFile,
      isWindows,
      windowsDefault: windowsShellSpec
    })
  }

  function safeTerminalCwd(cwd) {
    const candidate = path.resolve(String(cwd || app.getPath('home')))

    try {
      const stat = fs.statSync(candidate)

      return stat.isDirectory() ? candidate : path.dirname(candidate)
    } catch {
      return app.getPath('home')
    }
  }

  function terminalShellEnv() {
    const env = { ...process.env }

    // Electron is commonly launched through `npm run dev`; do not leak npm's
    // managed prefix into a user's interactive shell (nvm/proto warn loudly).
    for (const key of Object.keys(env)) {
      if (key === 'npm_config_prefix' || key.startsWith('npm_config_') || key.startsWith('npm_package_')) {
        delete env[key]
      }
    }

    // Strip color/theme-detection vars that ride along when Electron is launched
    // from a non-tty agent shell (Cursor's runner sets NO_COLOR/FORCE_COLOR=0
    // /TERM=dumb; some terminals set COLORFGBG which would flip Shiina' TUI into
    // light-mode). Our PTY is a real xterm-compat terminal — force truecolor.
    delete env.NO_COLOR
    delete env.FORCE_COLOR
    delete env.COLORFGBG

    env.COLORTERM = 'truecolor'
    env.LC_CTYPE = terminalLcCtype(env)
    env.TERM = 'xterm-256color'
    env.TERM_PROGRAM = 'Shiina'
    env.TERM_PROGRAM_VERSION = app.getVersion()

    // Let a shiina/--tui launched in this pane know it's embedded in the desktop
    // GUI (build_environment_hints surfaces this). Distinct from SHIINA_DESKTOP,
    // which marks the agent *backend* and gates cron/gateway behavior.
    env.SHIINA_DESKTOP_TERMINAL = '1'

    return env
  }

  function terminalChannel(id, suffix) {
    return `shiina:terminal:${id}:${suffix}`
  }

  // Best-effort read of a live PTY child's current working directory so a
  // reopened tab can restart the shell where the user last `cd`'d, instead of the
  // tab's original launch dir. Shell-agnostic (no prompt/OSC config needed) on
  // POSIX; Windows has no cheap per-process cwd query without a native module, so
  // it returns null and the caller falls back to the launch cwd.
  function readProcessCwd(pid) {
    return new Promise(resolve => {
      if (!Number.isInteger(pid) || pid <= 0) {
        resolve(null)

        return
      }

      if (process.platform === 'linux') {
        fs.promises
          .readlink(`/proc/${pid}/cwd`)
          .then(target => resolve(target || null))
          .catch(() => resolve(null))

        return
      }

      if (process.platform === 'darwin') {
        // lsof ships with macOS; -Fn emits the cwd fd's path on an `n<path>` line.
        execFile('lsof', ['-a', '-p', String(pid), '-d', 'cwd', '-Fn'], { timeout: 2000 }, (err, stdout) => {
          if (err) {
            resolve(null)

            return
          }

          const line = String(stdout || '')
            .split('\n')
            .find(entry => entry.startsWith('n'))

          resolve(line ? line.slice(1) : null)
        })

        return
      }

      resolve(null)
    })
  }

  function disposeTerminalSession(id: string) {
    const sessionInfo = terminalSessions.get(id)

    if (!sessionInfo) {
      return false
    }

    terminalSessions.delete(id)

    try {
      sessionInfo.pty.kill()
    } catch {
      // Process may already be gone.
    }

    return true
  }

  // SSH teardown: close every pane whose PTY rode the disconnected tunnel.
  function disposeTerminalSessionsForSshScope(scope: string) {
    for (const [id, info] of [...terminalSessions.entries()]) {
      if (info.sshScope === scope) {
        disposeTerminalSession(id)
      }
    }
  }

  // App shutdown: kill every open PTY before environment teardown.
  function disposeAllTerminalSessions() {
    for (const id of [...terminalSessions.keys()]) {
      disposeTerminalSession(id)
    }
  }

  // node-pty's published tarball ships the POSIX `spawn-helper` without an exec
  // bit; the dev flow resolves node-pty straight from node_modules (nothing
  // chmods it there), so the first terminal spawn dies with `posix_spawnp
  // failed`. Restore the bit once, lazily, right before the first spawn. Packaged
  // builds already stage an executable copy, so this is a no-op there.
  let _spawnHelperEnsured = false

  function ensureNodePtySpawnHelper() {
    if (_spawnHelperEnsured || isWindows) {
      return
    }

    _spawnHelperEnsured = true

    try {
      const nodePtyRoot = path.dirname(require.resolve('node-pty/package.json'))
      const { fixed, errors } = ensureSpawnHelperExecutable(nodePtyRoot)

      for (const helperPath of fixed) {
        rememberLog(`[terminal] restored +x on node-pty spawn-helper: ${helperPath}`)
      }

      for (const failure of errors) {
        rememberLog(`[terminal] could not chmod spawn-helper ${failure.path}: ${failure.error}`)
      }
    } catch (error) {
      rememberLog(
        `[terminal] spawn-helper exec check skipped: ${error instanceof Error ? error.message : String(error)}`
      )
    }
  }

  ipcMain.handle('shiina:terminal:start', async (event, payload = {}) => {
    ensureNodePtySpawnHelper()

    const id = crypto.randomUUID()
    const { args, command, name, requested, source } = terminalShellCommand()
    const cwd = safeTerminalCwd(payload?.cwd)
    const cols = Math.max(2, Number.parseInt(String(payload?.cols || 80), 10) || 80)
    const rows = Math.max(2, Number.parseInt(String(payload?.rows || 24), 10) || 24)

    const sshTarget = await resolveTerminalConnectionForSender(event.sender.id, activeSshTerminalTarget, ensureBackend)

    const remote = Boolean(sshTarget)
    const remoteState = remote ? getSshConnectionState(sshTarget.scope) : null

    const remoteCommand =
      remoteState?.remotePlatform === 'Windows'
        ? buildWindowsInteractiveCommand(String(payload?.cwd || '').trim())
        : undefined

    const ptyProcess = remote
      ? nodePty.spawn(
          process.platform === 'win32'
            ? path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'OpenSSH', 'ssh.exe')
            : 'ssh',
          buildInteractiveSshArgs(sshTarget.ssh, String(payload?.cwd || '').trim(), undefined, remoteCommand),
          { cols, cwd: app.getPath('home'), env: terminalShellEnv(), name: 'xterm-256color', rows }
        )
      : nodePty.spawn(command, args, { cols, cwd, env: terminalShellEnv(), name: 'xterm-256color', rows })

    const send = (suffix, payload) => {
      if (event.sender.isDestroyed()) {
        return
      }

      event.sender.send(terminalChannel(id, suffix), payload)
    }

    const outputGate = createTerminalOutputGate({
      onExitFlushed: () => terminalSessions.delete(id),
      sendData: data => send('data', data),
      sendExit: payload => send('exit', payload)
    })

    terminalSessions.set(id, {
      outputGate,
      pty: ptyProcess,
      webContentsId: event.sender.id,
      ...(remote ? { sshScope: sshTarget.scope, remoteCwd: String(payload?.cwd || '') } : {})
    })

    ptyProcess.onData(data => outputGate.data(data))
    ptyProcess.onExit(({ exitCode, signal }) => {
      outputGate.exit({ code: exitCode, signal: signal == null ? null : String(signal) })
    })
    event.sender.once('destroyed', () => disposeTerminalSession(id))

    return {
      cwd: remote ? null : cwd,
      id,
      shell: remote ? 'ssh' : name,
      shellSource: remote ? 'auto' : source,
      ...(requested && !remote ? { shellRequested: requested } : {})
    }
  })

  ipcMain.handle('shiina:terminal:attach', (event, id) => {
    const sessionInfo = terminalSessions.get(String(id || ''))

    if (!sessionInfo || sessionInfo.webContentsId !== event.sender.id) {
      return false
    }

    sessionInfo.outputGate.attach()

    return true
  })

  ipcMain.handle('shiina:terminal:write', (_event, id, data) => {
    const sessionInfo = terminalSessions.get(String(id || ''))

    if (!sessionInfo) {
      return false
    }

    sessionInfo.pty.write(String(data || ''))

    return true
  })

  ipcMain.handle('shiina:terminal:resize', (_event, id, size = {}) => {
    const sessionInfo = terminalSessions.get(String(id || ''))

    if (!sessionInfo) {
      return false
    }

    const cols = Math.max(2, Number.parseInt(String(size?.cols || 80), 10) || 80)
    const rows = Math.max(2, Number.parseInt(String(size?.rows || 24), 10) || 24)

    sessionInfo.pty.resize(cols, rows)

    return true
  })
  ipcMain.handle('shiina:terminal:cwd', async (_event, id) => {
    const sessionInfo = terminalSessions.get(String(id || ''))

    if (!sessionInfo) {
      return null
    }

    return sessionInfo.sshScope !== undefined ? null : readProcessCwd(sessionInfo.pty.pid)
  })

  ipcMain.handle('shiina:terminal:dispose', (_event, id) => disposeTerminalSession(String(id || '')))

  return { disposeTerminalSession, disposeTerminalSessionsForSshScope, disposeAllTerminalSessions }
}
