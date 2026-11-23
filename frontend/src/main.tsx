import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { installRandomUUIDPolyfill } from './core/browser/secureContext'
import './index.css'

// On plain http://<server IP> (corporate LAN without HTTPS) browsers do not provide
// crypto.randomUUID, which the app uses for message and artifact ids.
installRandomUUIDPolyfill()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
