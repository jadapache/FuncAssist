import { copyText } from '../../../core/browser/secureContext'
import { useState, useRef, useEffect, type RefObject } from 'react'
import { ArrowDown, Check, Copy, FileText, RotateCcw, Sparkles } from 'lucide-react'
import { MarkdownMessage } from '../../../components/common'
import type { ChatAttachment, ChatPersistMessage } from '../hooks/useChatPersistence'
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
  onCancelRun?: () => void
  onOpenArtifact?: (artifact: Artifact) => void
  onRetryMessage?: (content: string, attachments?: ChatAttachment[]) => void
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
  onOpenArtifact,
  onRetryMessage,
}: ChatMessageListProps) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [showScrollBottom, setShowScrollBottom] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const handleCopy = (id: string, text: string) => {
    if (!text) return
    void copyText(text)
    setCopiedId(id)
    setTimeout(() => {
      setCopiedId((current) => (current === id ? null : current))
    }, 2000)
  }

  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setShowScrollBottom(distanceFromBottom > 150)
  }

  const scrollToBottom = () => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    handleScroll()
  }, [messages, streamingText])

  return (
    <div className="relative flex-1 min-h-0 flex flex-col">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4"
      >
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

              if (m.role === 'assistant' && m.content === 'Detuviste esta respuesta') {
                return (
                  <div key={m.id} className="relative flex items-center justify-center my-4 py-1">
                    <div className="absolute inset-0 flex items-center" aria-hidden="true">
                      <div className="w-full border-t border-slate-200" />
                    </div>
                    <div className="relative bg-slate-50 px-3 text-xs text-slate-500 font-medium">
                      Detuviste esta respuesta
                    </div>
                  </div>
                )
              }

              if (m.role === 'assistant') {
                return (
                  <div key={m.id} className="group flex flex-col text-xs justify-start">
                    <div className="max-w-[85%] py-1 space-y-2 text-slate-800 leading-relaxed">
                      <MarkdownMessage content={m.content} />

                      {/* Inline Artifact Card for Assistant Responses */}
                      {isLastAssistantMessage && artifacts.length > 0 && onOpenArtifact && (
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

                      {/* Action buttons under assistant message */}
                      <div className="flex items-center gap-1 pt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          type="button"
                          onClick={() => handleCopy(m.id, m.content)}
                          className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition cursor-pointer"
                          title="Copiar respuesta"
                          aria-label="Copiar respuesta"
                        >
                          {copiedId === m.id ? (
                            <Check className="h-3.5 w-3.5 text-emerald-600" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                )
              }

              return (
                <div key={m.id} className="group flex flex-col items-end gap-1 text-xs">
                  <div className="flex gap-3 justify-end w-full">
                    <div className="max-w-[85%] rounded-2xl p-3.5 space-y-2 bg-[#002777] text-white rounded-br-none shadow-sm">
                      <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>

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
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white font-bold text-xs shadow-xs mt-0.5">
                      Tú
                    </div>
                  </div>

                  {/* Action buttons under user prompt: Copy & Retry */}
                  <div className="flex items-center gap-1 pr-11 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      type="button"
                      onClick={() => handleCopy(m.id, m.content)}
                      className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition cursor-pointer"
                      title="Copiar instrucción"
                      aria-label="Copiar instrucción"
                    >
                      {copiedId === m.id ? (
                        <Check className="h-3.5 w-3.5 text-emerald-600" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </button>
                    {onRetryMessage && (
                      <button
                        type="button"
                        onClick={() => onRetryMessage(m.content, m.attachments)}
                        className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 hover:text-blue-600 hover:bg-blue-50 transition cursor-pointer"
                        title="Reenviar petición"
                        aria-label="Reenviar petición"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })}

            {/* Loading and streaming state while generating */}
            {isCurrentChatGenerating && (
              <div className="flex flex-col justify-start animate-in fade-in duration-150" aria-busy="true">
                <div className="max-w-[85%] py-1 space-y-2 text-xs text-slate-800">
                  {!streamingText && (
                    <div className="flex items-center gap-2 text-slate-600 font-medium py-1">
                      <span>{runState.activeStatusText || 'Pensando'}</span>
                      <span className="inline-flex items-center gap-1" aria-hidden="true">
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]" />
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]" />
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" />
                      </span>
                    </div>
                  )}

                  {streamingText && (
                    <div className="text-slate-800">
                      <MarkdownMessage content={streamingText} />
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
        <div ref={chatBottomRef} />
      </div>

      {/* Floating scroll to bottom button */}
      {showScrollBottom && (
        <button
          type="button"
          onClick={scrollToBottom}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 flex h-9 w-9 items-center justify-center rounded-full bg-white border border-slate-200/90 text-slate-600 hover:text-slate-900 shadow-md hover:bg-slate-50 transition duration-150 cursor-pointer"
          title="Ir al final de la conversación"
          aria-label="Ir al final de la conversación"
        >
          <ArrowDown className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

export default ChatMessageList
