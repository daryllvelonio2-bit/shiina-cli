import { describe, expect, it } from 'vitest'

import {
  getScrollbarSnapshot,
  getViewportSnapshot,
  scrollbarSnapshotKey,
  viewportIsAtBottom,
  viewportSnapshotKey
} from '../lib/viewportStore.js'

describe('viewportStore', () => {
  // One definition of "at the bottom" for the whole app: the tail within a
  // couple of rows. ScrollBox restores stickiness only on an EXACT bottom
  // position, so a viewport left a row short (wheel tremor, click-select,
  // resize) reported "not at bottom" here and the tail follow stopped —
  // new streaming output landed below the viewport until a submit re-pinned.
  it('calls the tail within a couple of rows "at the bottom"', () => {
    expect(viewportIsAtBottom(0, 20, 20)).toBe(true)
    expect(viewportIsAtBottom(0, 20, 21)).toBe(true)
    expect(viewportIsAtBottom(0, 20, 22)).toBe(true)
    expect(viewportIsAtBottom(0, 20, 23)).toBe(false)
  })

  it('reports atBottom for a tail viewport that is scrolled short', () => {
    const handle = {
      getPendingDelta: () => 0,
      getScrollHeight: () => 42,
      getScrollTop: () => 20,
      getViewportHeight: () => 20,
      isSticky: () => false
    }

    expect(getViewportSnapshot(handle as any).atBottom).toBe(true)
  })

  it('normalizes absent scroll handles', () => {
    expect(getViewportSnapshot(null)).toEqual({
      atBottom: true,
      bottom: 0,
      pending: 0,
      scrollHeight: 0,
      top: 0,
      viewportHeight: 0
    })
  })

  it('includes pending scroll delta in snapshot math and keying', () => {
    const handle = {
      getPendingDelta: () => 3,
      getScrollHeight: () => 40,
      getScrollTop: () => 10,
      getViewportHeight: () => 5,
      isSticky: () => false
    }

    const snap = getViewportSnapshot(handle as any)

    expect(snap).toMatchObject({
      atBottom: false,
      bottom: 18,
      pending: 3,
      scrollHeight: 40,
      top: 13,
      viewportHeight: 5
    })
    expect(viewportSnapshotKey(snap)).toBe('0:16:5:40:3')
  })

  it('uses fresh scroll height to clear stale non-bottom state', () => {
    const handle = {
      getFreshScrollHeight: () => 20,
      getPendingDelta: () => 0,
      getScrollHeight: () => 40,
      getScrollTop: () => 15,
      getViewportHeight: () => 5,
      isSticky: () => false
    }

    const snap = getViewportSnapshot(handle as any)

    expect(snap.atBottom).toBe(true)
    expect(snap.scrollHeight).toBe(20)
  })

  it('keeps scrollbar position tied to committed scrollTop, not pending target', () => {
    const handle = {
      getPendingDelta: () => 24,
      getScrollHeight: () => 100,
      getScrollTop: () => 10,
      getViewportHeight: () => 20,
      isSticky: () => false
    }

    const viewport = getViewportSnapshot(handle as any)
    const scrollbar = getScrollbarSnapshot(handle as any)

    expect(viewport.top).toBe(34)
    expect(scrollbar).toEqual({
      scrollHeight: 100,
      top: 10,
      viewportHeight: 20
    })
    expect(scrollbarSnapshotKey(scrollbar)).toBe('10:20:100')
  })

  it('clamps scrollbar position to committed scroll bounds', () => {
    const handle = {
      getScrollHeight: () => 30,
      getScrollTop: () => 50,
      getViewportHeight: () => 20
    }

    expect(getScrollbarSnapshot(handle as any).top).toBe(10)
  })

  it('uses fresh scroll height to clear stale scrollbar non-bottom state after shrink', () => {
    const handle = {
      getFreshScrollHeight: () => 40,
      getScrollHeight: () => 60,
      getScrollTop: () => 20,
      getViewportHeight: () => 20
    }

    const snap = getScrollbarSnapshot(handle as any)

    expect(snap).toEqual({
      scrollHeight: 40,
      top: 20,
      viewportHeight: 20
    })
    expect(scrollbarSnapshotKey(snap)).toBe('20:20:40')
  })
})
