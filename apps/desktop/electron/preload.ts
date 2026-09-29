import { contextBridge, ipcRenderer, webFrame, webUtils } from 'electron'

import type { DesktopProfileRoute } from './desktop-profile'
import { customWindowControlsEnabled } from './window-controls'

// Which translucency the OS can back. Asked synchronously because the renderer
// needs it before its first paint, and answered by main because deciding it
// needs `os.release()` — a sandboxed preload may only require electron, events,
// timers and url, so importing node:os here throws before contextBridge runs
// and takes the ENTIRE bridge down with it (window.shiinaDesktop undefined =>
// "Desktop IPC bridge is unavailable"). No reply means no glass, which degrades
// to an ordinary opaque window rather than a page thinned over nothing.
const translucencySupport = ipcRenderer.sendSync('shiina:translucency:support')
const hudWindowing = ipcRenderer.sendSync('shiina:hud:windowing')
const hudNativeDrag = hudWindowing?.nativeDrag === true
const launchFlags = ipcRenderer.sendSync('shiina:launch-flags')

contextBridge.exposeInMainWorld('shiinaDesktop', {
  glassSupported: translucencySupport?.glass === true,
  translucencySupported: translucencySupport?.translucency === true,
  // Launch-flag fact: the app was started with --local, so the renderer may
  // show the local-models surfaces. Static for the window's lifetime.
  localModelsEnabled: launchFlags?.localModels === true,
  // Launch-flag fact: the Nous free tier is on for this launch
  // (SHIINA_GUEST_ONBOARDING=1 or --guest-onboarding). Read-only; the same
  // decision is stamped onto every backend the app spawns.
  guestOnboardingEnabled: launchFlags?.guestOnboarding === true,
  // Launch-flag fact: skip the first-run film (SHIINA_SKIP_INTRO=1 or
  // --skip-intro). Rehearsal aid for the guided chat behind it.
  skipIntro: launchFlags?.skipIntro === true,
  getConnection: (profile, opts) => ipcRenderer.invoke('shiina:connection', profile, opts),
  // Registry-scoped backend resolution: { connectionId, profile } → descriptor.
  getConnectionFor: payload => ipcRenderer.invoke('shiina:connection:for', payload),
  getProfileRoutes: profiles => ipcRenderer.invoke('shiina:plugin-profile-routes', profiles),
  revalidateConnection: () => ipcRenderer.invoke('shiina:connection:revalidate'),
  touchBackend: (profile, options) => ipcRenderer.invoke('shiina:backend:touch', profile, options),
  getPoolLimits: () => ipcRenderer.invoke('shiina:pool-limits:get'),
  setPoolLimits: limits => ipcRenderer.invoke('shiina:pool-limits:set', limits),
  getGatewayWsUrl: profile => ipcRenderer.invoke('shiina:gateway:ws-url', profile),
  // Registry-scoped fresh WS URL: { connectionId, profile } → result shape of
  // getGatewayWsUrl, minted against that connection's backend.
  getGatewayWsUrlFor: payload => ipcRenderer.invoke('shiina:gateway:ws-url-for', payload),
  // Union agent roster across every registered connection.
  getAgentRoster: () => ipcRenderer.invoke('shiina:agents:roster'),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('shiina:window:openSession', sessionId, opts),
  openSessionInTerminal: (sessionId, opts) => ipcRenderer.invoke('shiina:window:openInTerminal', sessionId, opts),
  openWindow: (options?: DesktopProfileRoute) => ipcRenderer.invoke('shiina:window:openInstance', options),
  openBrowserWindow: tabId => ipcRenderer.invoke('shiina:window:openBrowser', tabId),
  onBrowserPopoutClosed: callback => {
    const listener = (_event, tabId) => callback(tabId)
    ipcRenderer.on('shiina:browser-popout:closed', listener)

    return () => ipcRenderer.removeListener('shiina:browser-popout:closed', listener)
  },
  claimAmbientCue: key => ipcRenderer.invoke('shiina:ambient:claim', key),
  windowControls: {
    custom: customWindowControlsEnabled(),
    minimize: () => ipcRenderer.send('shiina:window-control', 'minimize'),
    toggleMaximize: () => ipcRenderer.send('shiina:window-control', 'toggle-maximize'),
    close: () => ipcRenderer.send('shiina:window-control', 'close')
  },
  wakeIndicator: {
    getState: () => ipcRenderer.invoke('shiina:wake-indicator:get'),
    setState: state => ipcRenderer.send('shiina:wake-indicator:set', state),
    onState: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('shiina:wake-indicator:state', listener)

      return () => ipcRenderer.removeListener('shiina:wake-indicator:state', listener)
    }
  },
  chatOnboarding: {
    grow: request => ipcRenderer.send('shiina:chat-onboarding:grow', request),
    soloBoot: () => ipcRenderer.send('shiina:chat-onboarding:solo-boot')
  },
  introReveal: {
    open: (payload?: { hideMain?: boolean }) => ipcRenderer.invoke('shiina:intro-reveal:open', payload),
    close: (payload?: { showMain?: boolean }) => ipcRenderer.invoke('shiina:intro-reveal:close', payload),
    skip: () => ipcRenderer.send('shiina:intro-reveal:skip'),
    ready: () => ipcRenderer.send('shiina:intro-reveal:ready'),
    onSkip: callback => {
      const listener = () => callback()

      ipcRenderer.on('shiina:intro-reveal:skip', listener)

      return () => ipcRenderer.removeListener('shiina:intro-reveal:skip', listener)
    },
    onClosed: callback => {
      const listener = () => callback()

      ipcRenderer.on('shiina:intro-reveal:closed', listener)

      return () => ipcRenderer.removeListener('shiina:intro-reveal:closed', listener)
    }
  },
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('shiina:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('shiina:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('shiina:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('shiina:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('shiina:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('shiina:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('shiina:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('shiina:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('shiina:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('shiina:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('shiina:pet-overlay:control', listener)
    }
  },
  // HUD mode: the chrome-free floating chat. A full app renderer (own gateway)
  // sized as a floating bar, so it mounts the real composer. Main owns the
  // window; `onChanged` keeps every window's toggle truthful.
  hud: {
    nativeDrag: hudNativeDrag,
    windowing: {
      clientPlacement: hudWindowing?.clientPlacement !== false,
      controlDrag: hudWindowing?.controlDrag === true,
      nativeDrag: hudNativeDrag,
      solid: hudWindowing?.solid === true,
      workspaceTransfer: hudWindowing?.workspaceTransfer === true
    },
    open: request => ipcRenderer.invoke('shiina:hud:open', request),
    close: () => ipcRenderer.invoke('shiina:hud:close'),
    setIgnoreMouse: ignore => ipcRenderer.send('shiina:hud:ignore-mouse', ignore),
    beginMove: () => ipcRenderer.send('shiina:hud:begin-move'),
    endMove: () => ipcRenderer.send('shiina:hud:end-move'),
    moveBy: delta => ipcRenderer.send('shiina:hud:move-by', delta),
    setWorkspaceTransfer: transferring => ipcRenderer.send('shiina:hud:workspace-transfer', transferring),
    setBounds: bounds => ipcRenderer.send('shiina:hud:set-bounds', bounds),
    resetLayout: () => ipcRenderer.invoke('shiina:hud:reset-layout'),
    // Whether the band covers the window below the bar. Main pairs it with the
    // user's translucency setting to decide the native frost (macOS vibrancy /
    // Windows 11 DWM backdrop) — see hudFrostFor.
    setFrost: showing => ipcRenderer.invoke('shiina:hud:frost', showing),
    // The HUD tells main which session it is on; main hands that back to the
    // app window when the HUD closes, so the app can re-home onto it.
    setSession: sessionId => ipcRenderer.send('shiina:hud:session', sessionId),
    onGoto: callback => {
      const listener = (_event, sessionId) => callback(sessionId)
      ipcRenderer.on('shiina:hud:goto', listener)

      return () => ipcRenderer.removeListener('shiina:hud:goto', listener)
    },
    onChanged: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('shiina:hud:changed', listener)

      return () => ipcRenderer.removeListener('shiina:hud:changed', listener)
    },
    // Linux only, and silent elsewhere: where the cursor is, in page
    // coordinates, or null when it has left the window. Stands in for the
    // mousemove that `setIgnoreMouseEvents(true, { forward: true })` delivers on
    // macOS and Windows but not here.
    onCursor: callback => {
      const listener = (_event, point) => callback(point)
      ipcRenderer.on('shiina:hud:cursor', listener)

      return () => ipcRenderer.removeListener('shiina:hud:cursor', listener)
    },
    // Main's game-overlay watch: whether a fullscreen app (a game) is under
    // the HUD, so the renderer can step back to the low-opacity overlay
    // treatment while one owns the screen.
    onGameOverlay: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('shiina:hud:game-overlay', listener)

      return () => ipcRenderer.removeListener('shiina:hud:game-overlay', listener)
    }
  },
  // macOS native screenshot gesture; captures require a main-issued request.
  screenshot: process.platform === 'darwin' ? {
    getSettings: () => ipcRenderer.invoke('shiina:screenshot:settings:get'),
    setEnabled: enabled => ipcRenderer.invoke('shiina:screenshot:settings:set', enabled),
    openPermissionSettings: kind => ipcRenderer.invoke('shiina:screenshot:permission', kind),
    capture: requestId => ipcRenderer.invoke('shiina:screenshot:capture', requestId),
    onStatus: callback => {
      const listener = (_event, status) => callback(status)
      ipcRenderer.on('shiina:screenshot:status', listener)

      return () => ipcRenderer.removeListener('shiina:screenshot:status', listener)
    },
    onRequest: callback => {
      const channel = 'shiina:screenshot:request'
      const listener = (_event, requestId) => callback(requestId)
      if (ipcRenderer.listenerCount(channel) === 0) {
        ipcRenderer.send('shiina:screenshot:subscribe', true)
      }
      ipcRenderer.on(channel, listener)

      return () => {
        ipcRenderer.removeListener(channel, listener)
        if (ipcRenderer.listenerCount(channel) === 0) {
          ipcRenderer.send('shiina:screenshot:subscribe', false)
        }
      }
    }
  } : undefined,
  // Quick Entry: the global-hotkey mini composer window. Main owns the OS
  // shortcut + the persisted preference; the quick window only captures text
  // and hands it back, and the primary renderer submits it through the normal
  // prompt path.
  quickEntry: {
    getSettings: () => ipcRenderer.invoke('shiina:quick-entry:settings:get'),
    setSettings: patch => ipcRenderer.invoke('shiina:quick-entry:settings:set', patch),
    submit: payload => ipcRenderer.send('shiina:quick-entry:submit', payload),
    dismiss: () => ipcRenderer.send('shiina:quick-entry:dismiss'),
    // Primary renderer → main → quick window: gateway connection state + the
    // recent-session options the target picker offers. Main caches the latest
    // payload so a freshly spawned quick window starts from truth.
    pushState: payload => ipcRenderer.send('shiina:quick-entry:state', payload),
    // Quick window subscribes to those pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('shiina:quick-entry:state', listener)

      return () => ipcRenderer.removeListener('shiina:quick-entry:state', listener)
    },
    // Main → primary renderer: a submit captured by the quick window.
    onSubmit: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('shiina:quick-entry:submit', listener)

      return () => ipcRenderer.removeListener('shiina:quick-entry:submit', listener)
    },
    // Main → quick window: you were just summoned (reset draft + refocus).
    onShown: callback => {
      const listener = () => callback()
      ipcRenderer.on('shiina:quick-entry:shown', listener)

      return () => ipcRenderer.removeListener('shiina:quick-entry:shown', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('shiina:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('shiina:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('shiina:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('shiina:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('shiina:connection-config:test', payload),
  // Opt-in OS-keychain encryption for stored gateway secrets (default off —
  // see secret-storage-policy.ts). get never touches the OS keychain.
  getSecretStorageEncryption: () => ipcRenderer.invoke('shiina:secret-storage:get'),
  setSecretStorageEncryption: (on: boolean) => ipcRenderer.invoke('shiina:secret-storage:set', on),
  // v2 multi-connection registry: named agent sources (local / remote / cloud / ssh).
  connections: {
    list: () => ipcRenderer.invoke('shiina:connections:list'),
    save: payload => ipcRenderer.invoke('shiina:connections:save', payload),
    remove: id => ipcRenderer.invoke('shiina:connections:remove', id),
    setPrimary: id => ipcRenderer.invoke('shiina:connections:set-primary', id),
    setLaunchMode: mode => ipcRenderer.invoke('shiina:connections:set-launch-mode', mode),
    setLastUsed: id => ipcRenderer.invoke('shiina:connections:set-last-used', id),
    test: id => ipcRenderer.invoke('shiina:connections:test', id),
    updateManaged: id => ipcRenderer.invoke('shiina:connections:update-managed', id),
    // Fan out `shiina update` to every eligible registered connection.
    // Optional excludeIds skips rows the caller updates through another path.
    updateAll: options => ipcRenderer.invoke('shiina:connections:update-all', options),
    // Registry lifecycle push (main → renderer): a connection was removed or
    // materially edited, so secondaries scoped to it must be disposed (and,
    // for edits, re-dialed at the new target).
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('shiina:connections:changed', listener)

      return () => ipcRenderer.removeListener('shiina:connections:changed', listener)
    }
  },
  sshConfigHosts: () => ipcRenderer.invoke('shiina:ssh-config:hosts'),
  sshResolveHost: host => ipcRenderer.invoke('shiina:ssh-config:resolve', host),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('shiina:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('shiina:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('shiina:connection-config:oauth-logout', remoteUrl),
  // Shiina Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('shiina:cloud:status'),
    login: () => ipcRenderer.invoke('shiina:cloud:login'),
    logout: () => ipcRenderer.invoke('shiina:cloud:logout'),
    discover: org => ipcRenderer.invoke('shiina:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('shiina:cloud:agent-sign-in', dashboardUrl)
  },
  profile: {
    getDefault: () => ipcRenderer.invoke('shiina:profile:default:get'),
    setDefault: (route: DesktopProfileRoute) => ipcRenderer.invoke('shiina:profile:default:set', route),
    onDefaultChanged: (callback: (route: DesktopProfileRoute | null) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, route: DesktopProfileRoute | null) => callback(route)
      ipcRenderer.on('shiina:profile:default:changed', listener)

      return () => ipcRenderer.removeListener('shiina:profile:default:changed', listener)
    },
    get: () => ipcRenderer.invoke('shiina:profile:get'),
    remember: name => ipcRenderer.invoke('shiina:profile:remember', name),
    set: name => ipcRenderer.invoke('shiina:profile:set', name)
  },
  api: request => ipcRenderer.invoke('shiina:api', request),
  notify: payload => ipcRenderer.invoke('shiina:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('shiina:requestMicrophoneAccess'),
  readWindowBelow: () => ipcRenderer.invoke('shiina:window:readBelow'),
  readFileDataUrl: filePath => ipcRenderer.invoke('shiina:readFileDataUrl', filePath),
  readFileDataUrlForAttach: filePath => ipcRenderer.invoke('shiina:readFileDataUrlForAttach', filePath),
  dataUrlReadMax: {
    get: () => ipcRenderer.invoke('shiina:data-url-read-max:get'),
    set: maxMb => ipcRenderer.invoke('shiina:data-url-read-max:set', maxMb)
  },
  readFileText: filePath => ipcRenderer.invoke('shiina:readFileText', filePath),
  readPluginSource: (filePath: string) => ipcRenderer.invoke('shiina:readPluginSource', filePath),
  selectPaths: options => ipcRenderer.invoke('shiina:selectPaths', options),
  selectSavePath: options => ipcRenderer.invoke('shiina:selectSavePath', options),
  writeClipboard: text => ipcRenderer.invoke('shiina:writeClipboard', text),
  readClipboard: () => ipcRenderer.invoke('shiina:readClipboard'),
  saveGatewayFile: payload => ipcRenderer.invoke('shiina:saveGatewayFile', payload),
  saveImageFromUrl: url => ipcRenderer.invoke('shiina:saveImageFromUrl', url),
  contextMenuEdit: command => ipcRenderer.invoke('shiina:context-menu:edit', command),
  contextMenuCopyImage: () => ipcRenderer.invoke('shiina:context-menu:copy-image'),
  contextMenuSpellcheck: action => ipcRenderer.invoke('shiina:context-menu:spellcheck', action),
  contextMenuGuestAddWord: payload => ipcRenderer.invoke('shiina:context-menu:guest-add-word', payload),
  onContextMenuSpellcheck: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:context-menu-spellcheck', listener)

    return () => ipcRenderer.removeListener('shiina:context-menu-spellcheck', listener)
  },
  saveImageBuffer: (data, ext, name) => ipcRenderer.invoke('shiina:saveImageBuffer', { data, ext, name }),
  capturePreview: payload => ipcRenderer.invoke('shiina:capturePreview', payload),
  savePastedText: text => ipcRenderer.invoke('shiina:savePastedText', { text }),
  saveClipboardImage: () => ipcRenderer.invoke('shiina:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('shiina:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('shiina:watchPreviewFile', url),
  watchDirectory: dir => ipcRenderer.invoke('shiina:watchDirectory', dir),
  stopPreviewFileWatch: id => ipcRenderer.invoke('shiina:stopPreviewFileWatch', id),
  setActiveWork: payload => ipcRenderer.send('shiina:active-work', payload),
  setTitleBarTheme: payload => ipcRenderer.send('shiina:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('shiina:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('shiina:translucency', payload),
  setKeepAwake: on => ipcRenderer.send('shiina:keep-awake', on),
  setDisableF12: blocked => ipcRenderer.send('shiina:devtools:disable-f12', blocked),
  setPreviewShortcutActive: active => ipcRenderer.send('shiina:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('shiina:openExternal', url),
  mcpOauth: {
    // One-shot loopback listener for MCP OAuth against remote backends: bind
    // on this machine, hand redirectUri to mcp.servers.oauth.start, then wait
    // for the provider redirect and relay code/state via oauth.callback.
    listen: () => ipcRenderer.invoke('shiina:mcp-oauth:listen'),
    wait: (id, timeoutMs) => ipcRenderer.invoke('shiina:mcp-oauth:wait', id, timeoutMs),
    cancel: id => ipcRenderer.invoke('shiina:mcp-oauth:cancel', id)
  },
  openPreviewInBrowser: url => ipcRenderer.invoke('shiina:openPreviewInBrowser', url),
  reachPreviewUrl: url => ipcRenderer.invoke('shiina:preview:reach', url),
  setActiveConnectionRoute: route => ipcRenderer.send('shiina:connection:active-route', route),
  fetchLinkTitle: url => ipcRenderer.invoke('shiina:fetchLinkTitle', url),
  resolveFavicon: url => ipcRenderer.invoke('shiina:resolveFavicon', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('shiina:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('shiina:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('shiina:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('shiina:setting:defaultProjectDir:pick')
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('shiina:zoom:get'),
    // Synchronous zoom factor (1 = 100%). Coordinate math needs it in the
    // same tick as the event it converts, so no IPC round-trip here.
    factor: () => webFrame.getZoomFactor(),
    setPercent: percent => ipcRenderer.send('shiina:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('shiina:zoom:changed', listener)

      return () => ipcRenderer.removeListener('shiina:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('shiina:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('shiina:logs:recent'),
  // Fire-and-forget: persists a renderer error-boundary catch (with component
  // stack) to desktop.log so crashes survive the window (#79428).
  reportRendererError: report => ipcRenderer.send('shiina:logs:renderer-error', report),
  readDir: dirPath => ipcRenderer.invoke('shiina:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('shiina:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('shiina:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('shiina:fs:openDir', dirPath),
  desktopPluginsRoot: () => ipcRenderer.invoke('shiina:fs:desktopPluginsRoot'),
  reconcileDesktopPlugins: () => ipcRenderer.invoke('shiina:fs:reconcileDesktopPlugins'),
  logsRoot: () => ipcRenderer.invoke('shiina:fs:logsRoot'),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('shiina:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('shiina:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('shiina:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('shiina:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('shiina:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('shiina:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('shiina:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('shiina:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('shiina:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('shiina:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('shiina:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('shiina:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('shiina:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('shiina:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('shiina:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('shiina:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('shiina:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('shiina:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('shiina:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('shiina:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('shiina:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('shiina:git:review:shipInfo', repoPath),
      prList: (repoPath, branches, numbers) =>
        ipcRenderer.invoke('shiina:git:review:prList', repoPath, branches, numbers),
      createPr: repoPath => ipcRenderer.invoke('shiina:git:review:createPr', repoPath)
    }
  },
  terminal: {
    attach: id => ipcRenderer.invoke('shiina:terminal:attach', id),
    cwd: id => ipcRenderer.invoke('shiina:terminal:cwd', id),
    dispose: id => ipcRenderer.invoke('shiina:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('shiina:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('shiina:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('shiina:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `shiina:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `shiina:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('shiina:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('shiina:close-preview-requested', listener)
  },
  onPreviewNav: callback => {
    const listener = (_event, command) => callback(command)
    ipcRenderer.on('shiina:preview-nav', listener)

    return () => ipcRenderer.removeListener('shiina:preview-nav', listener)
  },
  onOpenFolderRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('shiina:open-folder-requested', listener)

    return () => ipcRenderer.removeListener('shiina:open-folder-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('shiina:open-updates', listener)

    return () => ipcRenderer.removeListener('shiina:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:deep-link', listener)

    return () => ipcRenderer.removeListener('shiina:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('shiina:deep-link-ready'),
  probePluginRepo: payload => ipcRenderer.invoke('shiina:plugin:probe', payload),
  installDesktopPlugin: payload => ipcRenderer.invoke('shiina:plugin:installDesktop', payload),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:window-state-changed', listener)

    return () => ipcRenderer.removeListener('shiina:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('shiina:focus-session', listener)

    return () => ipcRenderer.removeListener('shiina:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:notification-action', listener)

    return () => ipcRenderer.removeListener('shiina:notification-action', listener)
  },
  onNotificationActivate: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:notification-activate', listener)

    return () => ipcRenderer.removeListener('shiina:notification-activate', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('shiina:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:backend-exit', listener)

    return () => ipcRenderer.removeListener('shiina:backend-exit', listener)
  },
  // Cooperative pool retirement (main → renderer): the pooled backend under
  // `poolKey` is being stopped for a foreground open. Park that scope; do not
  // redial into the slot it vacated.
  onPoolBackendRetiring: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:pool:retiring', listener)

    return () => ipcRenderer.removeListener('shiina:pool:retiring', listener)
  },
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('shiina:connection:applied', listener)

    return () => ipcRenderer.removeListener('shiina:connection:applied', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('shiina:power-resume', listener)

    return () => ipcRenderer.removeListener('shiina:power-resume', listener)
  },
  // AC ↔ battery transitions; renderers slow their backstop polls on battery.
  getOnBattery: () => ipcRenderer.invoke('shiina:power-battery:get'),
  onBatteryChanged: callback => {
    const listener = (_event, onBattery) => callback(Boolean(onBattery))
    ipcRenderer.on('shiina:power-battery', listener)

    return () => ipcRenderer.removeListener('shiina:power-battery', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:boot-progress', listener)

    return () => ipcRenderer.removeListener('shiina:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('shiina:bootstrap:get'),
  continueBootstrapLocal: () => ipcRenderer.invoke('shiina:bootstrap:continue-local'),
  recycleBackend: profile => ipcRenderer.invoke('shiina:backend:recycle', profile),
  resetBootstrap: () => ipcRenderer.invoke('shiina:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('shiina:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('shiina:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('shiina:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('shiina:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('shiina:version'),
  relaunchApp: () => ipcRenderer.invoke('shiina:app:relaunch'),
  getMachineProfile: () => ipcRenderer.invoke('shiina:machine:profile'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('shiina:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('shiina:uninstall:summary'),
    run: mode => ipcRenderer.invoke('shiina:uninstall:run', { mode })
  },
  updates: {
    check: opts => ipcRenderer.invoke('shiina:updates:check', opts),
    apply: opts => ipcRenderer.invoke('shiina:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('shiina:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('shiina:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('shiina:updates:progress', listener)

      return () => ipcRenderer.removeListener('shiina:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('shiina:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('shiina:vscode-theme:search', query)
  },
  // Find-in-page (Ctrl/Cmd+F): delegates to Electron's
  // webContents.findInPage on the IPC sender's window so a Cmd+F pressed
  // in a secondary session window searches THAT window, not the primary.
  // `onFoundInPage` returns the unsubscribe fn; the renderer wires it via
  // `initFindInPageListener` in store/find-in-page.ts and tears it down
  // when the FindBar unmounts.
  findInPage: (query, options) => ipcRenderer.invoke('shiina:find-in-page', query, options),
  stopFindInPage: () => ipcRenderer.invoke('shiina:stop-find-in-page'),
  onFoundInPage: callback => {
    const listener = (_event, result) => callback(result)
    ipcRenderer.on('shiina:found-in-page', listener)

    return () => ipcRenderer.removeListener('shiina:found-in-page', listener)
  },
  // Main-process `before-input-event` forwards Ctrl/Cmd+F here so renderer
  // can open the FindBar even when the GTK compositor has already grabbed
  // the chord at the windowing layer (#81727).
  onOpenFindBarRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('shiina:open-find-bar', listener)

    return () => ipcRenderer.removeListener('shiina:open-find-bar', listener)
  }
})
