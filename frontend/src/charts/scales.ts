import { useLayoutEffect, useRef, useState } from 'react'

/** A position along one axis: `at` maps a value to 0..1, `ticks` are the labeled gridlines. */
export type Scale = {
  at: (value: number) => number
  ticks: Array<{ value: number; label: string }>
}

function niceStep(raw: number) {
  const power = 10 ** Math.floor(Math.log10(raw || 1))
  return [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((value) => value >= raw) ?? 10 * power
}

/**
 * A linear scale padded out to round numbers. `minSpan` keeps a handful of answers from
 * looking like a cliff; `floor` and `ceil` keep it inside what the measure allows.
 */
export function linearScale(values: number[], { format, count = 4, minSpan = 0, floor = -Infinity, ceil = Infinity }: {
  format: (value: number) => string
  count?: number
  minSpan?: number
  floor?: number
  ceil?: number
}): Scale {
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (!Number.isFinite(min) || !Number.isFinite(max)) [min, max] = [0, 1]
  if (max - min < minSpan) {
    const grow = (minSpan - (max - min)) / 2
    min -= grow
    max += grow
    if (max > ceil) [min, max] = [min - (max - ceil), ceil]
    if (min < floor) [min, max] = [floor, max + (floor - min)]
  }
  const step = niceStep((max - min) / count || 1)
  const lo = Math.max(floor, Math.floor(min / step) * step)
  let hi = Math.min(ceil, Math.ceil(max / step) * step)
  if (hi <= lo) hi = lo + step
  const ticks: Scale['ticks'] = []
  for (let value = Math.ceil(lo / step) * step; value <= hi + step * 1e-6; value += step) {
    const rounded = Number(value.toFixed(10))
    ticks.push({ value: rounded, label: format(rounded) })
  }
  return { at: (value) => (value - lo) / (hi - lo), ticks }
}

/**
 * A log scale that still has a place for zero: free sits at the left edge, then cents and
 * dollars by powers of ten (the same symlog the trade-off charts use).
 */
export function logScale(values: number[], format: (value: number) => string): Scale {
  const positive = values.filter((value) => value > 0)
  const smallest = positive.length ? Math.min(...positive) : 1
  const offset = smallest / 3
  const tx = (value: number) => Math.log10(Math.max(0, value) + offset)
  const lo = tx(0)
  const top = Math.max(...values, smallest)
  const hi = tx(top) + (tx(top) - lo) * 0.04 || lo + 1
  const ticks: Scale['ticks'] = [{ value: 0, label: format(0) }]
  for (let power = Math.floor(Math.log10(smallest)); power <= Math.ceil(Math.log10(top)); power += 1) {
    const value = 10 ** power
    if (tx(value) > lo + (hi - lo) * 0.06 && tx(value) <= hi) ticks.push({ value, label: format(value) })
  }
  return { at: (value) => (tx(value) - lo) / (hi - lo || 1), ticks }
}

/** Drop tick labels that would touch the one before, given where each lands in pixels. */
export function thinTicks(ticks: Scale['ticks'], px: (value: number) => number, charWidth = 6.3) {
  let lastRight = -Infinity
  return ticks.filter((tick) => {
    const half = (tick.label.length * charWidth) / 2
    if (px(tick.value) - half < lastRight + 8) return false
    lastRight = px(tick.value) + half
    return true
  })
}

/** Dollars for an axis: Free, then $0.001, $0.01, $0.1, $1. */
export const dollarTick = (value: number) => (value === 0 ? 'Free' : value < 1 ? `$${Number(value.toPrecision(1))}` : `$${Number(value.toPrecision(3))}`)

/** The rendered width of an element, so an SVG can draw at its real size instead of scaling text. */
export function useWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(fallback)
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const measure = () => setWidth(element.clientWidth || fallback)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [fallback])
  return [ref, width] as const
}
