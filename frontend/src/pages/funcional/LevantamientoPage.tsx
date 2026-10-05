import { FUNCIONAL_FEATURE_BY_SLUG } from '../../constants/funcionalFeatures'
import { AgenticDocumentWorkspace } from '../../components/workspace/AgenticDocumentWorkspace'

export const LevantamientoPage = () => {
  const config = FUNCIONAL_FEATURE_BY_SLUG['levantamiento']
  if (!config) {
    return (
      <div className="p-6 text-center text-red-600">
        Configuración no encontrada para el módulo de Levantamiento.
      </div>
    )
  }
  return <AgenticDocumentWorkspace config={config} />
}

export default LevantamientoPage
