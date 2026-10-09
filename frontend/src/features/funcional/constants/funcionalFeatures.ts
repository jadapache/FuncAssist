import type { LucideIcon } from 'lucide-react'
import { FileEdit, FileText, List } from 'lucide-react'
import { api, type FeaturePayload } from '../../../api/client'

export type FuncionalFeatureConfig = {
  slug: string
  title: string
  subtitle: string
  uploadTags: string
  placeholder: string
  defaultQuery: string
  defaultTemplate: string
  defaultSources?: string[]
  icon: LucideIcon
  runApi: (payload: FeaturePayload) => Promise<any>
  exportFilenamePrefix?: string
  docxTitle?: string
  defaultExtension?: 'docx' | 'xlsx' | 'txt'
}

export const FUNCIONAL_SOURCE_OPTIONS = [
  { id: 'knowledge', label: 'Biblioteca' },
  { id: 'jira', label: 'Jira' },
  { id: 'github', label: 'GitHub' },
]

export const FUNCIONAL_FEATURES: FuncionalFeatureConfig[] = [
  {
    slug: 'mejoras',
    title: 'Generador de Documento de Mejoras',
    subtitle: 'Sube especificaciones o minutas y genera/mantiene el documento funcional corporativo en tiempo real.',
    uploadTags: 'mejoras_doc',
    placeholder: 'Escribe tu petición o consulta...',
    defaultQuery: 'Genera el Documento de Mejora detallado basado en la información recopilada.',
    defaultTemplate: `# Documento de Mejora y Requerimientos Funcionales

## 1. Información General del Proyecto
- **Proyecto / Módulo:** Sistema de Gestión QA / Módulo Funcional
- **Fecha:** {{FECHA}}
- **Responsables:** {{RESPONSABLES}}

## 2. Diagnóstico y Situación Actual
{{SITUACIÓN_ACTUAL}}

## 3. Propuesta de Solución y Mejoras Requeridas
{{SOLUCIÓN}}

## 4. Matriz de Requerimientos Funcionales
| ID | Requerimiento | Prioridad | Impacto en Negocio |
|---|---|---|---|
| RF-01 | Automatización de flujo funcional | Alta | Reducción de tiempos manuales |

## 5. Recomendaciones de Pruebas y Criterios de Aceptación
- Cobertura de pruebas unitarias e integración.
- Validación de rendimiento e impacto en la arquitectura.`,
    defaultSources: ['knowledge'],
    icon: FileEdit,
    runApi: (payload) => api.runMejoras(payload),
    exportFilenamePrefix: 'Documento_de_Mejora',
    docxTitle: 'Documento de Mejora y Requerimientos Funcionales',
  },
  {
    slug: 'inventario',
    title: 'Inventario de Requerimientos y Contexto',
    subtitle: 'Consolida la visión inicial, stakeholders, objetivos SMART, alcance preliminar y catálogo de requerimientos.',
    uploadTags: 'inventario_doc',
    placeholder: 'Indica el proyecto o especifica los objetivos y alcance a consolidar...',
    defaultQuery: 'Genera el Inventario de Requerimientos y Contexto del Proyecto estructurado según el estándar corporativo.',
    defaultTemplate: `# Inventario de Requerimientos y Contexto de Proyecto

## 1. Información General del Proyecto
- **Proyecto / Módulo:** [Nombre del Proyecto]
- **Fecha:** {{FECHA}}
- **Facilitador / Autor:** {{AUTOR}}
- **Participantes y Stakeholders:** {{PARTICIPANTES}}

## 2. Contexto, Antecedentes y Justificación
### 2.1 Situación Actual
[Diagnóstico de la situación previa y procesos actuales]

### 2.2 Problemática Identificada
[Puntos de dolor, ineficiencias o brechas detectadas]

### 2.3 Justificación y Valor de Negocio
[Beneficios esperados, retorno y motivación del proyecto]

## 3. Matriz de Stakeholders
| Rol | Nombre / Área | Interés Principal | Nivel de Influencia |
|---|---|---|---|
| Sponsor | Dirección de TI | Gobernanza y resultados | Alto |
| Usuario Líder | Operaciones | Eficiencia en tiempos | Alto |

## 4. Objetivos del Proyecto
### 4.1 Objetivo General
[Objetivo principal en formato SMART]

### 4.2 Objetivos Específicos
- Objetivo 1
- Objetivo 2

## 5. Alcance Preliminar
### 5.1 Dentro del Alcance (In Scope)
- [Módulos y funcionalidades cubiertos]

### 5.2 Fuera del Alcance (Out of Scope)
- [Funcionalidades expresamente excluidas]

## 6. Catálogo de Requerimientos Iniciales (Alto Nivel)
| ID | Requerimiento | Tipo | Prioridad | Módulo Relacionado | Fuente |
|---|---|---|---|---|---|
| INV-001 | Gestión de auditoría continua | Funcional | Alta | QA Core | [1] |

## 7. Riesgos y Supuestos Iniciales
| Riesgo / Supuesto | Impacto | Probabilidad | Estrategia de Mitigación |
|---|---|---|---|
| Retraso en integración API | Alto | Media | Definir contratos tempranos |

## 8. Próximos Pasos
- [ ] Realizar levantamiento detallado de historias de usuario y casos de uso
- [ ] Validar matriz de alcance con los stakeholders`,
    defaultSources: ['knowledge'],
    icon: FileText,
    runApi: (payload) => api.inventarioDoc(payload),
    exportFilenamePrefix: 'Inventario_Requerimientos',
    docxTitle: 'Inventario de Requerimientos y Contexto de Proyecto',
    defaultExtension: 'xlsx',
  },
  {
    slug: 'levantamiento',
    title: 'Levantamiento Detallado de Requerimientos',
    subtitle: 'Especificación funcional rigurosa con criterios de aceptación (Given-When-Then), User Stories, Casos de Uso y Matriz de Trazabilidad.',
    uploadTags: 'levantamiento_doc',
    placeholder: 'Indica los casos de uso, historias o requerimientos detallados que deseas estructurar...',
    defaultQuery: 'Genera el Levantamiento Detallado de Requerimientos Funcionales, Historias de Usuario y Casos de Uso.',
    defaultTemplate: `# Levantamiento Detallado de Requerimientos y Especificación Funcional

## 1. Ficha Técnica del Documento
- **Proyecto:** [Nombre del Proyecto]
- **Versión:** 1.0
- **Fecha:** {{FECHA}}
- **Analista Funcional:** {{ANALISTA}}
- **Documento Base:** Inventario de Requerimientos

## 2. Especificación de Requerimientos Funcionales Detallados
### RF-001: [Nombre del Requerimiento]
- **Descripción:** [Descripción técnica y funcional detallada]
- **Prioridad:** Alta | Media | Baja
- **Complejidad:** Alta | Media | Baja
- **Módulo:** [Módulo afectado]
- **Criterios de Aceptación:**
  - [ ] Criterio de validación 1
  - [ ] Criterio de validación 2
- **Dependencias:** Ninguna

## 3. Historias de Usuario (User Stories)
### HU-001: [Título de la Historia]
**Como** [rol/usuario]  
**Quiero** [funcionalidad]  
**Para** [beneficio o valor]  

**Criterios de Aceptación:**
- [ ] Dado que... Cuando... Entonces...

## 4. Casos de Uso del Sistema
### CU-001: [Nombre del Caso de Uso]
- **Actor Principal:** [Usuario]
- **Precondiciones:** [Estado necesario antes de iniciar]
- **Flujo Principal:**
  1. El usuario solicita la operación X
  2. El sistema valida los permisos y procesa Y
  3. El sistema confirma con resultado Z
- **Flujos Alternativos:**
  - 2a. Si la validación falla, el sistema muestra advertencia E
- **Postcondiciones:** [Estado del sistema tras la ejecución]

## 5. Reglas de Negocio
| ID | Regla | Descripción | Tipo de Validación |
|---|---|---|---|
| RN-001 | Validación de sesión | Tiempo de inactividad máximo de 15 min | Seguridad |

## 6. Requerimientos No Funcionales (RNF)
| ID | Categoría | Requerimiento No Funcional | Métrica / Criterio |
|---|---|---|---|
| RNF-001 | Rendimiento | Tiempo de respuesta en consultas | < 500 ms p95 |

## 7. Matriz de Trazabilidad
| Objetivo | Requerimiento Funcional | Historia de Usuario | Caso de Uso | Estado |
|---|---|---|---|---|
| OBJ-01 | RF-001 | HU-001 | CU-001 | Aprobado |`,
    defaultSources: ['knowledge'],
    icon: List,
    runApi: (payload) => api.levantamientoDoc(payload),
    exportFilenamePrefix: 'Levantamiento_Requerimientos',
    docxTitle: 'Levantamiento Detallado de Requerimientos y Especificación Funcional',
  },
]

export const FUNCIONAL_FEATURE_BY_SLUG = Object.fromEntries(
  FUNCIONAL_FEATURES.map((item) => [item.slug, item])
) as Record<string, FuncionalFeatureConfig>
