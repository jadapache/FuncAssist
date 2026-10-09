import { useEffect, useState } from 'react'
import { api } from '../../../api/client'

type JiraProject = {
  id: string
  key: string
  name: string
  selected: boolean
}

type JiraProjectsPanelProps = {
  siteUrl?: string | null
  onSaved: () => void
  onError: (message: string) => void
}

export const JiraProjectsPanel = ({ siteUrl, onSaved, onError }: JiraProjectsPanelProps) => {
  const [projects, setProjects] = useState<JiraProject[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  const loadProjects = async () => {
    setLoading(true)
    try {
      const data = await api.getProjects()
      setProjects(data.projects)
      setSelected(data.projects.filter((project) => project.selected).map((project) => project.key))
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load Jira projects')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadProjects()
  }, [])

  const handleSave = async () => {
    setBusy(true)
    try {
      await api.updateProjects(selected)
      await api.syncIntegration('jira')
      await loadProjects()
      onSaved()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to save project selection')
    } finally {
      setBusy(false)
    }
  }

  const handleAutoSelect = async () => {
    setBusy(true)
    try {
      await api.autoSelectJiraProject()
      await loadProjects()
      onSaved()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Could not auto-select project from site URL')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-5 space-y-4 border-t border-[var(--color-border)] pt-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Jira projects</h3>
          <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
            Features use issues from selected projects only. On connect, we try to match your site URL
            {siteUrl ? (
              <>
                {' '}
                (<code className="text-[10px]">{siteUrl}</code>)
              </>
            ) : null}
            .
          </p>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleAutoSelect()}
          className="btn-secondary text-xs disabled:opacity-50"
        >
          Auto-detect from site URL
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-[var(--color-ink-muted)]">Loading projects…</p>
      ) : projects.length === 0 ? (
        <p className="text-sm text-[var(--color-ink-muted)]">No projects found for this Jira site.</p>
      ) : (
        <div className="max-h-56 space-y-2 overflow-auto rounded-md border border-[var(--color-border)] bg-white p-3">
          {projects.map((project) => (
            <label key={project.key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.includes(project.key)}
                onChange={(event) => {
                  setSelected((prev) =>
                    event.target.checked
                      ? [...prev, project.key]
                      : prev.filter((item) => item !== project.key),
                  )
                }}
              />
              <span>
                <span className="font-medium">{project.key}</span> · {project.name}
              </span>
            </label>
          ))}
        </div>
      )}

      <button
        type="button"
        disabled={busy || loading}
        onClick={() => void handleSave()}
        className="btn-primary disabled:opacity-50"
      >
        Save project selection
      </button>
    </div>
  )
}
