import { atom, computed } from 'nanostores'

import { MOUSE_TRACKING } from '../config/env.js'
import { DEFAULT_LAYOUT } from '../domain/layout.js'
import { applyDesign } from '../domain/applyDesign.js'
import { ZERO } from '../domain/usage.js'
import { bootTheme } from '../lib/themeBoot.js'
import { DEFAULT_THEME } from '../theme.js'

import { DEFAULT_INDICATOR_STYLE, type UiState } from './interfaces.js'

// The skin-resolved theme before any design is worn on top.
const seed = bootTheme ?? DEFAULT_THEME

const buildUiState = (): UiState => ({
  battery: false,
  batteryStatus: null,
  bgTasks: new Set(),
  busy: false,
  busyInputMode: 'queue',
  compact: false,
  compacting: false,
  destructiveSlashConfirm: true,
  detailsMode: 'collapsed',
  detailsModeCommandOverride: false,
  focusView: false,
  indicatorStyle: DEFAULT_INDICATOR_STYLE,
  info: null,
  layout: DEFAULT_LAYOUT,
  liveSessionCount: 0,
  inlineDiffs: true,
  mouseTracking: MOUSE_TRACKING,
  notice: null,
  pasteCollapseLines: 5,
  pasteCollapseChars: 2000,
  sections: {},
  sessionTitle: '',
  showReasoning: false,
  sid: null,
  status: 'summoning shiina…',
  statusBar: 'top',
  storedSid: null,
  statusBarFields: null,
  streaming: true,
  timestamps: false,
  // Last session's resolved theme paints frame one (flash-free boot, like
  // the desktop's shiina-boot-* keys); DEFAULT_THEME only on first launch.
  // `theme` is the base with the active design worn on top; with no design
  // loaded the two are the same object.
  baseTheme: seed,
  design: null,
  designs: [],
  theme: seed,
  usage: ZERO
})

export const $uiState = atom<UiState>(buildUiState())

export const $uiTheme = computed($uiState, state => state.theme)
export const $uiSessionId = computed($uiState, state => state.sid)

export const getUiState = () => $uiState.get()

/**
 * Patch state, recomputing the effective theme when either input to it moves:
 * a new skin theme (`commitTheme`) or a newly loaded design (`display.design`
 * resolving, or a live switch). Single point on purpose — every path that
 * changes the design gets the applied theme for free, and the base is kept
 * separately so switching designs never layers one palette onto another's.
 */
export const patchUiState = (next: Partial<UiState> | ((state: UiState) => UiState)) => {
  const state = $uiState.get()
  const merged = typeof next === 'function' ? next(state) : { ...state, ...next }

  if (merged.theme !== state.theme || merged.design !== state.design) {
    const base = merged.theme !== state.theme ? merged.theme : state.baseTheme

    merged.baseTheme = base
    merged.theme = applyDesign(base, merged.design)
  }

  $uiState.set(merged)
}

export const resetUiState = () => $uiState.set(buildUiState())
