import type { RefObject } from 'react'
import { FileText, RefreshCw, Sparkles, Square } from 'lucide-react'
import { MarkdownMessage } from '../../../components/common'
import type { ChatPersistMessage } from '../hooks/useChatPersistence'
import type { AgentRunState } from '../types/agentEvents'
import type { Artifact } from '../../../types/artifacts'
import { InlineArtifactCard } from './InlineArtifactCard'

interface ChatMessageListProps {
  messages: ChatPersistMessage[]
  artifacts?: Artifact[]
  title: string
  subtitle: string
  isCurrentChatGenerating: boolean
  streamingText: string
  runState: AgentRunState
  chatBottomRef: RefObject<HTMLDivElement | null>
  onCancelRun: () => void
  onOpenArtifact?: (artifact: Artifact) => void
}

export const ChatMessageList = ({
  messages,
  artifacts = [],
  title,
  subtitle,
  isCurrentChatGenerating,
  streamingText,
  runState,
  chatBottomRef,
  onCancelRun,
  onOpenArtifact,
}: ChatMessageListProps) => {
  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
      {messages.length === 0 ? (
        <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-3 max-w-md mx-auto">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-[#002777] border border-blue-100 shadow-xs">
            <Sparkles className="h-6 w-6" />
          </div>
          <div className="space-y-1">
            <h2 className="text-base font-bold text-slate-900">{title}</h2>
            <p className="text-xs text-slate-500 leading-relaxed">{subtitle}</p>
          </div>
        </div>
      ) : (
        <>
          {messages.map((m, idx) => {
            const isLastAssistantMessage =
              m.role === 'assistant' &&
              idx === messages.map((msg) => msg.role).lastIndexOf('assistant')

            return (
              <div
                key={m.id}
                className={`flex gap-3 text-xs ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {/* Assistant spark icon */}
                {m.role === 'assistant' && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[#001744] text-white shadow-xs mt-0.5">
                    <Sparkles className="h-4 w-4 text-cyan-300" />
                  </div>
                )}

                <div
                  className={`max-w-[85%] rounded-2xl p-3.5 space-y-2 ${
                    m.role === 'user'
                      ? 'bg-[#002777] text-white rounded-br-none shadow-sm'
                      : 'bg-white text-slate-800 border border-slate-200/80 rounded-bl-none shadow-xs'
                  }`}
                >
                  <div className="flex items-center justify-between gap-4 text-[10px] opacity-70 font-medium">
                    <span>{m.role === 'user' ? 'Tú' : 'Asistente IA'}</span>
                    <span>{m.timestamp}</span>
                  </div>

                  {m.role === 'user' ? (
                    <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                  ) : (
                    <MarkdownMessage content={m.content} />
                  )}

                  {/* Inline Artifact Card for Assistant Responses */}
                  {m.role === 'assistant' &&
                    isLastAssistantMessage &&
                    artifacts.length > 0 &&
                    onOpenArtifact && (
                      <div className="pt-1">
                        {artifacts.map((art) => (
                          <InlineArtifactCard
                            key={art.id}
                            artifact={art}
                            onOpen={onOpenArtifact}
                          />
                        ))}
                      </div>
                    )}

                  {/* Attached images and documents inside message bubble */}
                  {m.attachments && m.attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {m.attachments.map((att) =>
                        att.type === 'image' && att.dataUrl ? (
                          <a
                            key={att.id}
                            href={att.dataUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block"
                          >
                            <img
                              src={att.dataUrl}
                              alt={att.name}
                              className="h-14 w-14 object-cover rounded-xl border border-white/20 shadow-2xs hover:opacity-90 transition"
                            />
                          </a>
                        ) : (
                          <span
                            key={att.id}
                            className="inline-flex items-center gap-1.5 text-[11px] bg-white/15 px-2.5 py-1 rounded-xl border border-white/20 text-white shadow-2xs font-medium"
                          >
                            <FileText className="h-3.5 w-3.5 text-blue-200" />
                            <span className="truncate max-w-[200px]">{att.name}</span>
                          </span>
                        ),
                      )}
                    </div>
                  )}
                </div>

                {/* User avatar indicator */}
                {m.role === 'user' && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white font-bold text-xs shadow-xs mt-0.5">
                    Tú
                  </div>
                )}
              </div>
            )
          })}

          {/* Minimal loading state while generating */}
          {isCurrentChatGenerating && (
            <div className="flex gap-3 justify-start animate-in fade-in duration-150" aria-busy="true">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[#001744] text-white shadow-xs mt-0.5">
                <Sparkles className="h-4 w-4 text-cyan-300" />
              </div>
              <div className="relative w-full max-w-[85%] overflow-hidden rounded-2xl rounded-bl-none border border-slate-200 bg-white p-4 text-slate-800 shadow-xs space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
                  <div className="flex items-center gap-2">
                    <RefreshCw className="h-4 w-4 animate-spin text-[#002777]" aria-hidden="true" />
                    <span className="text-xs font-semibold text-slate-700">
                      {runState.activeStatusText || 'Generando y consolidando documento...'}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={onCancelRun}
                    className="px-2.5 py-1 text-[11px] font-semibold text-red-600 hover:text-white hover:bg-red-600 rounded-lg border border-red-200 bg-red-50/50 transition cursor-pointer flex items-center gap-1"
                    title="Detener la generación actual"
                  >
                    <Square className="h-3 w-3 fill-current" />
                    <span>Cancelar</span>
                  </button>
                </div>

                {streamingText ? (
                  <div className="text-xs text-slate-700">
                    <MarkdownMessage content={streamingText} />
                  </div>
                ) : (
                  <div className="space-y-2.5 animate-pulse py-1" aria-hidden="true">
                    <div className="h-2.5 w-full rounded-full bg-slate-200" />
                    <div className="h-2.5 w-11/12 rounded-full bg-slate-200" />
                    <div className="h-2.5 w-4/5 rounded-full bg-slate-200" />
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
      <div ref={chatBottomRef} />
    </div>
  )
}

export default ChatMessageList
