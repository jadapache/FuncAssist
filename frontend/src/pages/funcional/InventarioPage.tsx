import { FUNCIONAL_FEATURE_BY_SLUG } from '../../constants/funcionalFeatures'
import { AgenticDocumentWorkspace } from '../../components/workspace/AgenticDocumentWorkspace'

export const InventarioPage = () => {
  const config = FUNCIONAL_FEATURE_BY_SLUG['inventario']
  if (!config) {
    return (
      <div className="p-6 text-center text-red-600">
        Configuración no encontrada para el módulo de Inventario.
      </div>
    )
  }
  return <AgenticDocumentWorkspace config={config} />
}

export default InventarioPage
