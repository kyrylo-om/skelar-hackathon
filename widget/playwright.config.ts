import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

// The smoke test runs the real stack: CloudBox mock (the host site), the execution server, Django in
// MCP mode with the mock LLM, and the widget. Servers already running on these ports are reused, so
// they must be started the same way (see DESIGN.md). Python comes from the repo's virtualenvs.
const repo = resolve(import.meta.dirname, '..')
const scratch = resolve(import.meta.dirname, '.e2e')
const secrets = {
  EXECUTION_SECRET: 'e2e-execution-secret',
  EXECUTION_SERVICE_KEY: 'e2e-service-key',
  CLOUDBOX_API_KEY: 'cloudbox-dev-key',
  SHOPX_API_KEY: 'shopx-dev-key',
}

export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  use: { baseURL: 'http://127.0.0.1:9201' },
  webServer: [
    {
      command: `${repo}/execution/.venv/bin/python -m mocks.cloudbox`,
      cwd: repo,
      url: 'http://127.0.0.1:9201/portal/customers',
      reuseExistingServer: true,
    },
    {
      command: `${repo}/execution/.venv/bin/python -m execution`,
      cwd: repo,
      port: 9000,
      env: { ...secrets, EXECUTION_AUDIT_LOG: `${scratch}/audit.jsonl` },
      reuseExistingServer: true,
    },
    {
      command:
        '.venv/bin/python manage.py migrate -v0 && .venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload',
      cwd: `${repo}/backend`,
      url: 'http://127.0.0.1:8000/api/health/',
      env: {
        ...secrets,
        DATABASE_URL: `sqlite:///${scratch}/db.sqlite3`,
        LLM_PROVIDER: 'mock',
        ORCHESTRATOR_GATEWAY: 'mcp',
        WIDGET_SECRETS: 'cloudbox=cloudbox-widget-dev-secret',
      },
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'npx vite build -c vite.loader.config.ts && npx vite',
      url: 'http://127.0.0.1:5174/widget.js',
      reuseExistingServer: true,
    },
  ],
})
