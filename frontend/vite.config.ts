import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev, Vite serves the UI and forwards /api to FastAPI.
// In production, FastAPI serves the built UI itself, so there's one origin and no CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
