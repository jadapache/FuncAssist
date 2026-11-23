import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core'
import { Marked } from 'marked'

/**
 * Rich Markdown renderer with clean styling support (port of React `MarkdownMessage`).
 *
 * Parity notes with the React implementation (react-markdown, no remark-gfm):
 * - CommonMark only (`gfm: false`): no tables/strikethrough/autolinks, exactly like React today.
 * - Raw HTML is escaped, never rendered.
 * - Fenced code WITH a language → dark block; without a language → inline-styled code (react-markdown quirk).
 * - Each element receives the same Tailwind classes as the React `components` map.
 */
const markdown = new Marked({
  gfm: false,
  breaks: false,
  async: false,
  renderer: {
    html({ text }) {
      return escapeHtml(text)
    },
  },
})

const CLASSES: Record<string, string> = {
  h1: 'text-base font-bold text-slate-900 mt-4 mb-2 first:mt-0 tracking-tight',
  h2: 'text-sm font-bold text-slate-900 mt-4 mb-2 first:mt-0 tracking-tight pb-1 border-b border-slate-100',
  h3: 'text-xs font-bold text-slate-900 mt-3 mb-1.5 first:mt-0',
  p: 'mb-2 last:mb-0 leading-relaxed text-slate-700',
  ul: 'list-disc pl-4 mb-2 space-y-1 text-slate-700 marker:text-slate-400',
  ol: 'list-decimal pl-4 mb-2 space-y-1 text-slate-700 marker:text-slate-500 font-medium',
  li: 'leading-relaxed',
  strong: 'font-semibold text-slate-900',
  em: 'italic text-slate-800',
  blockquote: 'my-2 border-l-2 border-[#002777] pl-3 italic text-slate-600 bg-blue-50/40 py-1 rounded-r-lg',
  thead: 'bg-slate-50 font-semibold text-slate-800 divide-y divide-slate-200',
  tbody: 'divide-y divide-slate-100 bg-white',
  tr: 'hover:bg-slate-50/60 transition-colors',
  th: 'px-3.5 py-2 font-semibold text-slate-800 whitespace-nowrap bg-slate-50/90',
  td: 'px-3.5 py-2 text-slate-600 align-top',
  hr: 'my-3 border-slate-200',
}
const INLINE_CODE_CLASS = 'rounded-md bg-slate-200/70 px-1.5 py-0.5 font-mono text-[11px] text-slate-800'
const BLOCK_CODE_CLASS =
  'my-2 overflow-x-auto rounded-xl border border-slate-200 bg-slate-900 p-3 text-[11px] text-slate-100 font-mono shadow-xs'
const TABLE_WRAPPER_CLASS = 'my-3 overflow-x-auto rounded-xl border border-slate-200 shadow-2xs bg-white'
const TABLE_CLASS = 'min-w-full divide-y divide-slate-200 text-xs text-left'

export function renderMarkdownToHtml(content: string): string {
  const raw = markdown.parse(content) as string
  const template = document.createElement('template')
  template.innerHTML = raw
  const root = template.content

  // <pre><code class="language-x"> → styled block <div><code>; <pre><code> (no lang) → inline-styled code
  root.querySelectorAll('pre').forEach((pre) => {
    const code = pre.querySelector('code')
    if (!code) return
    const isBlock = Array.from(code.classList).some((c) => c.startsWith('language-'))
    if (isBlock) {
      const wrapper = document.createElement('div')
      wrapper.className = BLOCK_CODE_CLASS
      const plainCode = document.createElement('code')
      plainCode.textContent = code.textContent
      wrapper.appendChild(plainCode)
      pre.replaceWith(wrapper)
    } else {
      code.className = INLINE_CODE_CLASS
      pre.replaceWith(code)
    }
  })
  root.querySelectorAll('code').forEach((code) => {
    if (!code.className) code.className = INLINE_CODE_CLASS
  })
  root.querySelectorAll('table').forEach((table) => {
    const wrapper = document.createElement('div')
    wrapper.className = TABLE_WRAPPER_CLASS
    table.className = TABLE_CLASS
    table.replaceWith(wrapper)
    wrapper.appendChild(table)
  })
  for (const [tag, cls] of Object.entries(CLASSES)) {
    root.querySelectorAll(tag).forEach((el) => (el.className = cls))
  }
  return template.innerHTML
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

@Component({
  selector: 'app-markdown-message',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (content()) {
      <div
        [class]="'prose-sm max-w-none text-slate-800 leading-relaxed text-xs space-y-2 ' + className()"
        [innerHTML]="html()"
      ></div>
    }
  `,
})
export class MarkdownMessageComponent {
  readonly content = input<string>('')
  readonly className = input<string>('')

  protected readonly html = computed(() => {
    const content = this.content()
    return content ? renderMarkdownToHtml(content) : ''
  })
}
