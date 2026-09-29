import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { $bindings } from '@/store/keybinds'

import { TerminalRail } from './rail'
import { $activeTerminalId, $terminals, $terminalStatuses } from './terminals'

describe('TerminalRail', () => {
  beforeEach(() => {
    $terminals.set([{ auto: true, cwd: 'C:\\repo', id: 'term-1', kind: 'user', title: 'PowerShell' }])
    $activeTerminalId.set('term-1')
    $terminalStatuses.set({})
    $bindings.set({ ...$bindings.get(), 'view.showTerminal': ['ctrl+`'] })
  })

  afterEach(() => {
    cleanup()
    $terminals.set([])
    $activeTerminalId.set(null)
    $terminalStatuses.set({})
  })

  it('keeps the terminal hotkey in a portaled bubble facing into the window', async () => {
    const view = render(<TerminalRail />)

    fireEvent.pointerMove(screen.getByRole('tab', { name: '1. PowerShell' }), { pointerType: 'mouse' })
    await screen.findByRole('tooltip')

    const content = view.baseElement.querySelector<HTMLElement>('[data-slot="tooltip-content"]')
    const label = content?.querySelector('[data-slot="tooltip-label"]')

    expect(content).not.toBeNull()
    expect(view.container.contains(content)).toBe(false)
    expect(content?.classList.contains('tooltip-bubble')).toBe(true)
    expect(content?.getAttribute('data-side')).toBe('left')
    expect(label?.textContent).toContain('PowerShell')
    expect(content?.querySelector('[data-slot="tooltip-arrow"]')).not.toBeNull()
  })

  it('⌘-click closes the tab; a plain click selects it', () => {
    $terminals.set([...$terminals.get(), { auto: true, cwd: 'C:\\repo', id: 'term-2', kind: 'user', title: 'zsh' }])

    render(<TerminalRail />)

    fireEvent.click(screen.getByRole('tab', { name: '2. zsh' }), { metaKey: true })
    expect($terminals.get().map(term => term.id)).toEqual(['term-1'])

    fireEvent.click(screen.getByRole('tab', { name: '1. PowerShell' }))
    expect($activeTerminalId.get()).toBe('term-1')
    expect($terminals.get()).toHaveLength(1)
  })

  it('shows a live session dot per tab, defaulting to starting', () => {
    $terminals.set([
      { auto: true, cwd: 'C:\\repo', id: 'term-1', kind: 'user', title: 'PowerShell' },
      { auto: true, cwd: 'C:\\repo', id: 'term-2', kind: 'user', title: 'zsh' }
    ])
    $terminalStatuses.set({ 'term-2': 'open' })

    render(<TerminalRail />)

    const tabs = screen.getAllByRole('tab')
    expect(tabs[0].querySelector('[data-terminal-status]')?.getAttribute('data-terminal-status')).toBe('starting')
    expect(tabs[1].querySelector('[data-terminal-status]')?.getAttribute('data-terminal-status')).toBe('open')
  })

  it('names the session state and restored history in the tooltip, keeping the tab name stable', async () => {
    $terminals.set([
      {
        auto: true,
        cwd: 'C:\\repo',
        id: 'term-1',
        kind: 'user',
        reviveBuffer: 'prior scrollback',
        title: 'PowerShell'
      }
    ])
    $terminalStatuses.set({ 'term-1': 'open' })

    const view = render(<TerminalRail />)

    fireEvent.pointerMove(screen.getByRole('tab', { name: '1. PowerShell' }), { pointerType: 'mouse' })
    await screen.findByRole('tooltip')

    const label = view.baseElement.querySelector<HTMLElement>('[data-slot="tooltip-label"]')
    expect(label?.textContent).toContain('PowerShell')
    expect(label?.textContent).toContain('Shell running')
    expect(label?.textContent).toContain('restored history')
  })
})
