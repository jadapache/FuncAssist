import type { GroundedResult } from '../../api/client'

export const GroundedResultView = ({ result }: { result: GroundedResult }) => {
  if (result.refused || !result.ok) {
    return (
      <section className="rounded-xl border border-[rgba(161,92,18,0.3)] bg-[rgba(161,92,18,0.08)] p-5">
        <h2 className="text-lg font-semibold text-[var(--color-warn)]">Sin respuesta — fuentes incompletas</h2>
        <p className="mt-2 text-sm">{result.reason}</p>
        {result.context?.missing_sources?.length ? (
          <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
            Faltantes: {result.context.missing_sources.join(', ')}
          </p>
        ) : null}
      </section>
    )
  }

  return (
    <div className="space-y-6">
      <section className="card">
        <h2 className="text-lg font-semibold">Respuesta</h2>
        <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{result.answer}</div>
        {result.meta ? (
          <p className="mt-4 text-xs text-[var(--color-ink-muted)]">
            prompt v{String(result.meta.prompt_version)} · rúbrica v{String(result.meta.rubric_version)} ·{' '}
            {String(result.meta.provider)}/{String(result.meta.model)}
          </p>
        ) : null}
      </section>

      <section>
        <h2 className="text-lg font-semibold">Citas y Referencias</h2>
        <ul className="mt-3 space-y-2">
          {result.citations.map((cite) => (
            <li key={cite.id} className="border-l-2 border-[var(--color-primary)] pl-3 text-sm">
              [{cite.index}] {cite.title}
              <span className="ml-2 text-xs text-[var(--color-ink-muted)]">
                {cite.source_type} · {cite.source_label}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
