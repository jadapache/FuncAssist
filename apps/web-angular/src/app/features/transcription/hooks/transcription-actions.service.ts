/**
 * Angular port of React `hooks/useTranscriptionActions.ts`
 * (actions and business logic for TranscriptionStudio).
 *
 * Per-component service: `TranscriptionStudioComponent` lists it in `providers` and calls
 * {@link TranscriptionActionsService.init} with its inputs (the React hook parameters).
 * The pure helpers that React exported from this hook now live in
 * `utils/transcriptCondense.ts` and `utils/transcriptionFormatting.ts`.
 */
import { DestroyRef, Injectable, Injector, computed, effect, inject, signal, untracked, type Signal } from '@angular/core'
import { api } from '../../../api/client'
import { ToastService } from '../../../core/notifications/toast.service'
import { inferenceService } from '../../ai/services/InferenceService'
import {
  transcriptionApi,
  type SummaryTemplateItem,
  type TranscriptionProgress,
  type TranscriptionResult,
} from '../api/transcriptionApi'
import { resolveStateAction, type RefObject, type SetStateAction } from '../utils/reactCompat'
import { condenseTranscriptForBrowser } from '../utils/transcriptCondense'
import { downloadFile, formatSegmentsForPrompt, formatTimestamp } from '../utils/transcriptionFormatting'

export interface TranscriptionActionsParams {
  transcriptionId: Signal<string>
  activeProgress?: Signal<TranscriptionProgress | null | undefined>
  onRefreshData?: () => void
  initialMeetingTitle?: Signal<string | undefined>
  onRetranscribe?: Signal<((transcriptionId: string, title?: string) => Promise<void>) | undefined>
}

@Injectable()
export class TranscriptionActionsService {
  private readonly toast = inject(ToastService).toast
  private readonly injector = inject(Injector)
  private readonly destroyRef = inject(DestroyRef)

  // ---- Hook parameters ----
  private params: TranscriptionActionsParams = { transcriptionId: signal('') }
  private readonly paramsSignal = signal<TranscriptionActionsParams>(this.params)
  private readonly transcriptionId = computed(() => this.paramsSignal().transcriptionId())
  private readonly activeProgress = computed(() => this.paramsSignal().activeProgress?.() ?? null)
  private readonly initialMeetingTitle = computed(() => this.paramsSignal().initialMeetingTitle?.())
  private initialized = false

  // ---- State ----
  private readonly rawTranscriptionResult = signal<TranscriptionResult | null>(null)
  private readonly _importantSegments = signal<Set<number>>(new Set())
  private readonly _isGeneratingSummary = signal(false)
  private readonly _isSavingKB = signal(false)
  private readonly _hasCopiedTranscript = signal(false)
  private readonly _hasCopiedSummary = signal(false)
  private readonly _generateModalOpen = signal(false)
  private readonly _showTranscriptDownloadMenu = signal(false)
  private readonly _showSummaryDownloadMenu = signal(false)
  private readonly _summaryTemplates = signal<SummaryTemplateItem[]>([])
  private readonly _selectedSummaryTemplate = signal<string>('')
  private readonly _showRenameModal = signal(false)
  private readonly _speakerMap = signal<Record<string, string>>({})
  private readonly _isRetranscribing = signal(false)

  readonly importantSegments = this._importantSegments.asReadonly()
  readonly isGeneratingSummary = this._isGeneratingSummary.asReadonly()
  readonly isSavingKB = this._isSavingKB.asReadonly()
  readonly hasCopiedTranscript = this._hasCopiedTranscript.asReadonly()
  readonly hasCopiedSummary = this._hasCopiedSummary.asReadonly()
  readonly generateModalOpen = this._generateModalOpen.asReadonly()
  readonly showTranscriptDownloadMenu = this._showTranscriptDownloadMenu.asReadonly()
  readonly showSummaryDownloadMenu = this._showSummaryDownloadMenu.asReadonly()
  readonly summaryTemplates = this._summaryTemplates.asReadonly()
  readonly selectedSummaryTemplate = this._selectedSummaryTemplate.asReadonly()
  readonly showRenameModal = this._showRenameModal.asReadonly()
  readonly speakerMap = this._speakerMap.asReadonly()
  readonly isRetranscribing = this._isRetranscribing.asReadonly()

