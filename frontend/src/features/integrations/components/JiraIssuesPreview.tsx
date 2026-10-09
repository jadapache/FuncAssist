import { useEffect, useState } from 'react'
import { api } from '../../../api/client'

export const JiraIssuesPreview = ({ onError }: { onError: (message: string) => void }) => {
  const [issues, setIssues] = useState<Array<Record<string, unknown>>>([])

  useEffect(() => {
    void api
      .getIssues()
      .then((data) => setIssues(data.issues.slice(0, 10)))
      .catch((err) => onError(err instanceof Error ? err.message : 'Failed to load issues'))
  }, [onError])

  if (!issues.length) {
    return null
  }

  return (
    <div className="mt-5 border-t border-[var(--color-line)] pt-5">
      <h3 className="text-sm font-semibold">Live issues (sample)</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {issues.map((issue) => (
          <li key={String(issue.key)}>
            <span className="font-medium">{String(issue.key)}</span> {String(issue.summary)} ·{' '}
            <span className="text-[var(--color-ink-muted)]">{String(issue.status)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
