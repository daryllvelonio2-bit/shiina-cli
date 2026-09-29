import assert from 'node:assert/strict'

import { test } from 'vitest'

import { desktopBackendSpawnEnv, guestOnboardingEnabled, skipIntroEnabled } from './guest-onboarding'
import { buildSpawnCommand } from './remote-lifecycle'

test('skipIntroEnabled: exactly "1" in env or --skip-intro on argv skips the first-run film', () => {
  assert.equal(skipIntroEnabled([], { SHIINA_SKIP_INTRO: '1' }), true)
  assert.equal(skipIntroEnabled(['electron', '.', '--skip-intro'], {}), true)

  assert.equal(skipIntroEnabled([], {}), false)
  assert.equal(skipIntroEnabled([], { SHIINA_SKIP_INTRO: 'true' }), false)
})

test('guestOnboardingEnabled: exactly "1" in env or --guest-onboarding on argv turns the free tier on', () => {
  assert.equal(guestOnboardingEnabled([], { SHIINA_GUEST_ONBOARDING: '1' }), true)
  assert.equal(guestOnboardingEnabled(['electron', '.', '--guest-onboarding'], {}), true)

  assert.equal(guestOnboardingEnabled([], {}), false)
  assert.equal(guestOnboardingEnabled([], { SHIINA_GUEST_ONBOARDING: 'true' }), false)
  assert.equal(guestOnboardingEnabled([], { SHIINA_GUEST_ONBOARDING: '0' }), false)
  assert.equal(guestOnboardingEnabled(['electron', '.', '--local'], { SHIINA_GUEST_ONBOARDING: '' }), false)
})

test('desktopBackendSpawnEnv stamps the launch decision last and never lets an inherited value leak', () => {
  const base = {
    SHIINA_HOME: '/tmp/home',
    SHIINA_DESKTOP: '1',
    SHIINA_GUEST_ONBOARDING: '1',
    PATH: '/usr/bin'
  }

  const on = desktopBackendSpawnEnv({ ...base, SHIINA_GUEST_ONBOARDING: '0' }, true)
  assert.equal(on.SHIINA_GUEST_ONBOARDING, '1')

  const off = desktopBackendSpawnEnv(base, false)
  assert.equal(off.SHIINA_GUEST_ONBOARDING, '0', 'a stray inherited "1" must not turn the free tier on')

  for (const env of [on, off]) {
    assert.equal(env.SHIINA_HOME, base.SHIINA_HOME)
    assert.equal(env.SHIINA_DESKTOP, base.SHIINA_DESKTOP)
    assert.equal(env.PATH, base.PATH)
  }
})

test('remote SSH spawn command carries SHIINA_GUEST_ONBOARDING=1 only when the launch decided on', () => {
  const on = buildSpawnCommand('/x/shiina', 'work', { logPath: '~/.shiina/log', guestOnboarding: true })
  assert.match(on, /exec env SHIINA_DESKTOP=1 SHIINA_GUEST_ONBOARDING=1 /)

  const off = buildSpawnCommand('/x/shiina', 'work', { logPath: '~/.shiina/log', guestOnboarding: false })
  assert.match(off, /exec env SHIINA_DESKTOP=1 /)
  assert.doesNotMatch(off, /SHIINA_GUEST_ONBOARDING/)

  const unset = buildSpawnCommand('/x/shiina', 'work', { logPath: '~/.shiina/log' })
  assert.doesNotMatch(unset, /SHIINA_GUEST_ONBOARDING/)
})
