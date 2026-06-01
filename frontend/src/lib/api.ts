import type { Strategy, StrategyCreateRequest, StrategyRunResponse, TaskStatusResponse } from './types'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const TENANT_ID = process.env.NEXT_PUBLIC_DEMO_TENANT_ID ?? 'demo-tenant-001'
const USER_ID   = process.env.NEXT_PUBLIC_DEMO_USER_ID   ?? 'demo-user-001'

function headers(user = false): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-Tenant-Id': TENANT_ID,
    ...(user ? { 'X-User-Id': USER_ID } : {}),
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  listStrategies: () =>
    req<Strategy[]>('/v1/strategies', { headers: headers() }),

  getStrategy: (id: string) =>
    req<Strategy>(`/v1/strategies/${id}`, { headers: headers() }),

  createStrategy: (data: StrategyCreateRequest) =>
    req<Strategy>('/v1/strategies', {
      method: 'POST',
      headers: headers(true),
      body: JSON.stringify(data),
    }),

  runStrategy: (id: string, dryRun = true) =>
    req<StrategyRunResponse>(`/v1/strategies/${id}/runs`, {
      method: 'POST',
      headers: headers(true),
      body: JSON.stringify({ dry_run: dryRun }),
    }),

  getTaskStatus: (taskId: string) =>
    req<TaskStatusResponse>(`/v1/tasks/${taskId}`, { headers: headers() }),
}
