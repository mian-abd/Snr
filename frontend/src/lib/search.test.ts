import { expect, it } from 'vitest'
import { rankScore } from './search'

it('ranks an item tagged with a word above one whose description only mentions it', () => {
  const tagged = rankScore('robust', 'When things change', 'robustness drift scenarios', 'Research')
  const mentioned = rankScore('robust', 'Research', 'paper results', 'Leaderboard, significance, errors, robustness, and method')
  expect(tagged).not.toBeNull()
  expect(mentioned).not.toBeNull()
  expect(tagged ?? -1).toBeGreaterThan(mentioned ?? 0)
  // A title match still beats both.
  expect(rankScore('research', 'Research', '', '') ?? 0).toBeGreaterThan(tagged ?? 0)
  expect(rankScore('zzz', 'Research', 'paper', 'about')).toBeNull()
})
