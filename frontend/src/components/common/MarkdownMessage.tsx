import React, { type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownMessageProps {
  content: string
  className?: string
}

interface ComponentProps {
  children?: ReactNode
  className?: string
}

/**
 * Rich Markdown renderer with GitHub Flavored Markdown (GFM) support.
 * Renders headings, bold/italic, code blocks, lists, and tables cleanly.
 */
export const MarkdownMessage: React.FC<MarkdownMessageProps> = ({
  content,
  className = '',
}) => {
  if (!content) return null

  return (
    <div className={`prose-sm max-w-none text-slate-800 leading-relaxed text-xs space-y-2 ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }: ComponentProps) => (
            <h1 className="text-base font-bold text-slate-900 mt-4 mb-2 first:mt-0 tracking-tight">
              {children}
            </h1>
          ),
          h2: ({ children }: ComponentProps) => (
            <h2 className="text-sm font-bold text-slate-900 mt-4 mb-2 first:mt-0 tracking-tight pb-1 border-b border-slate-100">
              {children}
            </h2>
          ),
          h3: ({ children }: ComponentProps) => (
            <h3 className="text-xs font-bold text-slate-900 mt-3 mb-1.5 first:mt-0">
              {children}
            </h3>
          ),
          p: ({ children }: ComponentProps) => (
            <p className="mb-2 last:mb-0 leading-relaxed text-slate-700">
              {children}
            </p>
          ),
          ul: ({ children }: ComponentProps) => (
            <ul className="list-disc pl-4 mb-2 space-y-1 text-slate-700 marker:text-slate-400">
              {children}
            </ul>
          ),
          ol: ({ children }: ComponentProps) => (
            <ol className="list-decimal pl-4 mb-2 space-y-1 text-slate-700 marker:text-slate-500 font-medium">
              {children}
            </ol>
          ),
          li: ({ children }: ComponentProps) => (
            <li className="leading-relaxed">
              {children}
            </li>
          ),
          strong: ({ children }: ComponentProps) => (
            <strong className="font-semibold text-slate-900">
              {children}
            </strong>
          ),
          em: ({ children }: ComponentProps) => (
            <em className="italic text-slate-800">
              {children}
            </em>
          ),
          code: ({ children, className: codeClass }: ComponentProps) => {
            const isBlock = codeClass?.includes('language-')
            if (isBlock) {
              return (
                <div className="my-2 overflow-x-auto rounded-xl border border-slate-200 bg-slate-900 p-3 text-[11px] text-slate-100 font-mono shadow-xs">
                  <code>{children}</code>
                </div>
              )
            }
            return (
              <code className="rounded-md bg-slate-200/70 px-1.5 py-0.5 font-mono text-[11px] text-slate-800">
                {children}
              </code>
            )
          },
          pre: ({ children }: ComponentProps) => <>{children}</>,
          blockquote: ({ children }: ComponentProps) => (
            <blockquote className="my-2 border-l-2 border-[#002777] pl-3 italic text-slate-600 bg-blue-50/40 py-1 rounded-r-lg">
              {children}
            </blockquote>
          ),
          table: ({ children }: ComponentProps) => (
            <div className="my-3 overflow-x-auto rounded-xl border border-slate-200 shadow-2xs bg-white">
              <table className="min-w-full divide-y divide-slate-200 text-xs text-left">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }: ComponentProps) => (
            <thead className="bg-slate-50 font-semibold text-slate-800 divide-y divide-slate-200">
              {children}
            </thead>
          ),
          tbody: ({ children }: ComponentProps) => (
            <tbody className="divide-y divide-slate-100 bg-white">
              {children}
            </tbody>
          ),
          tr: ({ children }: ComponentProps) => (
            <tr className="hover:bg-slate-50/60 transition-colors">
              {children}
            </tr>
          ),
          th: ({ children }: ComponentProps) => (
            <th className="px-3.5 py-2 font-semibold text-slate-800 whitespace-nowrap bg-slate-50/90">
              {children}
            </th>
          ),
          td: ({ children }: ComponentProps) => (
            <td className="px-3.5 py-2 text-slate-600 align-top">
              {children}
            </td>
          ),
          hr: () => <hr className="my-3 border-slate-200" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
