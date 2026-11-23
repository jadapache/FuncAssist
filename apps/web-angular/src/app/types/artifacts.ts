/**
 * Tipos compartidos para artefactos de documentos generados por IA.
 */

export type ArtifactExtension = 'docx' | 'xlsx' | 'txt'

export interface Artifact {
  id: string
  title: string
  subtitle?: string
  extension: ArtifactExtension
  content: string
  createdAt: string
  updatedAt: string
}
