import { AlertCircle, RefreshCw } from 'lucide-react'
import { AiModelsSkeleton } from '../common'
import { FloatingTranscriptionToast } from '../../features/transcription/components/FloatingTranscriptionToast'
import { useAiSettingsManager } from './hooks/useAiSettingsManager'
import { WritingModelSection } from './WritingModelSection'
import { VoiceAudioSection } from './VoiceAudioSection'

export const AiModelsPanel = () => {
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
    isPulling,
    pullingModelTag,
    pullStatusMsg,
    handlePullModel,
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
    localWhisperModels,
    downloadingWhisperId,
    deletingWhisperId,
    fetchingWhisperModels,
    fetchLocalWhisperModels,
    handleDownloadWhisperModel,
    handleDeleteWhisperModel,
    localBuiltinModels,
    downloadingBuiltinId,
    deletingBuiltinId,
    fetchingBuiltinModels,
    fetchLocalBuiltinModels,
    handleDownloadBuiltinModel,
    handleDeleteBuiltinModel,
    handleCancelBuiltinDownload,
    handleDismissDownloadTask,
    downloadTasks,
  } = useAiSettingsManager()


  if (loadingAi) {
    return <AiModelsSkeleton />
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-slate-900">Configuración del Modelo de IA</h2>
        <p className="text-sm text-slate-500">
          Configura el modelo de IA utilizado para la generación de resúmenes, análisis de QA, transcripción de reuniones y comandos de voz.
        </p>
      </div>

      {/* Alerta de conexión si el catálogo externo falló */}
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
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-900 font-semibold text-xs transition cursor-pointer shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Reintentar</span>
          </button>
        </div>
      )}

      {/* Panel 1: Modelo de Redacción y Chat */}
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
        isPulling={isPulling}
        pullingModelTag={pullingModelTag}
        pullStatusMsg={pullStatusMsg}
        handlePullModel={handlePullModel}
        localBuiltinModels={localBuiltinModels}
        downloadingBuiltinId={downloadingBuiltinId}
        deletingBuiltinId={deletingBuiltinId}
        fetchingBuiltinModels={fetchingBuiltinModels}
        fetchLocalBuiltinModels={fetchLocalBuiltinModels}
        handleDownloadBuiltinModel={handleDownloadBuiltinModel}
        handleDeleteBuiltinModel={handleDeleteBuiltinModel}
        handleCancelBuiltinDownload={handleCancelBuiltinDownload}
        downloadTasks={downloadTasks}
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
        handleAiSave={handleAiSave}
        handleTestConnection={handleTestConnection}
      />

      {/* Panel 2: Modelo de Transcripción y Comandos de Voz */}
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
        handleVoiceAudioSave={handleVoiceAudioSave}
        localWhisperModels={localWhisperModels}
        downloadingWhisperId={downloadingWhisperId}
        deletingWhisperId={deletingWhisperId}
        fetchingWhisperModels={fetchingWhisperModels}
        fetchLocalWhisperModels={fetchLocalWhisperModels}
        handleDownloadWhisperModel={handleDownloadWhisperModel}
        handleDeleteWhisperModel={handleDeleteWhisperModel}
      />

      {/* Floating Toast for Built-in Models Download Progress & Cancellation */}
      <FloatingTranscriptionToast
        extraTasks={Object.values(downloadTasks)}
        onCancelJob={(id) => void handleCancelBuiltinDownload(id)}
        onDismissJob={(id) => handleDismissDownloadTask(id)}
      />
    </div>
  )
}

