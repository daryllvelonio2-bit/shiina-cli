import { mkdtempSync, readdirSync, rmSync, statSync, utimesSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Readable } from 'node:stream'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { performHeapDump } from './memory.js'

// v8.getHeapSnapshot() serializes the worker's entire heap: hundreds of ms to
// seconds per call, growing with the heap, and nothing else here stubs it.
// These tests pin the auto-heapdump opt-in gate and the retention prune — not
// v8's serializer — so stand in a tiny synthetic stream. Without this, the
// tests that dump more than once (three truthy spellings; the retention case)
// raced the 5s budget under load and reported a timeout, not a gate failure.
vi.mock('node:v8', async importOriginal => ({
  ...(await importOriginal<typeof import('node:v8')>()),
  getHeapSnapshot: () => Readable.from(['{"snapshot":true}'])
}))

const ENV_KEYS = ['SHIINA_AUTO_HEAPDUMP', 'SHIINA_HEAPDUMP_DIR', 'SHIINA_HEAPDUMP_MAX_BYTES'] as const

describe('performHeapDump auto opt-in gate (#21767)', () => {
  let saved: Record<string, string | undefined>
  let dir: string

  beforeEach(() => {
    saved = {}

    for (const k of ENV_KEYS) {
      saved[k] = process.env[k]
      delete process.env[k]
    }

    dir = mkdtempSync(join(tmpdir(), 'shiina-heapdump-test-'))
    process.env.SHIINA_HEAPDUMP_DIR = dir
  })

  afterEach(() => {
    for (const k of ENV_KEYS) {
      if (saved[k] === undefined) {
        delete process.env[k]
      } else {
        process.env[k] = saved[k]
      }
    }

    rmSync(dir, { force: true, recursive: true })
  })

  it('writes diagnostics only for auto-high without SHIINA_AUTO_HEAPDUMP', async () => {
    const result = await performHeapDump('auto-high')

    expect(result.success).toBe(true)
    expect(result.suppressed).toBe(true)
    expect(result.diagPath).toBeDefined()
    expect(result.heapPath).toBeUndefined()

    const files = readdirSync(dir)
    expect(files.some(f => f.endsWith('.diagnostics.json'))).toBe(true)
    expect(files.some(f => f.endsWith('.heapsnapshot'))).toBe(false)
  })

  it('writes diagnostics only for auto-critical without SHIINA_AUTO_HEAPDUMP', async () => {
    const result = await performHeapDump('auto-critical')

    expect(result.success).toBe(true)
    expect(result.suppressed).toBe(true)
    expect(result.heapPath).toBeUndefined()

    const files = readdirSync(dir)
    expect(files.some(f => f.endsWith('.heapsnapshot'))).toBe(false)
  })

  it('writes both diagnostics and snapshot for auto-high when SHIINA_AUTO_HEAPDUMP=1', async () => {
    process.env.SHIINA_AUTO_HEAPDUMP = '1'

    const result = await performHeapDump('auto-high')

    expect(result.success).toBe(true)
    expect(result.suppressed).toBeUndefined()
    expect(result.diagPath).toBeDefined()
    expect(result.heapPath).toBeDefined()

    const files = readdirSync(dir)
    expect(files.some(f => f.endsWith('.heapsnapshot'))).toBe(true)
  })

  it('accepts truthy spellings (true|yes|on, case-insensitive) as opt-in', async () => {
    for (const value of ['true', 'YES', 'On']) {
      process.env.SHIINA_AUTO_HEAPDUMP = value
      const result = await performHeapDump('auto-high')

      expect(result.success).toBe(true)
      expect(result.heapPath).toBeDefined()
    }
  })

  it('treats other values (0, off, garbage) as opt-out for auto triggers', async () => {
    for (const value of ['0', 'off', 'nope']) {
      process.env.SHIINA_AUTO_HEAPDUMP = value
      const result = await performHeapDump('auto-high')

      expect(result.success).toBe(true)
      expect(result.suppressed).toBe(true)
      expect(result.heapPath).toBeUndefined()
    }
  })

  it('writes both for manual triggers regardless of SHIINA_AUTO_HEAPDUMP', async () => {
    const result = await performHeapDump('manual')

    expect(result.success).toBe(true)
    expect(result.suppressed).toBeUndefined()
    expect(result.heapPath).toBeDefined()

    const files = readdirSync(dir)
    expect(files.some(f => f.endsWith('.heapsnapshot'))).toBe(true)
  })
})

describe('heapdump retention guard (#21767)', () => {
  let savedDir: string | undefined
  let savedMax: string | undefined
  let dir: string

  beforeEach(() => {
    savedDir = process.env.SHIINA_HEAPDUMP_DIR
    savedMax = process.env.SHIINA_HEAPDUMP_MAX_BYTES
    delete process.env.SHIINA_AUTO_HEAPDUMP
    dir = mkdtempSync(join(tmpdir(), 'shiina-heapdump-prune-'))
    process.env.SHIINA_HEAPDUMP_DIR = dir
  })

  afterEach(() => {
    if (savedDir === undefined) {
      delete process.env.SHIINA_HEAPDUMP_DIR
    } else {
      process.env.SHIINA_HEAPDUMP_DIR = savedDir
    }

    if (savedMax === undefined) {
      delete process.env.SHIINA_HEAPDUMP_MAX_BYTES
    } else {
      process.env.SHIINA_HEAPDUMP_MAX_BYTES = savedMax
    }

    rmSync(dir, { force: true, recursive: true })
  })

  it('evicts oldest files when total bytes exceed the cap, retaining the newest', async () => {
    // 4 pre-existing dumps, 1KB each, with ascending mtimes (oldest first).
    const blob = 'x'.repeat(1024)
    const now = Date.now()

    for (let i = 0; i < 4; i++) {
      const p = join(dir, `old-${i}.heapsnapshot`)
      writeFileSync(p, blob)
      const t = (now - (4 - i) * 60_000) / 1000
      utimesSync(p, t, t)
    }

    // Cap at 2KB → a fresh diagnostics write should trigger a prune down to ~cap.
    process.env.SHIINA_HEAPDUMP_MAX_BYTES = String(2 * 1024)

    const result = await performHeapDump('auto-high')
    expect(result.success).toBe(true)

    const remaining = readdirSync(dir)
    const totalBytes = remaining.reduce((acc, f) => acc + statSync(join(dir, f)).size, 0)
    // Contract: prune evicts oldest-first until total <= cap, but always keeps
    // the single newest file even if it alone exceeds the cap. So either the
    // total is under cap, or exactly one (newest) file remains.
    expect(totalBytes <= 2 * 1024 || remaining.length === 1).toBe(true)
    // The old 1KB dumps must have been pruned down from the original four.
    expect(remaining.length).toBeLessThan(5)
    // The brand-new diagnostics sidecar must survive the prune.
    expect(remaining.some(f => f.endsWith('.diagnostics.json'))).toBe(true)
  })
})
