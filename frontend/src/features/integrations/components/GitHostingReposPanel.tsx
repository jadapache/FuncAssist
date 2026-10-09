import { useEffect, useState } from 'react'
import { api } from '../../../api/client'

type Repo = {
  full_name: string
  name: string
  private: boolean
  selected: boolean
  html_url: string
}

type GitHostingReposPanelProps = {
  integrationId: 'github' | 'gitlab'
  heading: string
  description: string
  onSaved: () => void
  onError: (message: string) => void
}

export const GitHostingReposPanel = ({
  integrationId,
  heading,
  description,
  onSaved,
  onError,
}: GitHostingReposPanelProps) => {
  const [repos, setRepos] = useState<Repo[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [prs, setPrs] = useState<Array<Record<string, unknown>>>([])

  const loadRepos = async () => {
    setLoading(true)
    try {
      const data = await api.getRepositories(integrationId)
      setRepos(data.repositories)
      setSelected(data.repositories.filter((repo) => repo.selected).map((repo) => repo.full_name))
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load repositories')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadRepos()
  }, [integrationId])

  const handleSave = async () => {
    setBusy(true)
    try {
      await api.updateRepositories(integrationId, selected)
      if (selected.length) {
        await api.syncIntegration(integrationId)
        const prData = await api.getPullRequests(integrationId)
        setPrs(prData.pull_requests.slice(0, 8))
      } else {
        setPrs([])
      }
      onSaved()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to save selection')
    } finally {
      setBusy(false)
    }
  }

  const prLabel = integrationId === 'gitlab' ? 'MRs' : 'PRs'

  return (
    <div className="mt-5 space-y-4 border-t border-[var(--color-border)] pt-5">
      <h3 className="text-sm font-semibold">{heading}</h3>
      <p className="text-xs text-[var(--color-ink-muted)]">{description}</p>

      {loading ? (
        <p className="text-sm text-[var(--color-ink-muted)]">Cargando repositorios...</p>
      ) : repos.length === 0 ? (
        <p className="text-sm text-[var(--color-ink-muted)]">
          No se encontraron repositorios. Comprueba que tu token o aplicación OAuth tenga acceso a los repositorios de esta cuenta.
        </p>
      ) : (
        <div className="max-h-56 space-y-2 overflow-auto rounded-md border border-[var(--color-border)] bg-white p-3">
          {repos.map((repo) => (
            <label key={repo.full_name} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.includes(repo.full_name)}
                onChange={(event) => {
                  setSelected((prev) =>
                    event.target.checked
                      ? [...prev, repo.full_name]
                      : prev.filter((item) => item !== repo.full_name),
                  )
                }}
              />
              <span>{repo.full_name}</span>
              {repo.private ? <span className="text-xs text-[var(--color-ink-muted)]">private</span> : null}
            </label>
          ))}
        </div>
      )}

      <button
        type="button"
        disabled={busy || loading || repos.length === 0}
        onClick={() => void handleSave()}
        className="btn-primary disabled:opacity-50"
      >
        Guardar selección
      </button>

      {prs.length ? (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-muted)]">
            Live {prLabel} (sample)
          </h4>
          <ul className="mt-2 space-y-1 text-sm">
            {prs.map((pr) => (
              <li key={`${pr.repo}-${pr.number}`}>
                #{String(pr.number)} {String(pr.title)} · {String(pr.repo)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
