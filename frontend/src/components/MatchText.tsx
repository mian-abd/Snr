import { matchRanges } from '../lib/search'

/** A title with the parts a query matched in bold. */
export function MatchText({ text, query }: { text: string; query: string }) {
  const ranges = query.trim() ? matchRanges(query, text) : []
  if (!ranges.length) return <>{text}</>
  const parts = []
  let at = 0
  for (const [start, end] of ranges) {
    if (start > at) parts.push(text.slice(at, start))
    parts.push(<mark key={start}>{text.slice(start, end)}</mark>)
    at = end
  }
  if (at < text.length) parts.push(text.slice(at))
  return <>{parts}</>
}
