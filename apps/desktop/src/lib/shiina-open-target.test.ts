import { describe, expect, it } from 'vitest'

import {
  normalizeShiinaOpenString,
  pathFromShiinaDeepLink,
  pathFromOpenDeepLink,
  resolveShiinaOpenPath
} from './shiina-open-target'

describe('normalizeShiinaOpenString', () => {
  it('accepts hash-router paths and strips a leading hash', () => {
    expect(normalizeShiinaOpenString('/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeShiinaOpenString('#/index-network/intent/1')).toBe('/index-network/intent/1')
  })

  it('maps plugin-scoped shiina:// deep links to the same path', () => {
    expect(normalizeShiinaOpenString('shiina://index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeShiinaOpenString('shiina://index-network/intent/1?focus=true')).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('maps shiina://open/… deep links by stripping the open host', () => {
    expect(normalizeShiinaOpenString('shiina://open/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeShiinaOpenString('shiina://open/settings/plugins')).toBe('/settings/plugins')
  })

  it('rejects reserved shiina kinds and unsafe paths', () => {
    expect(normalizeShiinaOpenString('shiina://blueprint/morning-brief')).toBeNull()
    expect(normalizeShiinaOpenString('shiina://plugin/install')).toBeNull()
    expect(normalizeShiinaOpenString('https://example.com/x')).toBeNull()
    expect(normalizeShiinaOpenString('/../etc/passwd')).toBeNull()
    expect(normalizeShiinaOpenString('index-network')).toBeNull()
  })
})

describe('resolveShiinaOpenPath', () => {
  it('merges structured path + params', () => {
    expect(resolveShiinaOpenPath({ path: '/index-network/intent/1', params: { focus: 'true' } })).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('resolves href the same as a bare string', () => {
    expect(resolveShiinaOpenPath({ href: 'shiina://index-network/intent/1' })).toBe('/index-network/intent/1')
  })
})

describe('pathFromShiinaDeepLink', () => {
  it('builds the navigate path from a plugin-scoped deep-link payload', () => {
    expect(pathFromShiinaDeepLink('index-network', 'intent/1')).toBe('/index-network/intent/1')
  })

  it('builds the navigate path from shiina://open/… payloads', () => {
    expect(pathFromOpenDeepLink('index-network/intent/1')).toBe('/index-network/intent/1')
    expect(pathFromShiinaDeepLink('open', 'agent/42')).toBe('/agent/42')
  })

  it('ignores reserved kinds', () => {
    expect(pathFromShiinaDeepLink('blueprint', 'morning-brief')).toBeNull()
    expect(pathFromShiinaDeepLink('plugin', 'install')).toBeNull()
    expect(pathFromShiinaDeepLink('skill', 'install')).toBeNull()
  })
})
