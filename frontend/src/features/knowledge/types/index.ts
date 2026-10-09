export type KnowledgeDocument = {
  id: string
  filename: string
  tags: string[]
  chunk_count: number
  uploaded_at: string
  char_count: number
}

export type KnowledgePathResponse = {
  configured_path: string
  resolved_path: string
  is_custom: boolean
  is_accessible: boolean
  ok?: boolean
}

export type KnowledgeIntegrityResponse = {
  ok: boolean
  details: string[]
  db_path: string
}

export type KnowledgeRebuildResponse = {
  ok: boolean
  chunks_reindexed: number
}

export type KnowledgeExportResponse = {
  ok: boolean
  manifest_path: string
  chunks_path: string
}
