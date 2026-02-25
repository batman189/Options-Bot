// ============================================================
// Typed API client for all backend endpoints.
// Base URL: empty string — Vite proxy handles /api -> localhost:8000
// All functions throw on non-2xx responses.
// ============================================================

import type {
  Profile, ProfileCreate, ProfileUpdate,
  TrainingStatus, ModelMetrics, TrainingLogEntry,
  Trade, TradeStats,
  SystemStatus, HealthCheck, PDTStatus, ErrorLogEntry,
  BacktestRequest, BacktestResult,
} from '../types/api';

const BASE = '';

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${options?.method ?? 'GET'} ${path} → ${res.status}: ${body}`);
  }
  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// -------------------------
// Profiles
// -------------------------
export const api = {
  profiles: {
    list: () =>
      request<Profile[]>('/api/profiles'),
    get: (id: string) =>
      request<Profile>(`/api/profiles/${id}`),
    create: (body: ProfileCreate) =>
      request<Profile>('/api/profiles', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: ProfileUpdate) =>
      request<Profile>(`/api/profiles/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    delete: (id: string) =>
      request<void>(`/api/profiles/${id}`, { method: 'DELETE' }),
    activate: (id: string) =>
      request<Profile>(`/api/profiles/${id}/activate`, { method: 'POST' }),
    pause: (id: string) =>
      request<Profile>(`/api/profiles/${id}/pause`, { method: 'POST' }),
  },

  models: {
    get: (profileId: string) =>
      request<ModelMetrics>(`/api/models/${profileId}`),
    train: (profileId: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/train`, { method: 'POST' }),
    retrain: (profileId: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/retrain`, { method: 'POST' }),
    status: (profileId: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/status`),
    metrics: (profileId: string) =>
      request<ModelMetrics>(`/api/models/${profileId}/metrics`),
    logs: (profileId: string, limit = 50) =>
      request<TrainingLogEntry[]>(`/api/models/${profileId}/logs?limit=${limit}`),
  },

  trades: {
    list: (params?: { profile_id?: string; status?: string; symbol?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.profile_id) q.set('profile_id', params.profile_id);
      if (params?.status) q.set('status', params.status);
      if (params?.symbol) q.set('symbol', params.symbol);
      if (params?.limit) q.set('limit', String(params.limit));
      return request<Trade[]>(`/api/trades${q.toString() ? `?${q}` : ''}`);
    },
    get: (id: string) =>
      request<Trade>(`/api/trades/${id}`),
    active: () =>
      request<Trade[]>('/api/trades/active'),
    stats: (profileId?: string) =>
      request<TradeStats>(`/api/trades/stats${profileId ? `?profile_id=${profileId}` : ''}`),
    exportUrl: (profileId?: string) =>
      `${BASE}/api/trades/export${profileId ? `?profile_id=${profileId}` : ''}`,
  },

  system: {
    health: () =>
      request<HealthCheck>('/api/system/health'),
    status: () =>
      request<SystemStatus>('/api/system/status'),
    pdt: () =>
      request<PDTStatus>('/api/system/pdt'),
    errors: (limit = 50) =>
      request<ErrorLogEntry[]>(`/api/system/errors?limit=${limit}`),
  },

  backtest: {
    run: (profileId: string, body: BacktestRequest) =>
      request<BacktestResult>(`/api/backtest/${profileId}`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    results: (profileId: string) =>
      request<BacktestResult>(`/api/backtest/${profileId}/results`),
  },
};
