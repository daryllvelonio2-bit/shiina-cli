import { appendFileSync, writeFileSync } from 'node:fs'

import { describe, it } from 'vitest'

import { hasReasoningTag, splitReasoning } from '../lib/reasoning.js'
import { liveTailWindow } from '../lib/text.js'

const para = (n: number) =>
  Array.from({ length: n }, (_, i) => `Paragraph ${i}: the agent is working on step ${i} and writing prose.`).join('\n\n')

const OUT = '/tmp/bench_stream_commit.txt'
writeFileSync(OUT, '')

describe('bench: per-commit stream work', () => {
  it('measures scheduleStreaming work vs accumulated reply size', () => {
    for (const target of [8_000, 32_000, 128_000, 512_000, 1_000_000]) {
      let text = para(Math.ceil(target / 78))

      while (text.length < target) {
        text += text
      }

      text = text.slice(0, target)

      // Warm.
      hasReasoningTag(text)
      splitReasoning(text)

      const reps = Math.max(1, Math.round(200_000 / target))
      const t0 = performance.now()

      for (let i = 0; i < reps; i++) {
        const raw = text.trimStart()
        const visible = hasReasoningTag(raw) ? splitReasoning(raw).text : raw

        liveTailWindow(visible)
      }

      const perCommit = (performance.now() - t0) / reps

      appendFileSync(
        OUT,
        `rawTrim=${(target / 1024).toFixed(0)}KB  splitReasoning+liveTailWindow=${perCommit.toFixed(2)}ms\n`
      )
    }
  })
})
