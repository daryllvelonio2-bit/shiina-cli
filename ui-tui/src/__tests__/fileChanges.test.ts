import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  $fileChanges,
  $fileChangesExpanded,
  $fileChangesTotals,
  collapseFileChanges,
  fetchFileChanges,
  toggleFileChanges
} from '../app/fileChangesStore.js'

const gwWith = (result: unknown) => ({ request: vi.fn().mockResolvedValue(result) }) as any

describe('file changes store', () => {
  beforeEach(() => {
    $fileChanges.set([])
    $fileChangesTotals.set({ changed: 0, added: 0, removed: 0 })
    $fileChangesExpanded.set(false)
  })

  it('maps a repo payload into files + totals', async () => {
    const files = [
      { path: 'src/app.py', added: 30, removed: 2, status: 'M' },
      { path: 'src/new.py', added: 12, removed: 0, status: '?' }
    ]

    await fetchFileChanges(gwWith({ repo: true, changed: 2, added: 42, removed: 2, files }), 'sid')

    expect($fileChanges.get()).toEqual(files)
    expect($fileChangesTotals.get()).toEqual({ changed: 2, added: 42, removed: 2 })
  })

  it('clears everything for a non-repo cwd', async () => {
    $fileChanges.set([{ path: 'a', added: 1, removed: 1, status: 'M' }])

    await fetchFileChanges(gwWith({ repo: false }), 'sid')

    expect($fileChanges.get()).toEqual([])
    expect($fileChangesTotals.get()).toEqual({ changed: 0, added: 0, removed: 0 })
  })

  it('clears without a session and never calls the backend', async () => {
    const gw = gwWith({ repo: true, changed: 1, added: 1, removed: 0, files: [] })

    await fetchFileChanges(gw, null)

    expect(gw.request).not.toHaveBeenCalled()
    expect($fileChangesTotals.get().changed).toBe(0)
  })

  it('drops the strip on a failed request instead of surfacing an error', async () => {
    const gw = { request: vi.fn().mockRejectedValue(new Error('boom')) } as any

    await fetchFileChanges(gw, 'sid')

    expect($fileChangesTotals.get()).toEqual({ changed: 0, added: 0, removed: 0 })
  })

  it('is collapsed by default and toggles', () => {
    expect($fileChangesExpanded.get()).toBe(false)

    toggleFileChanges()
    expect($fileChangesExpanded.get()).toBe(true)

    collapseFileChanges()
    expect($fileChangesExpanded.get()).toBe(false)
  })
})
