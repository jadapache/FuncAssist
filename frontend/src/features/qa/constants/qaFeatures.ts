import type { LucideIcon } from 'lucide-react'
import { ClipboardCheck, Database, Eye, Rocket, TestTube2 } from 'lucide-react'

export type QaFeatureConfig = {
  slug: string
  feature: string
  title: string
  description: string
  uploadTags: string
  placeholder: string
  defaultQuery: string
  defaultSources: string[]
  icon: LucideIcon
}

export const QA_SOURCE_OPTIONS = [
  { id: 'jira', label: 'Jira' },
  { id: 'github', label: 'GitHub' },
  { id: 'gitlab', label: 'GitLab' },
  { id: 'knowledge', label: 'Biblioteca de Conocimiento' },
]

export const QA_FEATURES: QaFeatureConfig[] = [
  {
    slug: 'regression',
    feature: 'regression',
    title: 'Regresión',
    description: 'Sube planes de prueba, notas de versión o especificaciones. Obtén contexto de Jira/GitHub/GitLab para enfocar el alcance de pruebas de regresión.',
    uploadTags: 'qa,regression,test-plan',
    placeholder: '¿Qué cambió en la versión v2.4? ¿Qué flujos necesitan regresión?',
    defaultQuery: 'Sugerir un alcance de pruebas de regresión a partir de los archivos cargados y fuentes conectadas.',
    defaultSources: ['jira', 'github', 'gitlab', 'knowledge'],
    icon: TestTube2,
  },
  {
    slug: 'api-qa',
    feature: 'api_qa',
    title: 'QA de API',
    description: 'Sube especificaciones OpenAPI, colecciones de Postman o docs de API. Identifica brechas de cobertura y casos límite a probar.',
    uploadTags: 'qa,api,openapi',
    placeholder: 'Revisa la API de pago para identificar pruebas negativas faltantes.',
    defaultQuery: 'Analizar brechas de cobertura en pruebas de API según las especificaciones cargadas.',
    defaultSources: ['knowledge', 'github', 'gitlab'],
    icon: ClipboardCheck,
  },
  {
    slug: 'visual-qa',
    feature: 'visual_qa',
    title: 'QA Visual',
    description: 'Sube especificaciones de interfaz, diseños o criterios de aceptación. Genera una lista de verificación de QA visual fundamentada en tus documentos.',
    uploadTags: 'qa,visual,ui-spec',
    placeholder: 'Construir una lista de verificación visual para el nuevo panel de control.',
    defaultQuery: 'Crear una lista de verificación de QA visual a partir de las especificaciones de interfaz cargadas.',
    defaultSources: ['knowledge', 'jira'],
    icon: Eye,
  },
  {
    slug: 'smart-test-data',
    feature: 'smart_test_data',
    title: 'Datos de Prueba Inteligentes',
    description: 'Sube esquemas, especificaciones de formularios o reglas de negocio. Genera escenarios y datos de prueba realistas.',
    uploadTags: 'qa,test-data,schema',
    placeholder: 'Generar datos de prueba para casos límite en el formulario de registro.',
    defaultQuery: 'Sugerir escenarios con datos de prueba inteligentes basados en los esquemas cargados.',
    defaultSources: ['knowledge'],
    icon: Database,
  },
  {
    slug: 'release-readiness',
    feature: 'release_readiness',
    title: 'Estado de Lanzamiento',
    description: 'Sube notas de lanzamiento y listas de verificación. Consolida Jira, GitHub y GitLab para evaluar la viabilidad de despliegue.',
    uploadTags: 'qa,release,checklist',
    placeholder: '¿Estamos listos para desplegar la versión v2.4? ¿Qué bloqueos persisten?',
    defaultQuery: 'Evaluar el estado de lanzamiento a partir de los documentos cargados y fuentes en vivo.',
    defaultSources: ['jira', 'github', 'gitlab', 'knowledge'],
    icon: Rocket,
  },
]

export const QA_FEATURE_BY_SLUG = Object.fromEntries(QA_FEATURES.map((item) => [item.slug, item])) as Record<
  string,
  QaFeatureConfig
>

