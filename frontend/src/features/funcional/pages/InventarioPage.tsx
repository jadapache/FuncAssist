import { FUNCIONAL_FEATURE_BY_SLUG } from '../../../features/funcional'
import { AgenticDocumentWorkspace } from '../../../features/document'

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
