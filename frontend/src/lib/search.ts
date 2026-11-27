/** Lowercase with accents stripped, so a query matches regardless of case or diacritics. */
export const normalize = (text: string) => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()

const boundary = /[\s\-_./()·,:]/

/** One query word against normalized text: the start of a word scores best, then anywhere, then letters in order. */
function tokenScore(token: string, text: string, inOrder: boolean): number | null {
  const index = text.indexOf(token)
  if (index === 0) return 120 + token.length
  if (index > 0) return (boundary.test(text[index - 1]) ? 90 : 55) + token.length
  if (!inOrder) return null
  // Letters in order ("gm4" finds "Gemma 4"), worth less the more they are spread out.
  let from = 0
  let first = -1
  let gaps = 0
  for (const char of token) {
    const found = text.indexOf(char, from)
    if (found < 0) return null
    if (first < 0) first = found
    else gaps += found - from
    from = found + 1
  }
  if (gaps > token.length * 2 + 2) return null
  return Math.max(1, 40 - gaps * 3 - first * 0.2)
}

const words = (query: string) => normalize(query).split(/\s+/).filter(Boolean)

/**
 * How well a query matches an item: each word against the title (also as letters in order), or
 * failing that against the item's keywords, or its description (only as written, and worth less
 * in that order, so a section tagged "robustness" outranks a page that mentions it). Null when a
 * word matches none of them.
 */
export function rankScore(query: string, title: string, keywords = '', description = ''): number | null {
  const tokens = words(query)
  if (!tokens.length) return 0
  const name = normalize(title)
  const tags = normalize(keywords)
  const about = normalize(description)
  let total = 0
  for (const token of tokens) {
    const own = tokenScore(token, name, true)
    const tagged = tags ? tokenScore(token, tags, false) : null
    const described = about ? tokenScore(token, about, false) : null
    if (own == null && tagged == null && described == null) return null
    total += Math.max(own ?? -Infinity, tagged == null ? -Infinity : tagged - 45, described == null ? -Infinity : described - 60)
  }
  return total
}

/** Character ranges of a title that a query's words match directly (for highlighting). */
export function matchRanges(query: string, title: string): Array<[number, number]> {
  const text = normalize(title)
  const ranges: Array<[number, number]> = []
  for (const token of normalize(query).split(/\s+/).filter(Boolean)) {
    const index = text.indexOf(token)
    if (index >= 0) ranges.push([index, index + token.length])
  }
  ranges.sort((a, b) => a[0] - b[0])
  const merged: Array<[number, number]> = []
  for (const range of ranges) {
    const last = merged[merged.length - 1]
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1])
    else merged.push([...range])
  }
  return merged
}

/** The site's pages, for the search palette. */
export const sitePages = [
  { path: '/', label: 'Home', about: 'The findings at a glance', keywords: 'start overview findings summary' },
  { path: '/router', label: 'Router', about: 'Preview where a prompt would go, then run it', keywords: 'route prompt decision preview run priority what-if' },
  { path: '/models', label: 'Models', about: 'Every model with accuracy, price, speed, and live status', keywords: 'catalog prices table leaderboard availability' },
  { path: '/compare', label: 'Compare', about: 'Up to four models side by side', keywords: 'versus vs side by side comparison' },
  { path: '/research', label: 'Research', about: 'Leaderboard, significance, errors, robustness, and method', keywords: 'paper results evaluation study' },
  { path: '/prompts', label: 'Prompts', about: 'Every prompt, how each model did, and where the router sent it', keywords: 'prompt explorer questions examples answers per prompt browse mistakes' },
  { path: '/faq', label: 'FAQ', about: 'Questions answered from the data', keywords: 'questions answers help' },
  { path: '/lab', label: 'Lab', about: 'The rule-based router and the early pilots', keywords: 'rule based pilot gsm8k benchmark eligibility' },
] as const

/**
 * The research page's sections (its side navigation), for the search palette. Sections whose ID
 * starts with "study-" exist only once that pool study has been run, and "scoring-fix" only once
 * the scoring-fix study has.
 */
export const researchSections = [
  { id: 'highlights', label: 'Highlights', keywords: 'summary findings' },
  { id: 'leaderboard', label: 'Leaderboard', keywords: 'strategies ranking accuracy cost' },
  { id: 'tradeoffs', label: 'Accuracy, cost, speed', keywords: 'tradeoff scatter frontier' },
  { id: 'significance', label: 'Is it real?', keywords: 'significance mcnemar confidence intervals statistics' },
  { id: 'study-flagship', label: 'With flagship models', keywords: 'flagship study pool' },
  { id: 'study-wide', label: 'With every model', keywords: 'wide study pool budget' },
  { id: 'errors', label: 'Where it goes wrong', keywords: 'routing errors mistakes oracle regret' },
  { id: 'robustness', label: 'When things change', keywords: 'robustness drift scenarios outage price' },
  { id: 'scoring-fix', label: 'Fixing the scoring flaw', keywords: 'scoring fix normalization reference reliability weight gemma mercury unavailable' },
  { id: 'priorities', label: 'Your priorities', keywords: 'weights sweep cost latency' },
  { id: 'training', label: 'How it was built', keywords: 'training classifier logistic features' },
  { id: 'method', label: 'Method and limits', keywords: 'methodology limitations protocol' },
  { id: 'downloads', label: 'Downloads', keywords: 'csv json export data' },
] as const
