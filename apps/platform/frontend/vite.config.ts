import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The dashboard talks to the API through /api. In dev that is proxied to the
// FastAPI process; in Docker, nginx does the same job.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': process.env.COPILOT_API ?? 'http://127.0.0.1:8000' },
  },
});
