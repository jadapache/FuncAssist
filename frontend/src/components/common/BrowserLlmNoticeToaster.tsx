import { useEffect } from 'react'
import { useToast } from '../../context/ToastContext'
import { subscribeBrowserLlmNotices } from '../../features/ai/services/browserLlmNotices'

/** Shows non-fatal notices of the in-browser LLM (e.g. it switched to a lighter model) as toasts. */
export const BrowserLlmNoticeToaster = () => {
  const { toast } = useToast()

  useEffect(
    () =>
      subscribeBrowserLlmNotices((notice) => {
        toast.warning(notice.message, notice.title, 9000)
      }),
    [toast],
  )

  return null
}
