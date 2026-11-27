import { lazy, Suspense, useEffect, useRef, useState, type ComponentProps, type ReactNode } from 'react'
import { Skeleton } from '../ui'

// The bar charts draw with the chart library, the heaviest dependency. These wrappers load that
// code only when a chart is about to scroll into view, so a page's first paint does not wait for it.
const ModelBarsChart = lazy(() => import('./ModelBars').then((m) => ({ default: m.ModelBars })))
const CompareBarsChart = lazy(() => import('./CompareBars').then((m) => ({ default: m.CompareBars })))

function WhenNear({ height, children }: { height: number; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const [near, setNear] = useState(() => typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    const node = ref.current
    if (near || !node) return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setNear(true)
        observer.disconnect()
      }
    }, { rootMargin: '200px 0px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [near])
  return <div ref={ref}>{near ? <Suspense fallback={<Skeleton height={height} />}>{children}</Suspense> : <Skeleton height={height} />}</div>
}

export function ModelBars(props: ComponentProps<typeof ModelBarsChart>) {
  return <WhenNear height={props.height ?? 360}><ModelBarsChart {...props} /></WhenNear>
}

export function CompareBars(props: ComponentProps<typeof CompareBarsChart>) {
  return <WhenNear height={props.height ?? 300}><CompareBarsChart {...props} /></WhenNear>
}
