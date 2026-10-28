import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Manual chunks function for Vite 8 / Rolldown
function manualChunks(id: string) {
  // React core - loaded immediately
  if (id.includes('react-dom') || id.includes('react-router-dom')) {
    return 'react-vendor'
  }
  // Univer document editor - large but needed for document features
  if (id.includes('@univerjs/')) {
    return 'univer'
  }
  // AI/ML dependencies - lazy loaded
  if (id.includes('@mlc-ai/web-llm') || id.includes('@huggingface/transformers')) {
    return 'ai-ml'
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    cssMinify: 'esbuild',
    // Increase chunk size warning limit to identify truly large chunks
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
  // Optimize worker bundling
  worker: {
    format: 'es',
  },
  // Optimize WASM loading
  optimizeDeps: {
    exclude: ['@mlc-ai/web-llm', '@huggingface/transformers'],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:6728',
        changeOrigin: true,
      },
    },
  },
})
