import { renderMarkdownToHtml } from './markdown-message.component'

/** Parity checks against the React `MarkdownMessage` (react-markdown without remark-gfm). */
describe('renderMarkdownToHtml', () => {
  const render = (md: string) => {
    const div = document.createElement('div')
    div.innerHTML = renderMarkdownToHtml(md)
    return div
  }

  it('applies the React heading/paragraph classes', () => {
    const el = render('# Título\n\nTexto **fuerte** y *énfasis*')
    expect(el.querySelector('h1')?.className).toContain('text-base font-bold')
    expect(el.querySelector('p')?.className).toContain('mb-2 last:mb-0')
    expect(el.querySelector('strong')?.className).toBe('font-semibold text-slate-900')
    expect(el.querySelector('em')?.className).toBe('italic text-slate-800')
  })

  it('renders fenced code with a language as a dark block without <pre>', () => {
    const el = render('```ts\nconst a = 1\n```')
    expect(el.querySelector('pre')).toBeNull()
    const block = el.querySelector('div')
    expect(block?.className).toContain('bg-slate-900')
    expect(block?.querySelector('code')?.textContent).toContain('const a = 1')
  })

  it('renders fenced code WITHOUT language as inline-styled code (react-markdown quirk)', () => {
    const el = render('```\nplain\n```')
    expect(el.querySelector('pre')).toBeNull()
    expect(el.querySelector('code')?.className).toContain('rounded-md bg-slate-200/70')
  })

  it('styles inline code', () => {
    const el = render('usa `npm ci`')
    expect(el.querySelector('code')?.className).toContain('font-mono text-[11px]')
  })

  it('escapes raw HTML instead of rendering it', () => {
    const el = render('<script>alert(1)</script>\n\n<b>bold</b>')
    expect(el.querySelector('script')).toBeNull()
    expect(el.querySelector('b')).toBeNull()
    expect(el.textContent).toContain('<b>bold</b>')
  })

  it('does not parse GFM tables (React has no remark-gfm)', () => {
    const el = render('| a | b |\n|---|---|\n| 1 | 2 |')
    expect(el.querySelector('table')).toBeNull()
  })

  it('styles lists and blockquotes', () => {
    const el = render('- uno\n- dos\n\n1. a\n2. b\n\n> cita')
    expect(el.querySelector('ul')?.className).toContain('list-disc')
    expect(el.querySelector('ol')?.className).toContain('list-decimal')
    expect(el.querySelectorAll('li')[0]?.className).toBe('leading-relaxed')
    expect(el.querySelector('blockquote')?.className).toContain('border-[#002777]')
  })
})
