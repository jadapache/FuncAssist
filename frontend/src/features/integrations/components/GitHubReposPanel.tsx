import { useEffect, useState } from 'react'
import { api } from '../../../api/client'

type Repo = {
  full_name: string
  name: string
  private: boolean
  selected: boolean
  html_url: string
}

type GitHubReposPanelProps = {
  onSaved: () => void
  onError: (message: string) => void
}

export const GitHubReposPanel = ({ onSaved, onError }: GitHubReposPanelProps) => {
  const [repos, setRepos] = useState<Repo[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [prs, setPrs] = useState<Array<Record<string, unknown>>>([])

  useEffect(() => {
    const load = async () => {
      const data = await api.getRepositories()
      setRepos(data.repositories)
      setSelected(data.repositories.filter((repo) => repo.selected).map((repo) => repo.full_name))
    }
    void load().catch((err) => onError(err instanceof Error ? err.message : 'Failed to load repos'))
  }, [onError])

  const handleSave = async () => {
    setBusy(true)
    try {
      await api.updateRepositories('github', selected)
      onSaved()
      if (selected.length) {
        const prData = await api.getPullRequests()
        setPrs(prData.pull_requests.slice(0, 8))
      } else {
        setPrs([])
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to save repos')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-5 space-y-4 border-t border-[var(--color-line)] pt-5">
      <h3 className="text-sm font-semibold">Repositorios</h3>
      <p className="text-xs text-[var(--color-ink-muted)]">
        Solo los repositorios seleccionados son accesibles para las funcionalidades. Nada se selecciona automáticamente.
      </p>
      <div className="max-h-56 space-y-2 overflow-auto rounded-md border border-[var(--color-line)] bg-white p-3">
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
      <button
        type="button"
        disabled={busy}
        onClick={() => void handleSave()}
        className="btn-primary disabled:opacity-50"
      >
        Guardar selección
      </button>
      {prs.length ? (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-muted)]">
            PRs en vivo (muestra)
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
