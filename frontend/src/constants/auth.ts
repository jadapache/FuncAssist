export const PASSWORD_REGEX = /^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,}$/
export const EMAIL_REGEX = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/

export const roleOptions = [
  {
    value: 'funcional',
    label: 'Analista Funcional',
    description: 'Generación de mejoras funcionales, procesamiento de transcripciones y requerimientos',
  },
  {
    value: 'pm',
    label: 'Director de Proyecto',
    description: 'Gestión de proyectos, standups diarios, revisión de PRDs e impacto',
  },
  {
    value: 'qa',
    label: 'Tester',
    description: 'Pruebas de integración, pruebas de regresión, planes de testeo, casos de prueba, etc.',
  },
] as const

export type SelectableRole = (typeof roleOptions)[number]['value']
