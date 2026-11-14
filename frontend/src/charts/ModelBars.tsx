import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { localLogo, makerOf } from '../lib/makers'
import styles from './charts.module.css'

/** One bar per model (or router strategy), colored by who made it, labeled by its logo and name. */
export type ModelBar = {
  id: string
  name: string
  value: number
  display: string
  /** Model ID for the maker color and logo; routers and baselines use their own look. */
  modelId?: string
  kind?: 'model' | 'router' | 'baseline'
  local?: boolean
  details?: string[]
}

type TickProps = { x?: number; y?: number; payload?: { index: number }; bars: ModelBar[]; rotate: boolean }

function NameTick({ x = 0, y = 0, payload, bars, rotate }: TickProps) {
  const bar = payload ? bars[payload.index] : undefined
  if (!bar) return null
  const maker = bar.modelId ? makerOf(bar.modelId) : null
  const logo = bar.local ? localLogo : maker?.logo
  const mono = bar.local || maker?.mono
  return (
    <g transform={`translate(${x},${y})`}>
      {bar.kind === 'router'
        ? <rect x={-7} y={6} width={14} height={14} rx={3} className={styles.routerKey} />
        : logo
          ? <image href={logo} x={-8} y={5} width={16} height={16} className={mono ? styles.monoImage : undefined} />
          : <rect x={-6} y={7} width={12} height={12} rx={2} className={styles.baselineKey} />}
      <text className={styles.barName} transform={rotate ? 'translate(4 32) rotate(-45)' : 'translate(0 38)'} textAnchor={rotate ? 'end' : 'middle'}>
        {bar.name}
      </text>
    </g>
  )
}

type TooltipProps = { active?: boolean; payload?: Array<{ payload: ModelBar }> }

function BarTooltip({ active, payload }: TooltipProps) {
  const bar = active ? payload?.[0]?.payload : undefined
  if (!bar) return null
  return (
    <div className={styles.tooltipBox}>
      <strong>{bar.name}</strong>
      <span className={styles.tooltipValue}>{bar.display}</span>
      {bar.details?.map((line) => <span key={line}>{line}</span>)}
    </div>
  )
}

type LabelProps = { x?: number | string; y?: number | string; width?: number | string; value?: string | number; inside: boolean }

/** The value above (or inside the top of) its bar, on one line. */
function ValueLabel({ x = 0, y = 0, width = 0, value, inside }: LabelProps) {
  const cx = Number(x) + Number(width) / 2
  return (
    <text x={cx} y={Number(y) + (inside ? 16 : -7)} textAnchor="middle" className={inside ? styles.barValueInside : styles.barValueTop}>{value}</text>
  )
}

function fillFor(bar: ModelBar) {
  if (bar.kind === 'router') return 'url(#bars-router)'
  if (bar.kind === 'baseline') return 'var(--text-3)'
  return bar.modelId ? makerOf(bar.modelId).color : 'var(--maker-other)'
}

/**
 * Vertical bars in the style of a model leaderboard. `inside` puts the value in the bar (for
 * scores); `top` puts it above (for costs and times, where bars can be tiny).
 */
export function ModelBars({ bars, label, labelPosition = 'top', height = 360, domain }: {
  bars: ModelBar[]
  label: string
  labelPosition?: 'inside' | 'top'
  height?: number
  domain?: [number, number]
}) {
  const rotate = bars.length > 6
  const max = Math.max(...bars.map((bar) => bar.value), 0)
  return (
    <div className={styles.barsFrame} role="img" aria-label={`${label}: ${bars.map((bar) => `${bar.name} ${bar.display}`).join(', ')}`}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={bars} margin={{ top: labelPosition === 'top' ? 22 : 8, right: 8, bottom: 0, left: rotate ? 40 : 8 }} barCategoryGap={bars.length > 10 ? '18%' : '28%'}>
          <defs>
            <pattern id="bars-router" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
              <rect width="6" height="6" className={styles.routerFill} />
              <line x1="0" y1="0" x2="0" y2="6" className={styles.routerHatch} />
            </pattern>
          </defs>
          <CartesianGrid vertical={false} strokeDasharray="2 4" className={styles.rechartsGrid} />
          <XAxis dataKey="name" interval={0} axisLine={false} tickLine={false} height={rotate ? 118 : 56}
            tick={(props: object) => <NameTick {...(props as TickProps)} bars={bars} rotate={rotate} />} />
          <YAxis hide domain={domain ?? [0, max * (labelPosition === 'top' ? 1.08 : 1.02)]} />
          <Tooltip content={<BarTooltip />} cursor={{ className: styles.rechartsCursor }} isAnimationActive={false} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} isAnimationActive={false} maxBarSize={56}>
            {bars.map((bar) => <Cell key={bar.id} fill={fillFor(bar)} />)}
            <LabelList dataKey="display" content={(props: object) => <ValueLabel {...(props as LabelProps)} inside={labelPosition === 'inside'} />} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
