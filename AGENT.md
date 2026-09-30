# AGENT.md — working rules for AI assistants on this repo

These rules sit on top of the repo's `AGENTS.md`. When they conflict, this file wins for
the things it names. Append new rules under § Latest rules — keep each one short.

---

## R1 — No bloat

Write the smallest thing that is correct. If it can be done in 2 lines, do not write 5.
No defensive wrappers around code that cannot fail, no flags nobody sets, no "just in case"
helpers, no re-stating the WHAT in comments or docstrings (keep the WHY).

Corollary: when you add a function, ask whether an existing one already does it. Deleting
lines is a valid fix.

## R2 — Every provider onboarding updates the process-provider notes

Whenever you connect a new CLI/tool to Shiina — certificates, keys, tokens, OAuth, a local
subprocess, a credential store on disk — you MUST update
`EXTERNAL_PROCESS_PROVIDERS_NOTES.md` **in the same change**, adding:

- **Steps** — the exact sequence used to wire it up (what was read, what was written).
- **Location** — every file + symbol + line touched, and where the credentials/token store
  lives on disk (`~/...`), including the binary-discovery env vars.
- **How** — the resolution path (which rung handles it), and the exact reason it broke if it
  was a fix, with the red-on-base proof.
- **Data needed** — aliases, display label, base_url/endpoint, auth_type, model list, the
  copy-paste reproduce/verify commands.

Goal: next time the AI can onboard or debug that provider from the file alone, without
re-deriving anything. If a detail was hard to find, it belongs in the file.

Reference implementation of this pattern: `EXTERNAL_PROCESS_PROVIDERS_NOTES.md` § 3–§ 5.

---

## Latest rules (append here)

<!-- R3 — ... -->
