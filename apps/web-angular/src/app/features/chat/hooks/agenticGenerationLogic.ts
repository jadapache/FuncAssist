/**
 * Pure logic extracted (mechanically, behaviour unchanged) from React `useAgenticGeneration.ts`:
 * intent resolution, artifact extraction/merging, assistant bubble text and error classification.
 * `AgenticGenerationService` orchestrates these functions and owns all side effects.
 */
import type { AgenticPromptResponse } from '../../../api/client'
import type { Artifact } from '../../../types/artifacts'
import {
  generateArtifactSubtitle,
  parseMultipleArtifacts,
  parseStreamForChatAndArtifacts,
  type ExtractedArtifact,
} from '../../../utils/artifactSplitter'

export interface AgenticGenerationConfig {
  slug?: string
  title?: string
  subtitle?: string
  uploadTags?: string
  placeholder?: string
  docxTitle?: string
  defaultExtension?: 'docx' | 'xlsx' | 'txt'
}

export type AgenticErrorCategory = 'auth' | 'rate_limit' | 'context' | 'gpu' | 'general'

export interface IntentResolution {
  commandSlug: string | null
  cleanQuery: string
  targetFeature: string
  targetMode: string
  initialStatus: string
  isChatOnly: boolean
}

/** `HH:MM` timestamp exactly as the React hook formatted it. */
export function formatNowTime(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** Title used for documents when the backend/LLM does not provide one. */
export function resolveDocTitle(config?: AgenticGenerationConfig): string {
  return config?.docxTitle || config?.title || 'Documento'
}

export function resolveIntentAndStatus(
  queryText: string,
  defaultFeature: string,
  templateId?: string | null,
): IntentResolution {
  const pLower = queryText.toLowerCase()
  const isQuestion =
    pLower.startsWith('¿') ||
    pLower.startsWith('que ') ||
    pLower.startsWith('qué ') ||
    pLower.startsWith('como ') ||
    pLower.startsWith('cómo ') ||
    pLower.startsWith('cual ') ||
    pLower.startsWith('cuál ') ||
    pLower.startsWith('por que') ||
    pLower.startsWith('por qué') ||
    pLower.startsWith('explica') ||
    pLower.includes('?')

  const commandMatch = queryText.match(/^\/([a-zA-Z0-9_-]+)(?:\s+(.*))?$/s)
  const commandSlug = commandMatch ? commandMatch[1].toLowerCase() : null
  const cleanQuery = commandMatch && commandMatch[2] ? commandMatch[2].trim() : queryText

  if (commandSlug) {
    if (commandSlug === 'plan') {
      return {
        commandSlug,
        cleanQuery,
        targetFeature: 'generic_plan',
        targetMode: 'plan',
        initialStatus: 'Generando plan...',
        isChatOnly: false,
      }
    }
    if (commandSlug === 'informe' || commandSlug === 'report') {
      return {
        commandSlug,
        cleanQuery,
        targetFeature: 'generic_report',
        targetMode: 'report',
        initialStatus: 'Elaborando informe...',
        isChatOnly: false,
      }
    }
    if (commandSlug === 'plantilla') {
      return {
        commandSlug,
        cleanQuery,
        targetFeature: defaultFeature,
        targetMode: 'template',
        initialStatus: 'Estructurando documento...',
        isChatOnly: false,
      }
    }
    return {
      commandSlug,
      cleanQuery,
      targetFeature: commandSlug,
      targetMode: commandSlug,
      initialStatus: `Ejecutando /${commandSlug}...`,
      isChatOnly: false,
    }
  }

  if (isQuestion) {
    return {
      commandSlug: null,
      cleanQuery,
      targetFeature: defaultFeature,
      targetMode: 'chat',
      initialStatus: 'Pensando...',
      isChatOnly: true,
    }
  }

  if (templateId && templateId.trim()) {
    return {
      commandSlug: 'plantilla',
      cleanQuery,
      targetFeature: defaultFeature,
      targetMode: 'template',
      initialStatus: 'Estructurando documento corporativo...',
      isChatOnly: false,
    }
  }

  if (pLower.includes('plan de') || pLower.includes('genera un plan') || pLower.includes('crea un plan')) {
    return {
      commandSlug: 'plan',
      cleanQuery,
      targetFeature: 'generic_plan',
      targetMode: 'plan',
      initialStatus: 'Generando plan...',
      isChatOnly: false,
    }
  }

  if (pLower.includes('informe') || pLower.includes('reporte') || pLower.includes('resumen ejecutivo')) {
    return {
      commandSlug: 'informe',
      cleanQuery,
      targetFeature: 'generic_report',
      targetMode: 'report',
      initialStatus: 'Elaborando informe...',
      isChatOnly: false,
    }
  }

  const isDocumentGeneration = [
    'completa la plantilla',
    'llena la plantilla',
    'genera el documento',
    'generar documento',
    'crear documento',
    'crea el documento',
    'generar artefacto',
    'genera el artefacto',
    'genera artefacto',
    'crear artefacto',
    'crea el artefacto',
    'redacta el documento',
    'elabora el documento',
    'regenera',
  ].some((kw) => pLower.includes(kw))

  if (isDocumentGeneration) {
    return {
      commandSlug: 'plantilla',
      cleanQuery,
      targetFeature: defaultFeature,
      targetMode: 'template',
      initialStatus: 'Estructurando documento...',
      isChatOnly: false,
    }
  }

  return {
    commandSlug: null,
    cleanQuery,
    targetFeature: defaultFeature,
    targetMode: 'auto',
    initialStatus: 'Pensando...',
    isChatOnly: false,
  }
}

export function resolveAssistantBubbleText(
  resMsg: string | undefined,
  finalContent: string,
  targetMode: string,
  detectedIntent: string,
  docTitle: string,
): string {
  if (resMsg && !resMsg.includes('<artifact') && resMsg !== finalContent) {
    return resMsg.replace(/<\/?chat>/gi, '').trim()
  }

  const parsed = parseStreamForChatAndArtifacts(finalContent, docTitle)
  if (parsed.chatText && !parsed.chatText.includes('<artifact') && parsed.chatText !== finalContent) {
    return parsed.chatText
  }

  if (targetMode === 'plan' || detectedIntent === 'generic_plan') {
    return 'He elaborado el plan solicitado. Puedes revisarlo, editarlo y descargarlo en el panel de Artefactos.'
  }
  if (targetMode === 'report' || detectedIntent === 'generic_report') {
    return 'He estructurado el informe solicitado con las evidencias y hallazgos. Puedes consultarlo en el panel de Artefactos.'
  }
  return 'He generado el documento correspondiente en el panel de artefactos.'
}

/** Status text shown when the backend reports the detected intent mid-stream. */
export function resolveIntentStatus(intent: string): string {
  if (intent === 'generic_plan') return 'Generando plan...'
  if (intent === 'generic_report') return 'Elaborando informe...'
  if (intent === 'template_mutation') return 'Mutando plantilla...'
  return 'Pensando...'
}

/**
 * Merge the artifacts detected in the live stream with the ones already stored in the conversation
 * (matched by case-insensitive title so ids stay stable while streaming).
 */
export function mergeStreamingArtifacts(streamed: ExtractedArtifact[], baseList: Artifact[]): Artifact[] {
  const nowFormatted = formatNowTime()
  return streamed.map((item, idx) => {
    const existing = baseList.find((a) => a.title.toLowerCase() === item.title.toLowerCase())
    return {
      id: existing ? existing.id : `art-stream-${idx}`,
      title: item.title,
      subtitle: generateArtifactSubtitle(item.content) || `Artefacto #${idx + 1} - Generado por IA`,
      extension: item.extension,
      content: item.content,
      createdAt: existing?.createdAt || nowFormatted,
      updatedAt: 'Generando...',
    }
  })
}

/** Final artifact extraction: backend-provided artifacts win, otherwise parse the generated text. */
export function extractFinalArtifacts(
  backendArtifacts: AgenticPromptResponse['artifacts'],
  finalContent: string,
  config: AgenticGenerationConfig | undefined,
  templateContent: string,
  isDocumentTarget: boolean,
): ExtractedArtifact[] {
  return backendArtifacts && backendArtifacts.length > 0
    ? backendArtifacts.map((a) => ({
        title: a.title,
        extension: (a.extension as 'docx' | 'xlsx' | 'txt') || config?.defaultExtension || 'docx',
        content: a.content,
      }))
    : parseMultipleArtifacts(
        finalContent,
        resolveDocTitle(config),
        config?.defaultExtension || 'docx',
        templateContent,
        isDocumentTarget,
      )
}

export interface ArtifactReconciliation {
  updatedArtifacts: Artifact[]
  targetArtifactId: string | null
  /** Artifact that must become active (React called `onSetActiveArtifactId` before resetting history). */
  activateArtifactId: string | null
  /** Content the document history must be reset to. */
  historyResetContent: string
}

/**
 * Decide how the generated artifacts land in the conversation:
 * - several artifacts → appended as new items;
 * - an artifact already exists → its content is replaced (no duplicates);
 * - first generation → a single new artifact is created.
 */
export function reconcileGeneratedArtifacts(params: {
  extractedArtifacts: ExtractedArtifact[]
  convArtifacts: Artifact[]
  activeArtifact: Artifact | null
  finalContent: string
  resolution: IntentResolution
  config?: AgenticGenerationConfig
}): ArtifactReconciliation {
  const { extractedArtifacts, convArtifacts, activeArtifact, finalContent, resolution, config } = params

  if (extractedArtifacts.length > 1) {
    const nowFormatted = formatNowTime()
    const newCreatedItems: Artifact[] = extractedArtifacts.map((extracted, idx) => ({
      id: crypto.randomUUID(),
      title: extracted.title,
      subtitle: generateArtifactSubtitle(extracted.content) || `Artefacto #${idx + 1} - Generado por IA`,
      extension: extracted.extension,
      content: extracted.content,
      createdAt: nowFormatted,
      updatedAt: 'Hace un momento',
    }))

    return {
      updatedArtifacts: [...convArtifacts, ...newCreatedItems],
      targetArtifactId: newCreatedItems[0].id,
      activateArtifactId: newCreatedItems[0].id,
      historyResetContent: newCreatedItems[0].content,
    }
  }

  if (activeArtifact || convArtifacts.length > 0) {
    // Si ya existe un artefacto activo en la sesión, actualizamos su contenido en lugar de duplicarlo
    const targetId = activeArtifact?.id || convArtifacts[0]?.id
    const newContent = extractedArtifacts[0]?.content || finalContent
    const newTitle = extractedArtifacts[0]?.title || activeArtifact?.title || resolveDocTitle(config)
    const newExt = extractedArtifacts[0]?.extension || activeArtifact?.extension || config?.defaultExtension || 'docx'

    return {
      updatedArtifacts: convArtifacts.map((a) =>
        a.id === targetId
          ? {
              ...a,
              title: newTitle,
              extension: newExt,
              content: newContent,
              subtitle: generateArtifactSubtitle(newContent),
              updatedAt: 'Hace un momento',
            }
          : a,
      ),
      targetArtifactId: targetId ?? null,
      activateArtifactId: null,
      historyResetContent: newContent,
    }
  }

  // Primera generación: se crea el artefacto inicial
  const newArtId = crypto.randomUUID()
  const artifactTitle =
    extractedArtifacts[0]?.title ||
    (resolution.commandSlug
      ? `${resolution.commandSlug.toUpperCase()}: ${resolution.cleanQuery.slice(0, 30)}`
      : resolveDocTitle(config))

  const newContent = extractedArtifacts[0]?.content || finalContent
  const newArtifact: Artifact = {
    id: newArtId,
    title: artifactTitle,
    subtitle: generateArtifactSubtitle(newContent) || 'Documento generado por IA',
    extension: extractedArtifacts[0]?.extension || config?.defaultExtension || 'docx',
    content: newContent,
    createdAt: formatNowTime(),
    updatedAt: 'Hace un momento',
  }
  return {
    updatedArtifacts: [newArtifact],
    targetArtifactId: newArtId,
    activateArtifactId: newArtId,
    historyResetContent: newArtifact.content,
  }
}

export interface ClassifiedAgenticError {
  displayMsg: string
  isAuthError: boolean
  errorCategory: AgenticErrorCategory
}

/** Map a raw pipeline error to the user-facing message/category (same regexes and copy as React). */
export function classifyAgenticError(err: unknown): ClassifiedAgenticError {
  const errMsg = err instanceof Error ? err.message : String(err || 'Error desconocido')

  const isGpuError =
    /device\s*(was\s*)?lost|gpu|dxgi|device_hung|0x887a0006|already\s*been\s*disposed|insufficient\s*memory|vram|memoria.*gr[aá]fica/i.test(
      errMsg,
    )

  const isAuthError =
    /api\s*key|autenticaci[oó]n|authentication|unauthorized|401|forbidden|403|invalid_api_key/i.test(errMsg)

  const isRateLimitError =
    /reduce max_tokens|RateLimitError/i.test(errMsg) && !/OTPM|tokens de salida por minuto/i.test(errMsg)

  const isContextMissingError =
    /not found in connected sources|no matching chunks|no documents uploaded|sin coincidencias en el contexto|no se encontr[oó] informaci[oó]n/i.test(
      errMsg,
    )

  let errorCategory: AgenticErrorCategory = 'general'
  if (isGpuError) errorCategory = 'gpu'
  else if (isAuthError) errorCategory = 'auth'
  else if (isRateLimitError) errorCategory = 'rate_limit'
  else if (isContextMissingError) errorCategory = 'context'

  let displayMsg = errMsg
  if (isGpuError) {
    displayMsg =
      'La GPU se quedó sin memoria (VRAM) o se desconectó al ejecutar el modelo en el navegador. Te recomendamos seleccionar un modelo más ligero (ej. Llama 3.2 1B) en Configuración o utilizar un proveedor externo (Ollama o API en la nube).'
  } else if (isAuthError) {
    displayMsg = 'Error: La API key guardada no es válida. Por favor actualízala en Configuración.'
  } else if (isRateLimitError) {
    displayMsg = 'La solicitud supera el límite de tokens de salida para este modelo.'
  } else if (isContextMissingError) {
    displayMsg = 'No se encontró contexto suficiente en las fuentes para procesar la consulta.'
  } else if (!displayMsg || displayMsg === 'Error desconocido') {
    displayMsg = 'Ocurrió un error inesperado al procesar la solicitud. Por favor intenta nuevamente.'
  }

  return { displayMsg, isAuthError, errorCategory }
}
