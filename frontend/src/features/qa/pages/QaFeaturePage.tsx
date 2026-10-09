import { Navigate, useParams } from 'react-router-dom'
import { api } from '../../../api/client'
import { FeatureWorkspace } from '../../../features/document'
import { QA_FEATURE_BY_SLUG, QA_SOURCE_OPTIONS } from '../../../features/qa'

export const QaFeaturePage = () => {
  const { slug } = useParams<{ slug: string }>()
  const config = slug ? QA_FEATURE_BY_SLUG[slug] : undefined

  if (!config) {
    return <Navigate to="/qa/regression" replace />
  }

  return (
    <FeatureWorkspace
      eyebrow="QA Tools"
      title={config.title}
      description={config.description}
      uploadTags={config.uploadTags}
      placeholder={config.placeholder}
      defaultQuery={config.defaultQuery}
      showSourceToggles
      sourceOptions={QA_SOURCE_OPTIONS}
      defaultSources={config.defaultSources}
      onRun={({ query, documentIds, chatContext, sources }) =>
        api.runQaFeature(config.feature, {
          query,
          document_ids: documentIds,
          chat_context: chatContext,
          sources,
        })
      }
    />
  )
}
