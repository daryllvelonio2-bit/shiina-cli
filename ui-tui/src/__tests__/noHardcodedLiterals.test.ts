/**
 * Regression guard: no hardcoded presentation literals in the TUI.
 *
 * The chrome — glyph vocabulary, border styles, container spacing — is owned by
 * the design token table in `src/design.ts` and overridable per design from
 * `shiina_cli/designs/*.yaml`. A literal typed into a component escapes that
 * table: the design switch misses it and restyling is a hunt through renderers
 * again. This test reads SOURCE (comments stripped, so banner art and prose
 * never match) and fails on a reintroduced literal, naming the file, the line,
 * the literal, and the fix.
 *
 * Scanned: every `.ts`/`.tsx` under `ui-tui/src` EXCEPT test files — the
 * `__tests__/` tree and any `*.test.ts(x)` beside its subject. A test asserts
 * ABOUT chrome, so the literal it names is the ASSERTION, not chrome being
 * drawn: tokenising it makes the assertion tautological, and exempting each
 * one buries the allowlist (13 of the first 25 entries were exactly that).
 * Production chrome is still covered end to end; the injected-literal check
 * (`todoPanel.tsx`) proves the guard still fires.
 * Allowlisted: the genuinely non-chrome hits in `ALLOWLIST` below, each WITH A
 * REASON. An entry without a reason — or one that matches nothing any more —
 * fails too, so the list cannot rot.
 *
 * Deliberately NOT detected: a single box-drawing character (`\u2500`). Alone
 * it is a token definition (design.ts) or a legitimate token override in a
 * fixture; the regression this guards is chrome DRAWN inline, i.e. a run.
 *
 * The second family — the inline separator (`\u00b7`), the meter cells (`\u2588`,
 * `\u2591`) and the ruler tick (`\u253c`) — needs a SHAPE rule rather than a
 * `line.includes`, for the same reason: a mid-dot is also the punctuation inside
 * ~130 sentences of hint copy (a key-hint line like `select \u00b7 Enter open`),
 * and a design token cannot be spliced into arbitrary prose without rewriting
 * every one of those lines. So only a literal whose VALUE is the chrome is
 * flagged: a whole-separator value, a template that opens with it, a lone
 * separator as JSX text, or a literal made of meter cells. A separator embedded
 * inside a longer string of copy stays literal — by decision, and therefore
 * outside this guard's vocabulary.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const SRC_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

/** Escape-written so this file is itself literal-free — it gets scanned too. */
const GLYPH_CHARS = [
  '\u25b8',
  '\u25be',
  '\u25cf',
  '\u2713',
  '\u2717',
  '\u25b6',
  '\u25cb',
  '\u25c9',
  '\u203a',
  '\u2304',
  '\u2022',
  '\u23fa'
]

