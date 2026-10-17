import { defineConfig } from '@playwright/test'
import path from 'node:path'
const python=process.env.PYTHON || (process.platform==='win32'?path.resolve('../.venv/Scripts/python.exe'):'python')
export default defineConfig({
  testDir:'./e2e',
  timeout:30000,
  use:{baseURL:'http://127.0.0.1:5173',trace:'retain-on-failure'},
  webServer:[
    {command:`"${python}" -m alembic upgrade head && "${python}" -m backend.seed && "${python}" -m backend.demo_seed && "${python}" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`,cwd:'..',url:'http://127.0.0.1:8000/api/health',reuseExistingServer:!process.env.CI,timeout:120000,env:{DATABASE_URL:'sqlite:///./e2e.db',DEMO_MODE:'true',LOCAL_STT:'false'}},
    {command:'npm run dev -- --host 127.0.0.1',url:'http://127.0.0.1:5173',reuseExistingServer:!process.env.CI,timeout:120000}
  ]
})
