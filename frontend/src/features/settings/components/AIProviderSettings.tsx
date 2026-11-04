import type { FormEvent } from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'
import { AiModelsSkeleton } from '../../../components/common'
import { useAiSettingsManager } from '../hooks/useAiSettingsManager'
import { WritingModelSection } from './WritingModelSection'
import { VoiceAudioSection } from './VoiceAudioSection'

export type AIProviderSettingsProps = {
  onSaved?: () => void
}

export const AIProviderSettings = ({ onSaved }: AIProviderSettingsProps) => {
  const aiManager = useAiSettingsManager()
  const {
    ai,
    loadingAi,
    provider,
    setProvider,
    model,
    setModel,
    isWritingOpen,
    setIsWritingOpen,
    showEndpointSection,
    setShowEndpointSection,
    ollamaUrl,
    setOllamaUrl,
    ollamaOnline,
    ollamaModels,
    fetchingModels,
    fetchOllamaModels,
    catalogModels,
    catalogError,
    loadDynamicCatalog,
    groqKey,
    setGroqKey,
    geminiKey,
    setGeminiKey,
    openaiKey,
    setOpenaiKey,
    claudeKey,
    setClaudeKey,
    showKey,
    setShowKey,
    savingAi,
    testingConnection,
    handleAiSave,
    handleTestConnection,
    voiceAudioProvider,
    setVoiceAudioProvider,
    voiceAudioModel,
    setVoiceAudioModel,
    transcriptionGroqKey,
    setTranscriptionGroqKey,
    transcriptionOpenaiKey,
    setTranscriptionOpenaiKey,
    showTranscriptionKey,
    setShowTranscriptionKey,
    isVoiceAudioOpen,
    setIsVoiceAudioOpen,
    handleVoiceAudioSave,
  } = aiManager

  const wrappedHandleAiSave = async (e?: FormEvent) => {
    await handleAiSave(e)
    onSaved?.()
  }

  const wrappedHandleVoiceAudioSave = async (e?: FormEvent) => {
    await handleVoiceAudioSave(e)
    onSaved?.()
  }

  if (loadingAi) {
    return <AiModelsSkeleton />
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-slate-900">Configuración del Modelo de IA</h2>
        <p className="text-sm text-slate-500">
          Configura los modelos de IA para chat, redacción y transcripción (en este navegador o APIs externas).
        </p>
      </div>

      {catalogError && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-xs text-amber-900 flex items-center justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-2.5">
            <AlertCircle className="h-5 w-5 text-amber-600 shrink-0" />
            <div>
              <p className="font-bold text-amber-950">{catalogError}</p>
              <p className="text-[11px] text-amber-700 mt-0.5">
                No se pudo contactar a los proveedores externos para actualizar el catálogo de modelos.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void loadDynamicCatalog(true)}
            className="btn btn-secondary text-xs py-1.5 px-3 shrink-0 inline-flex items-center gap-1.5 cursor-pointer"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Reintentar</span>
          </button>
        </div>
      )}

      <WritingModelSection
        ai={ai}
        provider={provider}
        setProvider={setProvider}
        model={model}
        setModel={setModel}
        isWritingOpen={isWritingOpen}
        setIsWritingOpen={setIsWritingOpen}
        showEndpointSection={showEndpointSection}
        setShowEndpointSection={setShowEndpointSection}
        ollamaUrl={ollamaUrl}
        setOllamaUrl={setOllamaUrl}
        ollamaOnline={ollamaOnline}
        ollamaModels={ollamaModels}
        fetchingModels={fetchingModels}
        fetchOllamaModels={fetchOllamaModels}
        catalogModels={catalogModels}
        groqKey={groqKey}
        setGroqKey={setGroqKey}
        geminiKey={geminiKey}
        setGeminiKey={setGeminiKey}
        openaiKey={openaiKey}
        setOpenaiKey={setOpenaiKey}
        claudeKey={claudeKey}
        setClaudeKey={setClaudeKey}
        showKey={showKey}
        setShowKey={setShowKey}
        savingAi={savingAi}
        testingConnection={testingConnection}
        handleAiSave={wrappedHandleAiSave}
        handleTestConnection={handleTestConnection}
      />

      <VoiceAudioSection
        ai={ai}
        voiceAudioProvider={voiceAudioProvider}
        setVoiceAudioProvider={setVoiceAudioProvider}
        voiceAudioModel={voiceAudioModel}
        setVoiceAudioModel={setVoiceAudioModel}
        isVoiceAudioOpen={isVoiceAudioOpen}
        setIsVoiceAudioOpen={setIsVoiceAudioOpen}
        catalogModels={catalogModels}
        transcriptionGroqKey={transcriptionGroqKey}
        setTranscriptionGroqKey={setTranscriptionGroqKey}
        transcriptionOpenaiKey={transcriptionOpenaiKey}
        setTranscriptionOpenaiKey={setTranscriptionOpenaiKey}
        showTranscriptionKey={showTranscriptionKey}
        setShowTranscriptionKey={setShowTranscriptionKey}
        savingAi={savingAi}
        handleVoiceAudioSave={wrappedHandleVoiceAudioSave}
      />
    </div>
  )
}
