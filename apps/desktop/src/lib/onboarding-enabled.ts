/** The preload launch flag is the only gate for guided onboarding. */
export function isOnboardingEnabled(): boolean {
  return window.shiinaDesktop?.guestOnboardingEnabled === true
}