  /** Dropdown dismiss refs (filled by `DownloadMenuComponent`, like React `ref={menuRef}`). */
  readonly transcriptMenuRef: RefObject<HTMLDivElement | null> = { current: null }
  readonly summaryMenuRef: RefObject<HTMLDivElement | null> = { current: null }

  readonly meetingTitle = computed(
    () =>
      this.rawTranscriptionResult()?.metadata?.title ||
      this.activeProgress()?.title ||
      this.initialMeetingTitle() ||
      'Transcripción de Reunión',
  )

  /** Job active status */
  readonly isJobActive = computed(() => {
    const activeProgress = this.activeProgress()
    return Boolean(activeProgress && activeProgress.status !== 'complete' && activeProgress.status !== 'failed')
  })

  /** React returned `displayResult` under the name `transcriptionResult`. */
  readonly transcriptionResult = computed<TranscriptionResult | null>(() => {
    const transcriptionResult = this.rawTranscriptionResult()
    const activeProgress = this.activeProgress()
    const isJobActive = this.isJobActive()
    if (transcriptionResult) {
      if (
        isJobActive &&
        activeProgress?.live_segments &&
        activeProgress.live_segments.length > (transcriptionResult.segments?.length || 0)
      ) {
        return {
          ...transcriptionResult,
          segments: activeProgress.live_segments,
          text: activeProgress.live_text || transcriptionResult.text,
        }
      }
      return transcriptionResult
    }
    if (activeProgress && isJobActive) {
      const transcriptionId = this.transcriptionId()
      return {
        id: transcriptionId,
        media_id: activeProgress.media_id || transcriptionId,
        metadata: {
          title: activeProgress.title || this.initialMeetingTitle() || 'Transcripción',
        },
        language: 'es',
        duration_seconds: 0,
        created_at: new Date().toISOString(),
        segments: activeProgress.live_segments || [],
        text: activeProgress.live_text || '',
        summary: null,
      }
    }
    return null
  })

  private readonly summaryTemplateId = computed(() => this.rawTranscriptionResult()?.summary?.template_id)

  // ---- Summary derived data ----
  private readonly summaryData = computed(() => this.rawTranscriptionResult()?.summary)

  readonly summaryParagraphs = computed<string[]>(() => {
    const summaryData = this.summaryData()
    const summaryParagraphs: string[] = []
    if (summaryData?.summary_text) {
      summaryParagraphs.push(
        ...summaryData.summary_text
          .split('\n\n')
          .map((p) => p.trim())
          .filter(Boolean),
      )
    } else if (summaryData?.topics && summaryData.topics.length > 0) {
      summaryParagraphs.push(
        `Durante la reunión se abordaron los aspectos principales vinculados a ${summaryData.topics.join(
          ', ',
        )}. Los participantes evaluaron los requerimientos y el alcance operativo para la solución requerida.`,
      )
      if (summaryData.decisions && summaryData.decisions.length > 0) {
        summaryParagraphs.push(`Como parte de los acuerdos alcanzados, se definió: ${summaryData.decisions.join('. ')}.`)
      }
    }
    return summaryParagraphs
  })

  readonly keyInsights = computed<string[]>(() => {
    const summaryData = this.summaryData()
    return summaryData?.key_insights && summaryData.key_insights.length > 0
      ? summaryData.key_insights
      : summaryData?.action_items && summaryData.action_items.length > 0
        ? summaryData.action_items
        : summaryData?.requirements && summaryData.requirements.length > 0
          ? summaryData.requirements
          : []
  })

  readonly hasTranscriptContent = computed(() => {
    const displayResult = this.transcriptionResult()
    return Boolean(
      (displayResult?.text && displayResult.text.trim().length > 0) ||
        (displayResult?.segments && displayResult.segments.length > 0),
    )
  })

