import {
  API_BASE,
  handleResponse,
  type CorporateTemplate,
  type TemplateDetail,
} from '../../../api/client'

export const templatesApi = {
  getTemplates: () =>
    fetch(`${API_BASE}/api/templates`).then((r) =>
      handleResponse<{ templates: CorporateTemplate[] }>(r),
    ),

  getTemplateContent: (id: string) =>
    fetch(`${API_BASE}/api/templates/${id}/content`).then((r) =>
      handleResponse<TemplateDetail>(r),
    ),

  uploadTemplate: async (file: File, title?: string, module?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)
    if (module) form.append('module', module)
    return fetch(`${API_BASE}/api/templates/upload`, { method: 'POST', body: form }).then((r) =>
      handleResponse<{ template: CorporateTemplate }>(r),
    )
  },

  updateTemplate: (
    id: string,
    payload: { title?: string; module?: string; tags?: string[]; content?: string },
  ) =>
    fetch(`${API_BASE}/api/templates/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<{ template: CorporateTemplate }>(r)),

  deleteTemplate: (id: string) =>
    fetch(`${API_BASE}/api/templates/${id}`, { method: 'DELETE' }).then((r) =>
      handleResponse<{ ok: boolean; template_id: string }>(r),
    ),
}
