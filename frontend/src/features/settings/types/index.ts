import type { Cpu } from 'lucide-react'

export type TabType = 'ai_models' | 'templates' | 'integrations' | 'knowledge'

export type BuiltInModel = {
  id: string
  name: string
  tag: string
  description: string
  size: string
  tokens: string
}

export type RecommendedModel = {
  id: string
  name: string
}

export type CloudProvider = {
  id: string
  name: string
  recommendedModels?: RecommendedModel[]
}

export type SettingsTabItem = {
  id: TabType
  label: string
  subtitle: string
  icon: typeof Cpu
  badgeCount?: number
}
