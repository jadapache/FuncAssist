import {
  API_BASE,
  getAuthHeaders,
  handleResponse,
  type CorporateTemplate,
  type TemplateDetail,
} from '../../../api/client'

export const templatesApi = {
  getTemplates: () =>
    fetch(`${API_BASE}/api/templates`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{ templates: CorporateTemplate[] }>(r),
    ),

  getTemplateContent: (id: string) =>
    fetch(`${API_BASE}/api/templates/${id}/content`, {
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<TemplateDetail>(r),
    ),

  uploadTemplate: async (file: File, title?: string, module?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)
    if (module) form.append('module', module)
    return fetch(`${API_BASE}/api/templates/upload`, {
      method: 'POST',
      headers: { ...getAuthHeaders() },
      body: form,
    }).then((r) => handleResponse<{ template: CorporateTemplate }>(r))
  },

  updateTemplate: (
    id: string,
    payload: { title?: string; module?: string; tags?: string[]; content?: string },
  ) =>
    fetch(`${API_BASE}/api/templates/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    }).then((r) => handleResponse<{ template: CorporateTemplate }>(r)),

  deleteTemplate: (id: string) =>
    fetch(`${API_BASE}/api/templates/${id}`, {
      method: 'DELETE',
      headers: { ...getAuthHeaders() },
    }).then((r) =>
      handleResponse<{ ok: boolean; template_id: string }>(r),
    ),
}
