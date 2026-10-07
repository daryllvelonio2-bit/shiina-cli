import type { ScrollBoxHandle } from '@shiina/ink'
import type { RefObject } from 'react'
import { useCallback, useMemo, useSyncExternalStore } from 'react'

export interface ViewportSnapshot {
  atBottom: boolean
  bottom: number
  pending: number
  scrollHeight: number
  top: number
  viewportHeight: number
}

export interface ScrollbarSnapshot {
  scrollHeight: number
  top: number
  viewportHeight: number
}

const EMPTY: ViewportSnapshot = {
  atBottom: true,
  bottom: 0,
  pending: 0,
  scrollHeight: 0,
  top: 0,
  viewportHeight: 0
}

const EMPTY_SCROLLBAR: ScrollbarSnapshot = {
  scrollHeight: 0,
  top: 0,
  viewportHeight: 0
}

// Rows of slack when deciding the viewport sits at the tail. A terminal
// viewport is a row-height slab of text, so "at the bottom" is the tail
// within a couple of rows, not an exact scrollTop — the mouse wheel, a
// click-select and a resize all land a row short. Shared with the scroll
// heal in useVirtualHistory so the app and ScrollBox can't drift apart on
// what "at the bottom" means.
export const VIEWPORT_AT_BOTTOM_SLACK_ROWS = 2

export const viewportIsAtBottom = (top: number, viewportHeight: number, scrollHeight: number): boolean =>
  top + viewportHeight >= scrollHeight - VIEWPORT_AT_BOTTOM_SLACK_ROWS

export function getViewportSnapshot(s?: ScrollBoxHandle | null): ViewportSnapshot {
  if (!s) {
    return EMPTY
  }

  const pending = s.getPendingDelta()
  const top = Math.max(0, s.getScrollTop() + pending)
  const viewportHeight = Math.max(0, s.getViewportHeight())
  const cachedScrollHeight = Math.max(viewportHeight, s.getScrollHeight())
  let scrollHeight = cachedScrollHeight
  const bottom = top + viewportHeight
  let atBottom = s.isSticky() || viewportIsAtBottom(top, viewportHeight, scrollHeight)

  if (!atBottom) {
    scrollHeight = Math.max(viewportHeight, s.getFreshScrollHeight?.() ?? cachedScrollHeight)
    atBottom = s.isSticky() || viewportIsAtBottom(top, viewportHeight, scrollHeight)
  }

  return {
    atBottom,
    bottom,
    pending,
    scrollHeight,
    top,
    viewportHeight
  }
}

export function viewportSnapshotKey(v: ViewportSnapshot) {
  return `${v.atBottom ? 1 : 0}:${Math.ceil(v.top / 8) * 8}:${v.viewportHeight}:${Math.ceil(v.scrollHeight / 8) * 8}:${v.pending}`
}

export function getScrollbarSnapshot(s?: ScrollBoxHandle | null): ScrollbarSnapshot {
  if (!s) {
    return EMPTY_SCROLLBAR
  }

  const viewportHeight = Math.max(0, s.getViewportHeight())
  const top = Math.max(0, s.getScrollTop())
  const cachedScrollHeight = Math.max(viewportHeight, s.getScrollHeight())
  let scrollHeight = cachedScrollHeight
  let maxTop = Math.max(0, scrollHeight - viewportHeight)

  if (top < maxTop) {
    const freshScrollHeight = Math.max(viewportHeight, s.getFreshScrollHeight?.() ?? cachedScrollHeight)
    const freshMaxTop = Math.max(0, freshScrollHeight - viewportHeight)

    if (top >= freshMaxTop) {
      scrollHeight = freshScrollHeight
      maxTop = freshMaxTop
    }
  }

  return {
    scrollHeight,
    top: Math.max(0, Math.min(maxTop, top)),
    viewportHeight
  }
}

export function scrollbarSnapshotKey(v: ScrollbarSnapshot) {
  return `${v.top}:${v.viewportHeight}:${v.scrollHeight}`
}

export function useViewportSnapshot(scrollRef: RefObject<ScrollBoxHandle | null>): ViewportSnapshot {
  const key = useSyncExternalStore(
    useCallback((cb: () => void) => scrollRef.current?.subscribe(cb) ?? (() => {}), [scrollRef]),
    () => viewportSnapshotKey(getViewportSnapshot(scrollRef.current)),
    () => viewportSnapshotKey(EMPTY)
  )

  return useMemo(() => {
    const [atBottom = '1', top = '0', viewportHeight = '0', scrollHeight = '0', pending = '0'] = key.split(':')

    return {
      atBottom: atBottom === '1',
      bottom: Number(top) + Number(viewportHeight),
      pending: Number(pending),
      scrollHeight: Number(scrollHeight),
      top: Number(top),
      viewportHeight: Number(viewportHeight)
    }
  }, [key])
}

export function useScrollbarSnapshot(scrollRef: RefObject<ScrollBoxHandle | null>): ScrollbarSnapshot {
  const key = useSyncExternalStore(
    useCallback((cb: () => void) => scrollRef.current?.subscribe(cb) ?? (() => {}), [scrollRef]),
    () => scrollbarSnapshotKey(getScrollbarSnapshot(scrollRef.current)),
    () => scrollbarSnapshotKey(EMPTY_SCROLLBAR)
  )

  return useMemo(() => {
    const [top = '0', viewportHeight = '0', scrollHeight = '0'] = key.split(':')

    return {
      scrollHeight: Number(scrollHeight),
      top: Number(top),
      viewportHeight: Number(viewportHeight)
    }
  }, [key])
}