  readonly isSummaryReady = computed(() => {
    const summaryParagraphs = this.summaryParagraphs()
    return (
      this.hasTranscriptContent() &&
      ((summaryParagraphs.length > 0 &&
        summaryParagraphs.some(
          (p) =>
            p &&
            !p.toLowerCase().includes('no se detectaron diálogos') &&
            !p.toLowerCase().includes('no se detectaron dialogos') &&
            !p.toLowerCase().includes('sin texto registrado'),
        )) ||
        this.keyInsights().length > 0)
    )
  })

  readonly summaryText = computed(() => this.summaryData()?.summary_text || null)

  /** Wires the React hook parameters and starts the hook effects. Call once from the component constructor. */
  init(params: TranscriptionActionsParams): void {
    if (this.initialized) return
    this.initialized = true
    this.params = params
    this.paramsSignal.set(params)

    // Summary template selection queried from DB by tag like 'transcript_%'
    effect(
      (onCleanup) => {
        const templateId = this.summaryTemplateId()
        let isMounted = true
        onCleanup(() => {
          isMounted = false
        })
        untracked(() => {
          transcriptionApi
            .getSummaryTemplates('transcript_summary')
            .then((templates) => {
              if (!isMounted || !templates || templates.length === 0) return
              this._summaryTemplates.set(templates)
              this._selectedSummaryTemplate.update((prev) => {
                if (prev && templates.some((t) => t.id === prev)) return prev
                return templateId || templates[0]?.id || ''
              })
            })
            .catch(() => {})
        })
      },
      { injector: this.injector },
    )

    effect(
      () => {
        const templateId = this.summaryTemplateId()
        if (templateId) {
          untracked(() => this._selectedSummaryTemplate.set(templateId))
        }
      },
      { injector: this.injector },
    )

    // Fetch transcription data (React: useEffect on loadTranscription → [transcriptionId, activeProgress])
    effect(
      () => {
        this.transcriptionId()
        this.activeProgress()
        untracked(() => void this.loadTranscription())
      },
      { injector: this.injector },
    )

    // Reload when job finishes
    effect(
      () => {
        this.transcriptionId()
        const activeProgress = this.activeProgress()
        if (activeProgress && activeProgress.status === 'complete') {
          untracked(() => {
            void this.loadTranscription()
            this.params.onRefreshData?.()
          })
        }
      },
      { injector: this.injector },
    )

    // Close menus on click outside
    const handleClickOutside = (e: MouseEvent) => {
      if (this.transcriptMenuRef.current && !this.transcriptMenuRef.current.contains(e.target as Node)) {
        this._showTranscriptDownloadMenu.set(false)
      }
      if (this.summaryMenuRef.current && !this.summaryMenuRef.current.contains(e.target as Node)) {
        this._showSummaryDownloadMenu.set(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    this.destroyRef.onDestroy(() => document.removeEventListener('mousedown', handleClickOutside))
  }

  // ---- Setters (React useState setters) ----

  setGenerateModalOpen(action: SetStateAction<boolean>): void {
    this._generateModalOpen.update((prev) => resolveStateAction(action, prev))
  }

  setShowTranscriptDownloadMenu(action: SetStateAction<boolean>): void {
    this._showTranscriptDownloadMenu.update((prev) => resolveStateAction(action, prev))
  }

  setShowSummaryDownloadMenu(action: SetStateAction<boolean>): void {
    this._showSummaryDownloadMenu.update((prev) => resolveStateAction(action, prev))
  }

  setShowRenameModal(action: SetStateAction<boolean>): void {
    this._showRenameModal.update((prev) => resolveStateAction(action, prev))
  }

  setSpeakerMap(action: SetStateAction<Record<string, string>>): void {
    this._speakerMap.update((prev) => resolveStateAction(action, prev))
  }

  setSelectedSummaryTemplate(action: SetStateAction<string>): void {
    this._selectedSummaryTemplate.update((prev) => resolveStateAction(action, prev))
  }

  // ---- Actions ----

  /** Fetch transcription data */
  private async loadTranscription(): Promise<void> {
    const activeProgress = untracked(this.activeProgress)
    // If transcription is actively running in browser, do not query backend until completed
    if (activeProgress && activeProgress.status !== 'complete' && activeProgress.status !== 'failed') {
      return
    }
    try {
      const res = await transcriptionApi.getTranscriptionResult(untracked(this.transcriptionId))
      this.rawTranscriptionResult.set(res)

      // Initialize unique speakers map
      const speakers = Array.from(new Set(res.segments?.map((s) => s.speaker) || []))
      const initMap: Record<string, string> = {}
      speakers.forEach((spk) => {
        initMap[spk] = spk
      })
      this._speakerMap.set(initMap)
    } catch {
      // Result not ready or unavailable yet
    }
  }

  /** Toggle segment importance */
  toggleSegmentImportance(index: number): void {
    this._importantSegments.update((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  /** Handle re-transcription / regeneration with current configured model */
  async handleRetranscribe(): Promise<void> {
    const transcriptionId = this.transcriptionId()
    const onRetranscribe = this.params.onRetranscribe?.()
    try {
      this._isRetranscribing.set(true)
      if (onRetranscribe) {
        await onRetranscribe(transcriptionId, this.meetingTitle())
      } else {
        await transcriptionApi.startTranscription(transcriptionId, {
          mode: 'auto',
          enable_diarization: true,
          transcription_id: transcriptionId,
        })
        this.toast.info('Regeneración de transcripción iniciada.')
        this.params.onRefreshData?.()
      }
    } catch (err: unknown) {
      this.toast.error(`Error al regenerar transcripción: ${(err as Error)?.message}`)
    } finally {
      this._isRetranscribing.set(false)
    }
  }

  /** Handle AI summary generation */
  async handleGenerateSummary(templateIdOverride?: unknown): Promise<void> {
    const transcriptionId = this.transcriptionId()
    const summaryTemplates = this._summaryTemplates()
    const displayResult = this.transcriptionResult()
    const templateToUse =
      (typeof templateIdOverride === 'string' && templateIdOverride.trim().length > 0
        ? templateIdOverride.trim()
        : this._selectedSummaryTemplate()) ||
      summaryTemplates[0]?.id ||
      'transcript_summary_standard_meeting'
    try {
      this._isGeneratingSummary.set(true)
      const settings = await inferenceService.getAiSettings()
      const isBrowser = inferenceService.isBrowserExecution(settings)
      const transcriptContent = formatSegmentsForPrompt(displayResult?.segments, displayResult?.text)

      if (isBrowser && transcriptContent) {
        const [prompt, rubric] = await Promise.all([
          api.getAiPrompt(templateToUse).catch(() => null),
          api.getAiRubric(templateToUse).catch(() => null),
        ])

        const rubricText = rubric?.criteria?.length ? rubric.criteria.map((c: string) => `- ${c}`).join('\n') : ''
        const meetingTitle = displayResult?.metadata?.title || 'Reunión'

        const defaultSystem =
          'Eres un analista y redactor ejecutivo senior especializado en minutas y notas de reunión. Genera una síntesis profesional, clara y estructurada de la reunión basada estrictamente en la transcripción. No inventes información que no esté sustentada en la grabación.'
        const defaultUserTemplate = 'Título de la reunión: {title}\n\nTRANSCRIPCIÓN:\n{transcript}\n\nRÚBRICA:\n{rubric}'

        const systemPrompt = prompt?.system?.trim() || defaultSystem
        const userTemplate = prompt?.user_template?.trim() || defaultUserTemplate

        const safeTranscript = condenseTranscriptForBrowser(transcriptContent, 8000)
        const userContent = userTemplate
          .replace('{title}', meetingTitle)
          .replace('{transcript}', safeTranscript)
          .replace('{rubric}', rubricText)

        const genResult = await inferenceService.generateMessages(
          [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: userContent },
          ],
          undefined,
          { temperature: 0.3, maxTokens: 2500 },
        )

        const templateTitle =
          summaryTemplates.find((t) => t.id === templateToUse)?.title ||
          (typeof prompt?.title === 'string' ? prompt.title : templateToUse)

        const updated = await transcriptionApi.updateTranscriptionSummary(transcriptionId, {
          summary_text: genResult.content,
          template_id: templateToUse,
          template_name: templateTitle,
        })
        this.rawTranscriptionResult.set(updated.transcription)
        this.toast.success('Resumen generado con éxito con IA.')
        this.params.onRefreshData?.()
        return
      }

      const res = await transcriptionApi.generateSummary(transcriptionId, templateToUse)
      if (res.transcription) {
        this.rawTranscriptionResult.set(res.transcription)
        this.toast.success('Resumen generado con éxito.')
        this.params.onRefreshData?.()
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al generar resumen'
      this.toast.error(`Error al generar resumen: ${msg}`)
    } finally {
      this._isGeneratingSummary.set(false)
    }
  }

  /** Save to Knowledge Base */
  async handleSaveToKB(): Promise<void> {
    const transcriptionId = this.transcriptionId()
    const transcriptionResult = this.rawTranscriptionResult()
    try {
      this._isSavingKB.set(true)
      await transcriptionApi.saveToKnowledgeBase(transcriptionId, ['reunion', 'transcripcion'])
      this.toast.success('Transcripción y resumen indexados en la Base de Conocimiento.')
      if (transcriptionResult) {
        this.rawTranscriptionResult.set({ ...transcriptionResult, saved_to_knowledge: true })
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al guardar'
      this.toast.error(`Error al guardar en Base de Conocimiento: ${msg}`)
    } finally {
      this._isSavingKB.set(false)
    }
  }

  /** Rename speakers */
  async handleSaveSpeakerNames(): Promise<void> {
    try {
      const res = await transcriptionApi.renameSpeakers(this.transcriptionId(), this._speakerMap())
      this.rawTranscriptionResult.set(res.transcription)
      this._showRenameModal.set(false)
      this.toast.success('Interlocutores actualizados.')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al renombrar'
      this.toast.error(`Error al renombrar: ${msg}`)
    }
  }

  /** Copy transcript */
  handleCopyTranscript(): void {
    const transcriptionResult = this.rawTranscriptionResult()
    const importantSegments = this._importantSegments()
    if (!transcriptionResult?.segments || transcriptionResult.segments.length === 0) {
      if (transcriptionResult?.text) {
        void navigator.clipboard.writeText(transcriptionResult.text)
        this._hasCopiedTranscript.set(true)
        setTimeout(() => this._hasCopiedTranscript.set(false), 2000)
        this.toast.success('Transcripción copiada.')
      }
      return
    }

    const lines = transcriptionResult.segments.map((seg, idx) => {
      const time = formatTimestamp(seg.start)
      const isImportant = importantSegments.has(idx)
      const prefix = isImportant ? '**[IMPORTANTE] ' : ''
      const suffix = isImportant ? '**' : ''
      return `${prefix}[${time}] ${seg.speaker}: ${seg.text}${suffix}`
    })

    void navigator.clipboard.writeText(lines.join('\n\n'))
    this._hasCopiedTranscript.set(true)
    setTimeout(() => this._hasCopiedTranscript.set(false), 2000)
    this.toast.success('Transcripción copiada al portapapeles.')
  }

  /** Download transcript as TXT */
  handleDownloadTranscriptTxt(): void {
    const transcriptionResult = this.rawTranscriptionResult()
    const importantSegments = this._importantSegments()
    if (!transcriptionResult) return
    const title = transcriptionResult.metadata?.title || 'Transcripcion'
    const safeTitle = title.replace(/[^a-zA-Z0-9_-]/g, '_')

    let content = `# Transcripción: ${title}\n`
    content += `Fecha: ${transcriptionResult.created_at}\n`
    content += `Duración: ${Math.round(transcriptionResult.duration_seconds)} segundos\n\n`
    content += `------------------------------------------------------------\n\n`

    if (transcriptionResult.segments && transcriptionResult.segments.length > 0) {
      const lines = transcriptionResult.segments.map((seg, idx) => {
        const time = formatTimestamp(seg.start)
        const isImportant = importantSegments.has(idx)
        if (isImportant) {
          return `**[${time}] ${seg.speaker}: ${seg.text}**`
        }
        return `[${time}] ${seg.speaker}: ${seg.text}`
      })
      content += lines.join('\n\n')
    } else {
      content += transcriptionResult.text || 'Sin texto registrado.'
    }

    downloadFile(content, `Transcripcion_${safeTitle}.txt`, 'text/plain;charset=utf-8')
    this._showTranscriptDownloadMenu.set(false)
  }

  /** Download transcript as JSON */
  handleDownloadTranscriptJson(): void {
    const transcriptionResult = this.rawTranscriptionResult()
    const importantSegments = this._importantSegments()
    if (!transcriptionResult) return
    const safeTitle = (transcriptionResult.metadata?.title || 'Transcripcion').replace(/[^a-zA-Z0-9_-]/g, '_')

    const data = {
      ...transcriptionResult,
      segments: transcriptionResult.segments.map((s, idx) => ({
        ...s,
        is_important: importantSegments.has(idx),
      })),
    }

    downloadFile(JSON.stringify(data, null, 2), `Transcripcion_${safeTitle}.json`, 'application/json;charset=utf-8')
    this._showTranscriptDownloadMenu.set(false)
  }

  /** Copy summary text */
  handleCopySummary(): void {
    if (!this.isSummaryReady()) return
    let text = this.summaryText()
    if (!text) {
      text = `# Summary\n\n${this.summaryParagraphs().join('\n\n')}\n\n# Key Insights\n\n`
      text += this.keyInsights()
        .map((ki) => `• ${ki}`)
        .join('\n\n')
    }

    void navigator.clipboard.writeText(text)
    this._hasCopiedSummary.set(true)
    setTimeout(() => this._hasCopiedSummary.set(false), 2000)
    this.toast.success('Resumen copiado al portapapeles.')
  }

  /** Download summary as Markdown (.md) */
  handleDownloadSummaryMd(): void {
    const displayResult = this.transcriptionResult()
    if (!displayResult || !this.isSummaryReady()) return
    const summaryParagraphs = this.summaryParagraphs()
    const keyInsights = this.keyInsights()
    const title = displayResult.metadata?.title || 'Resumen'
    const safeTitle = title.replace(/[^a-zA-Z0-9_-]/g, '_')

    let content = this.summaryText()
    if (!content) {
      content = `# Resumen: ${title}\n\n`
      if (summaryParagraphs.length > 0) {
        content += `## Puntos Clave\n\n${summaryParagraphs.join('\n\n')}\n\n`
      }
      if (keyInsights.length > 0) {
        content += `## Insights Principales\n\n`
        content += keyInsights.map((ki) => `- ${ki}`).join('\n')
        content += '\n'
      }
    }

    downloadFile(content, `Resumen_${safeTitle}.md`, 'text/markdown;charset=utf-8')
    this._showSummaryDownloadMenu.set(false)
  }

  /** Download summary as JSON */
  handleDownloadSummaryJson(): void {
    const displayResult = this.transcriptionResult()
    if (!displayResult || !this.isSummaryReady()) return
    const safeTitle = (displayResult.metadata?.title || 'Resumen').replace(/[^a-zA-Z0-9_-]/g, '_')

    const data = {
      meeting_title: displayResult.metadata?.title,
      summary_paragraphs: this.summaryParagraphs(),
      key_insights: this.keyInsights(),
      summary_raw: this.summaryData(),
    }

    downloadFile(JSON.stringify(data, null, 2), `Resumen_${safeTitle}.json`, 'application/json;charset=utf-8')
    this._showSummaryDownloadMenu.set(false)
  }
}
