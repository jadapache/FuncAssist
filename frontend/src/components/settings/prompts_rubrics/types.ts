export interface FeatureMeta {
  id: string
  title: string
  description: string
  category: 'workspace' | 'qa' | 'product'
}

export const FEATURE_METAS: FeatureMeta[] = [
  {
    id: 'mejoras_doc',
    title: 'Redacción y Mejoras de Documentos',
    description: 'Instrucciones del agente de redacción para propuestas de mejora funcional en formato corporativo.',
    category: 'workspace',
  },
  {
    id: 'standup',
    title: 'Asistente de Standup Diario',
    description: 'Estructuración de resúmenes diarios (Ayer, Hoy, Bloqueos, Riesgos) basados en tickets y PRs.',
    category: 'product',
  },
  {
    id: 'ask_product',
    title: 'Preguntas de Producto y QA',
    description: 'Respuestas a consultas funcionales sustentadas estrictamente en la base de conocimiento.',
    category: 'product',
  },
  {
    id: 'prd_checker',
    title: 'Auditoría de PRDs y Especificaciones',
    description: 'Revisión y análisis de completitud, riesgos y criterios de aceptación en especificaciones.',
    category: 'product',
  },
  {
    id: 'change_impact',
    title: 'Análisis de Impacto de Cambios',
    description: 'Identificación de áreas afectadas, documentación, tickets y partes interesadas por un cambio.',
    category: 'qa',
  },
  {
    id: 'regression',
    title: 'Estrategia de Pruebas de Regresión',
    description: 'Definición de alcance y flujos prioritarios de pruebas basados en historias y cambios recientes.',
    category: 'qa',
  },
  {
    id: 'api_qa',
    title: 'Cobertura y Pruebas de APIs',
    description: 'Detección de endpoints sin probar, escenarios negativos y verificaciones de autenticación.',
    category: 'qa',
  },
  {
    id: 'visual_qa',
    title: 'Checklist de QA Visual y UI',
    description: 'Pautas de verificación de estados de interfaz, accesibilidad y criterios de diseño.',
    category: 'qa',
  },
  {
    id: 'smart_test_data',
    title: 'Generación de Datos de Prueba',
    description: 'Construcción de casos válidos, límites e inválidos respetando reglas de negocio y esquemas.',
    category: 'qa',
  },
  {
    id: 'release_readiness',
    title: 'Evaluación de Salida a Producción',
    description: 'Semáforo de pase a producción verificando bloqueos abiertos, PRs pendientes y riesgos.',
    category: 'qa',
  },
  {
    id: 'transcript_summary',
    title: 'Resumen de Transcripción y Minutas',
    description: 'Generación de resumen narrativo ejecutivo y Key Insights a partir de audios transcritos.',
    category: 'workspace',
  },
  {
    id: 'inventario_doc',
    title: 'Inventario de Requerimientos',
    description: 'Plantilla y rúbrica para generación de matriz de contexto de proyecto e inventario funcional.',
    category: 'product',
  },
  {
    id: 'levantamiento_doc',
    title: 'Levantamiento Detallado de Requerimientos',
    description: 'Plantilla y rúbrica para especificación funcional detallada, historias de usuario y casos de uso.',
    category: 'product',
  },
]

export const AVAILABLE_SOURCES: { id: string; label: string }[] = [
  { id: 'knowledge', label: 'Base de Conocimiento (Archivos subidos)' },
  { id: 'jira', label: 'Jira Software' },
  { id: 'github', label: 'GitHub' },
  { id: 'gitlab', label: 'GitLab' },
]
