import { describe, expect, it } from 'vitest'

import { resolveTerminalShell, type ShellResolutionInput } from './terminal-ipc'

const windowsDefault = () => ({ args: ['-NoLogo'], command: 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe', name: 'powershell.exe' })

function baseInput(overrides: Partial<ShellResolutionInput> = {}): ShellResolutionInput {
  return {
    findOnPath: () => null,
    isExecutableFile: file => file === '/bin/zsh',
    isWindows: false,
    windowsDefault,
    ...overrides
  }
}

describe('resolveTerminalShell', () => {
  it('prefers SHIINA_DESKTOP_SHELL when it resolves', () => {
    const spec = resolveTerminalShell(
      baseInput({
        SHIINA_DESKTOP_SHELL: '/opt/fish',
        isExecutableFile: file => file === '/opt/fish' || file === '/bin/zsh'
      })
    )

    expect(spec.command).toBe('/opt/fish')
    expect(spec.source).toBe('override')
    expect(spec.requested).toBeUndefined()
  })

  it('resolves a bare override name via PATH', () => {
    const spec = resolveTerminalShell(
      baseInput({
        SHIINA_DESKTOP_SHELL: 'fish',
        findOnPath: command => (command === 'fish' ? '/usr/bin/fish' : null),
        isExecutableFile: () => false
      })
    )

    expect(spec.command).toBe('/usr/bin/fish')
    expect(spec.source).toBe('override')
  })

  it('honors $SHELL on POSIX when no override is set', () => {
    const spec = resolveTerminalShell(
      baseInput({
        SHELL: '/bin/bash',
        isExecutableFile: file => file === '/bin/bash'
      })
    )

    expect(spec.command).toBe('/bin/bash')
    expect(spec.args).toEqual(['-il'])
    expect(spec.source).toBe('login-shell')
  })

  it('marks an unresolvable override as a fallback and names the request', () => {
    const spec = resolveTerminalShell(baseInput({ SHIINA_DESKTOP_SHELL: '/opt/nushell' }))

    expect(spec.command).toBe('/bin/zsh')
    expect(spec.source).toBe('fallback')
    expect(spec.requested).toBe('/opt/nushell')
  })

  it('auto-detects the best installed POSIX shell', () => {
    const spec = resolveTerminalShell(baseInput())

    expect(spec.command).toBe('/bin/zsh')
    expect(spec.source).toBe('auto')
    expect(spec.requested).toBeUndefined()
  })

  it('falls back to bare sh when no candidate exists', () => {
    const spec = resolveTerminalShell(baseInput({ isExecutableFile: () => false }))

    expect(spec.command).toBe('/bin/sh')
    expect(spec.source).toBe('auto')
  })

  it('ignores $SHELL on Windows and uses the platform default', () => {
    const spec = resolveTerminalShell(
      baseInput({ SHELL: '/bin/bash', isWindows: true, isExecutableFile: () => false })
    )

    expect(spec.command).toContain('powershell.exe')
    expect(spec.args).toEqual(['-NoLogo'])
    expect(spec.source).toBe('auto')
  })

  it('reports a bad Windows override as a fallback', () => {
    const spec = resolveTerminalShell(
      baseInput({
        SHIINA_DESKTOP_SHELL: 'nonexistent-shell',
        isWindows: true,
        isExecutableFile: () => false
      })
    )

    expect(spec.source).toBe('fallback')
    expect(spec.requested).toBe('nonexistent-shell')
    expect(spec.command).toContain('powershell.exe')
  })

  it('picks PowerShell flags for pwsh and none for cmd', () => {
    const pwsh = resolveTerminalShell(
      baseInput({
        SHIINA_DESKTOP_SHELL: 'pwsh',
        findOnPath: command => (command === 'pwsh' ? '/usr/bin/pwsh' : null),
        isExecutableFile: () => false
      })
    )

    expect(pwsh.args).toEqual(['-NoLogo'])

    const cmd = resolveTerminalShell(
      baseInput({
        SHIINA_DESKTOP_SHELL: 'C:/Windows/System32/cmd.exe',
        isExecutableFile: () => true,
        isWindows: true
      })
    )

    expect(cmd.args).toEqual([])
  })
})