const BORDER_STYLE_RE = /borderStyle\s*=\s*["']/
const BOX_DRAWING_RE = /[\u2500\u2501]{2,}/g
const PADDING_RE = /padding([XY])\s*=\s*\{\s*(\d+)\s*\}/g

/** Chrome whose character cannot be matched bare (see the header): the shapes.
 *  Each captures only the chrome character so the allowlist keys stay stable. */
const SEPARATOR_RE = /['"`][ \t]*(\u00b7)[ \t]*['"`]/g
const SEPARATOR_HEAD_RE = /['"`][ \t]*(\u00b7)[ \t]*\$\{/g
const SEPARATOR_JSX_RE = /(?:^|[}>])[ \t]*(\u00b7)[ \t]*(?:\{|<|$)/g
/** A literal made only of METER cells. The eighth-block ramps/heat markers are
 *  a data encoding, not the meter (see ALLOWLIST). */
const CELL_RE = /['"`][ \t]*([\u2588\u2591]+)[ \t]*['"`]/g
const RULER_RE = /['"`][ \t]*(\u253c)[ \t]*['"`]/g

/** Test files are assertions ABOUT chrome, not chrome: out of scan scope. */
const TEST_FILE_RE = /\.test\.tsx?$/

type LiteralKind = 'glyph' | 'borderStyle' | 'boxDrawing' | 'padding' | 'separator' | 'cell' | 'ruler'

interface Violation {
  /** Path relative to `ui-tui/src`, posix separators. */
  file: string
  line: number
  literal: string
  kind: LiteralKind
  /** The offending source line, trimmed — context for the failure message. */
  text: string
}

/** A regex literal can only start where a value is expected, never after an identifier. */
const isRegexStart = (source: string, at: number): boolean => {
  for (let i = at - 1; i >= 0; i -= 1) {
    const c = source[i]!

    if (c === ' ' || c === '\t' || c === '\n' || c === '\r') {
      continue
    }

    return '(,=:[!&|?{};+-*/%~^>'.includes(c)
  }

  return true
}

/**
 * Blank out line, block and JSX comments while preserving line numbers, so the
 * pre-existing banner comments in this tree never read as a hardcoded rule.
 *
 * Strings, template literals — including their `${}` holes, which are code
 * again — and regex literals are skipped whole. Getting that wrong is not
 * cosmetic: a template nested inside another template reads as a closed string,
 * which leaves the rest of the file unstripped and turns every later banner
 * comment into a false positive.
 */
const blankComments = (source: string): string => {
  const chars = source.split('')

  const blank = (from: number, to: number): void => {
    for (let i = from; i < to && i < chars.length; i += 1) {
      if (chars[i] !== '\n') {
        chars[i] = ' '
      }
    }
  }

  const skipQuoted = (at: number): number => {
    const quote = source[at]!
    let i = at + 1

    while (i < source.length) {
      if (source[i] === '\\') {
        i += 2
        continue
      }
      const c = source[i]!
      i += 1
      if (c === quote) {
        break
      }
    }

    return i
  }

  const skipRegex = (at: number): number => {
    let inClass = false
    let i = at + 1

    while (i < source.length) {
      const c = source[i]!

      if (c === '\\') {
        i += 2
        continue
      }

      if (c === '[') {
        inClass = true
      } else if (c === ']') {
        inClass = false
      } else if (c === '/' && !inClass) {
        return i + 1
      } else if (c === '\n') {
        return i
      }

      i += 1
    }

    return i
  }

  function skipBraces(at: number): number {
    let depth = 1
    let i = at

    while (i < source.length) {
      const c = source[i]!

      if (c === '`') {
        i = skipTemplate(i)
        continue
      }
      if (c === '"' || c === "'") {
        i = skipQuoted(i)
        continue
      }

      if (c === '{') {
        depth += 1
      } else if (c === '}') {
        depth -= 1
        if (depth === 0) {
          return i + 1
        }
      }

      i += 1
    }

    return i
  }

  function skipTemplate(at: number): number {
    let i = at + 1

    while (i < source.length) {
      const c = source[i]!

      if (c === '\\') {
        i += 2
        continue
      }
      if (c === '`') {
        return i + 1
      }
      if (c === '$' && source[i + 1] === '{') {
        i = skipBraces(i + 2)
        continue
      }

      i += 1
    }

    return i
  }

  let i = 0

  while (i < source.length) {
    if (source.startsWith('//', i)) {
      const end = source.indexOf('\n', i)
      const stop = end === -1 ? source.length : end
      blank(i, stop)
      i = stop
      continue
    }

    if (source.startsWith('/*', i)) {
      const close = source.indexOf('*/', i + 2)
      const stop = close === -1 ? source.length : close + 2
      blank(i, stop)
      i = stop
      continue
    }

    const c = source[i]!

    if (c === '"' || c === "'") {
      i = skipQuoted(i)
      continue
    }

    if (c === '`') {
      i = skipTemplate(i)
      continue
    }

    if (c === '/' && isRegexStart(source, i)) {
      i = skipRegex(i)
      continue
    }

    i += 1
  }

  return chars.join('')
}

/** Every hardcoded presentation literal in one file's source. */
const scan = (source: string, file: string): Violation[] => {
  const violations: Violation[] = []

  blankComments(source)
    .split('\n')
    .forEach((line, index) => {
      const push = (literal: string, kind: LiteralKind) =>
        violations.push({ file, line: index + 1, literal, kind, text: line.trim() })

      for (const glyph of GLYPH_CHARS) {
        if (line.includes(glyph)) {
          push(glyph, 'glyph')
        }
      }

      const border = line.match(BORDER_STYLE_RE)
      if (border) {
        push(border[0], 'borderStyle')
      }

      for (const rule of line.matchAll(BOX_DRAWING_RE)) {
        push(rule[0], 'boxDrawing')
      }

      for (const padding of line.matchAll(PADDING_RE)) {
        if (padding[2] !== '0') {
          push(`padding${padding[1]}={${padding[2]}}`, 'padding')
        }
      }

      const shapes: [RegExp, LiteralKind][] = [
        [SEPARATOR_RE, 'separator'],
        [SEPARATOR_HEAD_RE, 'separator'],
        [SEPARATOR_JSX_RE, 'separator'],
        [CELL_RE, 'cell'],
        [RULER_RE, 'ruler']
      ]

      for (const [rule, kind] of shapes) {
        for (const match of line.matchAll(rule)) {
          push(match[1]!, kind)
        }
      }
    })

  return violations
}

const collectSources = (dir: string, out: string[] = []): string[] => {
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name)

    if (statSync(full).isDirectory()) {
      if (name !== 'node_modules' && name !== 'dist' && name !== '__tests__') {
        collectSources(full, out)
      }
    } else if (name.endsWith('.ts') || name.endsWith('.tsx')) {
      if (!TEST_FILE_RE.test(name)) {
        out.push(full)
      }
    }
  }

  return out
}

interface AllowlistEntry {
  /** Path relative to `ui-tui/src`. */
  path: string
  /** `'*'` allows every literal in that file. */
  literals: string[]
  /** WHY this hit is not chrome. An entry without a reason is itself a bug. */
  reason: string
}

const ALLOWLIST: AllowlistEntry[] = [
  {
    path: 'theme.ts',
    literals: ['›'],
    reason: 'Default brand icon and tool prefix glyphs aligned with codex design tokens.'
  },
  {
    path: 'lib/text.ts',
    literals: ['\u2713', '\u2717'],
    reason: 'Pinned tool-trail wire protocol marks (TOOL_TRAIL_OK / TOOL_TRAIL_ERR) for transcript persistence.'
  },
  {
    path: 'design.ts',
    literals: ['*'],
    reason:
      'The DEFAULT_GLYPHS / DEFAULT_BORDERS table itself. This file is the canonical home of ' +
      'the literal characters; every other file must read them as tokens.'
  },
  {
    path: 'app/createGatewayEventHandler.ts',
    literals: ['\u2713'],
    reason:
      "Echoes the BACKEND's goal-line protocol: the gateway writes '\u2713 <goal>' lines and the " +
      "TUI matches startsWith to derive the status line. The mark belongs to the wire format, " +
      'not the chrome, so it cannot move to a token until the producer does.'
  },
  {
    path: 'content/faces.ts',
    literals: ['\u2022', '\u25c9'],
    reason:
      'Kaomoji faces are user-visible CONTENT (the face the user picks for the agent), not chrome.'
  },
  {
    path: 'lib/mathUnicode.ts',
    literals: ['\u2022'],
    reason: 'LaTeX-to-Unicode translation table: a mathematical symbol mapping, not chrome.'
  },
  {
    path: 'lib/charts.ts',
    literals: ['\u2588', '\u2591'],
    reason:
      'A chart cell encodes a NUMBER — the layer owns its own scale, so the gauge/hbar cells ' +
      'are data-viz, not chrome. The chrome meters read barFill/barEmpty.'
  },
  {
    path: 'lib/subagentTree.ts',
    literals: ['\u2588'],
    reason: 'The top cell of the sparkline ramp — a data encoding, not chrome.'
  },
  {
    path: 'app/createGatewayEventHandler.ts',
    literals: ['\u00b7'],
    reason:
      'The separator is baked into a spawn-tree LABEL that is POSTed to the backend ' +
      '(`spawn_tree.save`) — wire data, not chrome a renderer draws.'
  },
  {
    path: 'app/spawnHistoryStore.ts',
    literals: ['\u00b7'],
    reason:
      'The same persisted snapshot label as `createGatewayEventHandler` (stored, replayed, sent ' +
      'on the wire), so it cannot read a theme token.'
  },
]

const allows = (violation: Violation, entry: AllowlistEntry): boolean =>
  entry.path === violation.file &&
  (entry.literals.includes('*') || entry.literals.includes(violation.literal))

const report = (violations: Violation[]): string =>
  [
    `Hardcoded presentation literal(s) found — TUI chrome must come from design tokens (${violations.length}):`,
    '',
    ...violations.map(
      v => `  ${v.file}:${v.line}  ${JSON.stringify(v.literal)}  [${v.kind}]  ${v.text}`
    ),
    '',
    'How to fix:',
    '  1. Use the token: t.design.glyphs.<name>, t.design.borders.<panel|alert|rule>,',
    '     or t.design.spacing.<name>.',
    '  2. No token fits? Add one, in this order:',
    '       ui-tui/src/design.ts            (DesignGlyphs interface + DEFAULT_GLYPHS)',
    "       shiina_cli/design_cmd.py        (_DESIGN_KEYS: 'design.glyphs.<name>')",
    '       shiina_cli/designs/README.md    (the design.glyphs: block)',
    '     ...then read it from the component.',
    '  3. Genuinely not chrome (wire protocol, backend payload, a fixture pinning one)?',
    '     Add an entry to ALLOWLIST in this file WITH THE REASON STATED.',
    '     An entry without a reason is itself a bug.'
  ].join('\n')

const SOURCES = collectSources(SRC_ROOT)

const allViolations = SOURCES.flatMap(full =>
  scan(readFileSync(full, 'utf8'), relative(SRC_ROOT, full).split(sep).join('/'))
)

describe('design literal guard', () => {
  it('detects every literal kind the guard exists for', () => {
    // The fixtures below spell `=` as `\u003d` and the glyphs as `\uNNNN` so
    // this file contains no literal itself — it is scanned like any other.
    const source = [
      `const mark = '\u25b8'`,
      'const box = <Box borderStyle\u003d"round" />',
      'const rule = \'\u2500\u2500\u2500\u2500\'',
      'const pad = <Box paddingX\u003d{3} paddingY\u003d{1} />'
    ].join('\n')

    expect(scan(source, 'src/synthetic.tsx').map(v => [v.kind, v.literal])).toEqual([
      ['glyph', '\u25b8'],
      ['borderStyle', 'borderStyle\u003d"'],
      ['boxDrawing', '\u2500\u2500\u2500\u2500'],
      ['padding', 'paddingX\u003d{3}'],
      ['padding', 'paddingY\u003d{1}']
    ])
  })

  it('detects the separator, meter cell and ruler shapes', () => {
    // Escape-written like every other fixture here: this file is scanned too.
    const source = [
      "const sep = ' \u00b7 '",
      'const head = ` \u00b7 ${value}`',
      'const lone = <Text> \u00b7 </Text>',
      "const meter = '\u2588'.repeat(n) + '\u2591'.repeat(m)",
      "const tick = '\u253c'",
      "const prose = '\u2191/\u2193 select \u00b7 Enter open'"
    ].join('\n')

    expect(scan(source, 'src/synthetic.tsx').map(v => [v.kind, v.literal])).toEqual([
      ['separator', '\u00b7'],
      ['separator', '\u00b7'],
      ['separator', '\u00b7'],
      ['cell', '\u2588'],
      ['cell', '\u2591'],
      ['ruler', '\u253c']
    ])
  })

  it('ignores a separator embedded in a sentence of copy', () => {
    const source = [
      "const hint = '\u2191/\u2193 select \u00b7 Enter confirm \u00b7 Esc cancel'",
      "const notice = 'out of credits \u00b7 top up to continue'"
    ].join('\n')

    expect(scan(source, 'src/synthetic.ts')).toEqual([])
  })

  it('ignores a literal that only appears in a comment', () => {
    const source = [
      '// \u2500\u2500 header \u2500\u2500',
      '/* \u2713 done @ paddingX\u003d{4} */',
      'const label = {\'\u2022\': x}',
      "const t = '\u2713'"
    ].join('\n')

    expect(scan(source, 'src/synthetic.ts')).toEqual([
      { file: 'src/synthetic.ts', line: 3, literal: '\u2022', kind: 'glyph', text: "const label = {'\u2022': x}" },
      { file: 'src/synthetic.ts', line: 4, literal: '\u2713', kind: 'glyph', text: "const t = '\u2713'" }
    ])
  })

  it('ignores explicit zero padding (a reset, not a styling value)', () => {
    const source = ['<Box paddingX\u003d{0} paddingY\u003d{0} />', '<Box paddingX\u003d{2} />'].join('\n')

    expect(scan(source, 'src/synthetic.tsx').map(v => v.literal)).toEqual(['paddingX\u003d{2}'])
  })

  it('scans the whole TUI source tree, not an empty list', () => {
    expect(SOURCES.length).toBeGreaterThan(150)
    expect(SOURCES.some(f => f.endsWith('components/appChrome.tsx'))).toBe(true)
    expect(SOURCES.some(f => f.endsWith('design.ts'))).toBe(true)
  })

  it('has no unexplained allowlist entry', () => {
    expect(ALLOWLIST.filter(e => e.reason.trim().length === 0).map(e => e.path)).toEqual([])
    expect(ALLOWLIST.filter(e => e.literals.length === 0).map(e => e.path)).toEqual([])
  })

  it('has no stale allowlist entry', () => {
    const stale = ALLOWLIST.filter(e => !allViolations.some(v => allows(v, e))).map(e => e.path)

    expect(stale, 'allowlist entry matches nothing any more — delete it').toEqual([])
  })

  it('finds no hardcoded presentation literal in ui-tui/src', () => {
    const unexplained = allViolations.filter(v => !ALLOWLIST.some(e => allows(v, e)))

    expect(unexplained.length, report(unexplained)).toBe(0)
  })
})
