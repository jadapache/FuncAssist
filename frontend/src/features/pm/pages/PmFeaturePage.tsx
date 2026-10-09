import { Navigate, useParams, useOutletContext } from 'react-router-dom'
import { FeatureWorkspace } from '../../../features/document'
import { PM_FEATURE_BY_SLUG } from '../../../features/pm'
import { toolsGroupLabel } from '../../../constants/app'

type OutletContext = {
  displayName: string
}

export const PmFeaturePage = () => {
  const { slug } = useParams<{ slug: string }>()
  const { displayName } = useOutletContext<OutletContext>()
  const config = slug ? PM_FEATURE_BY_SLUG[slug] : undefined

  if (!config) {
    return <Navigate to="/pm/standup" replace />
  }

  return (
    <FeatureWorkspace
      eyebrow={toolsGroupLabel(displayName)}
      title={config.title}
      description={config.description}
      uploadTags={config.uploadTags}
      placeholder={config.placeholder}
      defaultQuery={config.defaultQuery}
      showSourceToggles={config.showSourceToggles}
      sourceOptions={config.sourceOptions}
      defaultSources={config.defaultSources}
      onRun={({ query, documentIds, chatContext, sources }) =>
        config.runApi({
          query,
          document_ids: documentIds,
          chat_context: chatContext,
          sources,
        })
      }
    />
  )
}
