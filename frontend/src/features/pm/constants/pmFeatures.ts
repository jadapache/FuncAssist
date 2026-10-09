import type { LucideIcon } from 'lucide-react'
import { FileSearch, GitCompareArrows } from 'lucide-react'
import { api, type FeaturePayload } from '../../../api/client'

export type PmFeatureConfig = {
  slug: string
  title: string
  description: string
  uploadTags: string
  placeholder: string
  defaultQuery: string
  showSourceToggles?: boolean
  sourceOptions?: Array<{ id: string; label: string }>
  defaultSources?: string[]
  icon: LucideIcon
  runApi: (payload: FeaturePayload) => Promise<any>
}

export const PM_SOURCE_OPTIONS = [
  { id: 'jira', label: 'Jira' },
  { id: 'github', label: 'GitHub' },
  { id: 'gitlab', label: 'GitLab' },
  { id: 'knowledge', label: 'Biblioteca de Conocimiento' },
]

export const PM_FEATURES: PmFeatureConfig[] = [
  {
    slug: 'prd-checker',
    title: 'Revisor de PRD',
    description: 'Sube uno o más documentos de requerimientos (PRD) o especificaciones para evaluarlos. Analiza claridad, vacíos y riesgos basándose estrictamente en el contenido.',
    uploadTags: 'prd,prd_checker',
    placeholder: 'Evalúa este PRD según la rúbrica de criterios de aceptación. Enfócate en casos límite.',
    defaultQuery: 'Revisar los documentos de PRD cargados con respecto a la rúbrica de evaluación.',
    icon: FileSearch,
    runApi: (payload) => api.runPrdChecker(payload),
  },
  {
    slug: 'change-impact',
    title: 'Impacto de Cambios',
    description: 'Describe un cambio propuesto, sube especificaciones o tickets relacionados y consolida datos en vivo de Jira, GitHub o GitLab para evaluar el impacto.',
    uploadTags: 'change_impact,spec',
    placeholder: 'Vamos a eliminar el proceso de compra como invitado. ¿Qué tickets, PRs y documentos se ven afectados?',
    defaultQuery: 'Analizar el impacto de cambio basándose en los archivos cargados y fuentes conectadas.',
    showSourceToggles: true,
    sourceOptions: PM_SOURCE_OPTIONS,
    defaultSources: ['jira', 'github', 'knowledge'],
    icon: GitCompareArrows,
    runApi: (payload) => api.runChangeImpact(payload),
  },
]

export const PM_FEATURE_BY_SLUG = Object.fromEntries(PM_FEATURES.map((item) => [item.slug, item])) as Record<
  string,
  PmFeatureConfig
>
