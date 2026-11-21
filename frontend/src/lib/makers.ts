import deepseek from '../assets/makers/deepseek-color.svg'
import gemini from '../assets/makers/gemini-color.svg'
import gemma from '../assets/makers/gemma-color.svg'
import grok from '../assets/makers/grok.svg'
import inception from '../assets/makers/inception.svg'
import kimi from '../assets/makers/kimi-color.svg'
import meta from '../assets/makers/meta-color.svg'
import mistral from '../assets/makers/mistral-color.svg'
import nvidia from '../assets/makers/nvidia-color.svg'
import ollama from '../assets/makers/ollama.svg'
import openai from '../assets/makers/openai.svg'
import qwen from '../assets/makers/qwen-color.svg'
import ernie from '../assets/makers/wenxin-color.svg'
import mimo from '../assets/makers/xiaomimimo.svg'

/** Who made a model: the name, the data color its marks wear, and its logo. */
export type Maker = { id: string; name: string; color: string; logo: string | null; mono: boolean }

const makers = {
  google: { name: 'Google', color: 'var(--maker-google)' },
  openai: { name: 'OpenAI', color: 'var(--maker-openai)' },
  deepseek: { name: 'DeepSeek', color: 'var(--maker-deepseek)' },
  meta: { name: 'Meta', color: 'var(--maker-meta)' },
  nvidia: { name: 'NVIDIA', color: 'var(--maker-nvidia)' },
  alibaba: { name: 'Alibaba', color: 'var(--maker-alibaba)' },
  xai: { name: 'xAI', color: 'var(--maker-xai)' },
  moonshot: { name: 'Moonshot AI', color: 'var(--maker-moonshot)' },
  inception: { name: 'Inception', color: 'var(--maker-inception)' },
  xiaomi: { name: 'Xiaomi', color: 'var(--maker-xiaomi)' },
  mistral: { name: 'Mistral AI', color: 'var(--maker-mistral)' },
  baidu: { name: 'Baidu', color: 'var(--maker-baidu)' },
  other: { name: 'Other', color: 'var(--maker-other)' },
} as const

type MakerId = keyof typeof makers

/** Pattern on the model ID → maker and the product logo that identifies it best. */
const rules: Array<[RegExp, MakerId, string | null, boolean]> = [
  [/gemini/i, 'google', gemini, false],
  [/gemma/i, 'google', gemma, false],
  [/gpt|openai|o\d-/i, 'openai', openai, true],
  [/deepseek/i, 'deepseek', deepseek, false],
  [/llama|muse|meta/i, 'meta', meta, false],
  [/nemotron|nvidia/i, 'nvidia', nvidia, false],
  [/qwen/i, 'alibaba', qwen, false],
  [/grok|xai/i, 'xai', grok, true],
  [/kimi|moonshot/i, 'moonshot', kimi, false],
  [/mercury|inception/i, 'inception', inception, true],
  [/mimo|xiaomi/i, 'xiaomi', mimo, true],
  [/mistral|ministral/i, 'mistral', mistral, false],
  [/ernie|baidu/i, 'baidu', ernie, false],
]

export function makerOf(modelId: string): Maker {
  const rule = rules.find(([pattern]) => pattern.test(modelId))
  const id: MakerId = rule?.[1] ?? 'other'
  return { id, ...makers[id], logo: rule?.[2] ?? null, mono: rule?.[3] ?? false }
}

/** Every maker that appears among these models, in first-seen order (for legends). */
export function makersIn(modelIds: string[]): Maker[] {
  const seen = new Map<string, Maker>()
  for (const id of modelIds) {
    const maker = makerOf(id)
    if (!seen.has(maker.id)) seen.set(maker.id, maker)
  }
  return [...seen.values()]
}

export const localLogo = ollama

/**
 * A color per model: its maker's hue, with lighter steps for a maker's second and third model,
 * so two models from one maker stay apart side by side. Pass every model ID that can appear,
 * in a fixed order, so a model keeps its color across charts.
 */
export function modelColors(modelIds: string[]): Map<string, string> {
  const seen = new Map<string, number>()
  const colors = new Map<string, string>()
  for (const id of modelIds) {
    const maker = makerOf(id)
    const step = seen.get(maker.id) ?? 0
    seen.set(maker.id, step + 1)
    const tint = [0, 42, 64][Math.min(step, 2)]
    colors.set(id, tint ? `color-mix(in srgb, ${maker.color} ${100 - tint}%, var(--surface))` : maker.color)
  }
  return colors
}
