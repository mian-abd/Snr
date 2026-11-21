import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import styles from './charts.module.css'

/** One model in a grouped bar chart: its name and its data color. */
export type CompareSeries = { id: string; name: string; color: string }
/** One group of bars (a task): a value per series, in series order. */
export type CompareGroup = { id: string; label: string; values: Array<number | null> }

type Row = { label: string } & Record<string, number | string | null>

type TooltipProps = { active?: boolean; label?: string; payload?: Array<{ dataKey?: string | number; value?: number | null }> }

function GroupTooltip({ active, label, payload, series, format }: TooltipProps & { series: CompareSeries[]; format: (value: number) => string }) {
  if (!active || !payload?.length) return null
  return (
    <div className={styles.tooltipBox}>
      <strong>{label}</strong>
      {series.map((item) => {
        const value = payload.find((entry) => entry.dataKey === item.id)?.value
        return (
          <span key={item.id} style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <i className={`${styles.swatch} ${styles.swatchSquare}`} style={{ background: item.color }} aria-hidden="true" />
            <span style={{ flex: 1 }}>{item.name}</span>
            <span className={styles.tooltipValue}>{value == null ? '—' : format(value)}</span>
          </span>
        )
      })}
    </div>
  )
}

type LabelProps = { x?: number | string; y?: number | string; width?: number | string; value?: number | string | null }

/**
 * Bars grouped by task, one per model in its maker's color, the value above each bar when
 * there is room for it. The legend (logos and names) is the caller's, above the chart.
 */
export function CompareBars({ series, groups, label, format, height = 300 }: {
  series: CompareSeries[]
  groups: CompareGroup[]
  label: string
  format: (value: number) => string
  height?: number
}) {
  const data: Row[] = groups.map((group) => ({ label: group.label, ...Object.fromEntries(series.map((item, index) => [item.id, group.values[index] ?? null])) }))
  const max = Math.max(0, ...groups.flatMap((group) => group.values.filter((value): value is number => value != null)))
  const summary = groups.map((group) => `${group.label}: ${series.map((item, index) => `${item.name} ${group.values[index] == null ? 'not measured' : format(group.values[index]!)}`).join(', ')}`).join('; ')
  return (
    <div className={styles.barsFrame} role="img" aria-label={`${label}. ${summary}`}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 24, right: 4, bottom: 0, left: 4 }} barCategoryGap={series.length > 2 ? '16%' : '26%'} barGap={3}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" className={styles.rechartsGrid} />
          <XAxis dataKey="label" axisLine={false} tickLine={false} interval={0} tick={{ className: styles.barName }} height={34} />
          <YAxis hide domain={[0, Math.max(max, 1e-9) * 1.06]} />
          <Tooltip content={<GroupTooltip series={series} format={format} />} cursor={{ className: styles.rechartsCursor }} isAnimationActive={false} />
          {series.map((item) => (
            <Bar key={item.id} dataKey={item.id} name={item.name} fill={item.color} radius={[4, 4, 0, 0]} maxBarSize={48} isAnimationActive={false}>
              <LabelList
                dataKey={item.id}
                content={(props: object) => {
                  const { x = 0, y = 0, width = 0, value } = props as LabelProps
                  if (value == null || Number(width) < 26) return null
                  return <text x={Number(x) + Number(width) / 2} y={Number(y) - 7} textAnchor="middle" className={styles.barValueTop}>{format(Number(value))}</text>
                }}
              />
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
