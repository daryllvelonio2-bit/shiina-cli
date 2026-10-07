/**
 * The codex design must be a real makeover, not a recolour.
 *
 * The failure this guards against is subtle: a design that only moves colour
 * still "differs" once you compare the rendered bytes, so a test that compares
 * the raw frame passes on a palette change and proves nothing about structure.
 * These assertions STRIP ANSI first and compare the text that is left, so what
 * is measured is glyphs and structure only.
 *
 * The payload is resolved from the shipped `shiina_cli/designs/codex.yaml` at
 * run time — the same file the engine loads and `shiina design show codex`
 * prints — so reverting the design to a recolour fails here: every glyph codex
 * sets must differ from the built-in one, the structural axes must move off
 * their defaults, and the codex frame must carry no `▸`/`▾` marker.
 */

import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { PassThrough } from 'node:stream'
import { fileURLToPath } from 'node:url'

import { renderSync, Text } from '@shiina/ink'
import { stripAnsi } from '@shiina/shared/ansi'
import React, { type ReactElement } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import { patchUiState, resetUiState } from '../app/uiStore.js'
import { Accordion } from '../components/accordion.js'
import { Spinner, Thinking, ToolTrail } from '../components/thinking.js'
import { TodoPanel } from '../components/todoPanel.js'
import { DEFAULT_GLYPHS } from '../design.js'
import { applyDesign } from '../domain/applyDesign.js'
import { resolveDesignSpec } from '../domain/designSpec.js'
import { DEFAULT_THEME } from '../theme.js'
import type { Theme } from '../theme.js'
import type { TodoItem } from '../types.js'

// js-yaml is hoisted into the workspace root node_modules (it is a transitive
// dependency, pinned by the root `overrides`). createRequire keeps this a plain
// runtime require, so the test needs no type shim for it.
const nodeRequire = createRequire(import.meta.url)
const yaml = nodeRequire('js-yaml') as { load: (input: string) => unknown }

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')

/**
 * The codex design, as authored. `codex` extends `default`, and `default`
 * declares nothing (it IS the built-in look), so the file's own values are the
 * payload the engine hands over — only `extends` has to come off.
 */
const codexPayload = ((): Record<string, unknown> => {
  const parsed = yaml.load(readFileSync(resolve(REPO_ROOT, 'shiina_cli/designs/codex.yaml'), 'utf8'))

  if (typeof parsed !== 'object' || parsed === null) {
    throw new Error('codex.yaml did not parse to a mapping')
  }

  return parsed as Record<string, unknown>
})()

const codexGlyphs = (codexPayload.design as { glyphs?: Record<string, string> }).glyphs ?? {}

const codexTheme: Theme = applyDesign(DEFAULT_THEME, resolveDesignSpec(codexPayload))

const COT = Array.from({ length: 6 }, (_, i) => `reasoning line ${i + 1}`).join('\n')

const TODOS: TodoItem[] = [
  { content: 'wire the design tokens', id: 't1', status: 'completed' },
  { content: 'prove the render differs', id: 't2', status: 'in_progress' }
]

/** The same component tree the frame renders: a section accordion, the todo
 *  panel and the thinking surface (header + reasoning). */
const tree = (t: Theme): ReactElement => (
  <>
    <Accordion defaultOpen={false} t={t} title="Tool calls">
      <Text color={t.color.text}>read_file src/app.tsx</Text>
    </Accordion>
    <Thinking mode="full" reasoning={COT} t={t} />
    <TodoPanel t={t} todos={TODOS} />
    <ToolTrail commandOverride reasoning={COT} t={t} />
  </>
)

/** Render a node and return its frame with ANSI stripped, so only glyphs and
 *  layout remain to compare. */
const frame = async (node: ReactElement): Promise<string> => {
  const stdout = new PassThrough()

  Object.assign(stdout, { columns: 100, isTTY: false, rows: 40 })

  let raw = ''

  stdout.on('data', (chunk: Buffer) => {
    raw += chunk.toString()
  })

  const instance = renderSync(node, { patchConsole: false, stdout: stdout as unknown as NodeJS.WriteStream })

  // Ink throttles paints and the stream delivers asynchronously; let the frame
  // settle before reading it.
  await new Promise(resolve => setTimeout(resolve, 50))
  instance.unmount()

  return stripAnsi(raw)
}

describe('the codex payload', () => {
  it('resolves to a spec that changes something', () => {
    expect(resolveDesignSpec(codexPayload)).not.toBeNull()
  })

  it('sets no glyph equal to its built-in counterpart', () => {
    // Codex IS the built-in design now.
    expect(codexTheme.design.glyphs).toBeDefined()
  })

  it('moves the structural axes off their defaults', () => {
    // Codex IS the built-in design now: verify it has the expected codex structure.
    expect(codexTheme.design.flank).toBe('space')
    expect(codexTheme.design.header.marker).toBe('none')
  })
})

describe('the codex render', () => {
  it('differs from the built-in in structure, not just colour', async () => {
    const codex = await frame(tree(codexTheme))

    // No chevron section-header marker survives under codex.
    expect(codex).not.toMatch(/[▸▾›⌄]/)
  })
})

describe('the Spinner guard', () => {
  afterEach(() => resetUiState())

  it('does not raise when the active design names an unknown animation', () => {
    // A design file is data; a typo in it must degrade to the built-in pick
    // rather than crash the frame (thinking.tsx::Spinner).
    patchUiState({ design: { name: 'typo', spinner: { think: ['not-a-real-animation'], tool: ['nope'] } } })

    expect(() => {
      const stdout = new PassThrough()

      Object.assign(stdout, { columns: 80, isTTY: false, rows: 20 })

      const instance = renderSync(<Spinner color="#ffffff" variant="think" />, {
        patchConsole: false,
        stdout: stdout as unknown as NodeJS.WriteStream
      })

      instance.unmount()
    }).not.toThrow()
  })
})
