// ============================================================
// Typed API client for all backend endpoints.
// Base URL: empty string — Vite proxy handles /api -> localhost:8000
// All functions throw on non-2xx responses.
// ============================================================

import type {
  Profile, ProfileCreate, ProfileUpdate, StrategyType,
  TrainingStatus, TrainingLogEntry,
  Trade, TradeStats,
  SystemStatus, HealthCheck, PDTStatus, ErrorLogEntry,
  BacktestRequest, BacktestResult,
  TradingStatusResponse, TradingStartResponse, TradingStopResponse,
  StartableProfile,
  FeatureImportanceResponse,
  SignalLogEntry,
  V2SignalLogEntry,
  ModelHealthResponse,
  TrainingQueueStatus,
  LearningStateResponse,
  ResumeResponse,
  RegimeResponse,
  ScannerResponse,
  EquityCurveResponse,
} from '../types/api';

const BASE = '';

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const { headers, ...rest } = options ?? {};
  const method = options?.method ?? 'GET';
  const defaultHeaders: Record<string, string> = method !== 'GET'
    ? { 'Content-Type': 'application/json' }
    : {};
  const res = await fetch(`${BASE}${path}`, {
    ...rest,
    headers: { ...defaultHeaders, ...headers },
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
    strategyTypes: () =>
      request<StrategyType[]>('/api/profiles/strategy-types'),
  },

  models: {
    train: (profileId: string, modelType?: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/train`, {
        method: 'POST',
        body: JSON.stringify({ model_type: modelType ?? 'xgboost' }),
      }),
    retrain: (profileId: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/retrain`, { method: 'POST' }),
    status: (profileId: string) =>
      request<TrainingStatus>(`/api/models/${profileId}/status`),
    logs: (profileId: string, limit = 50) =>
      request<TrainingLogEntry[]>(`/api/models/${profileId}/logs?limit=${limit}`),
    clearLogs: (profileId: string) =>
      request<{ status: string }>(`/api/models/${profileId}/logs`, { method: 'DELETE' }),
    importance: (profileId: string) =>
      request<FeatureImportanceResponse>(`/api/models/${profileId}/importance`),
  },

  trades: {
    list: (params?: { profile_id?: string; status?: string; symbol?: string; setup_type?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.profile_id) q.set('profile_id', params.profile_id);
      if (params?.status) q.set('status', params.status);
      if (params?.symbol) q.set('symbol', params.symbol);
      if (params?.setup_type) q.set('setup_type', params.setup_type);
      if (params?.limit) q.set('limit', String(params.limit));
      return request<Trade[]>(`/api/trades${q.toString() ? `?${q}` : ''}`);
    },
    active: () =>
      request<Trade[]>('/api/trades/active'),
    stats: (profileId?: string) =>
      request<TradeStats>(`/api/trades/stats${profileId ? `?profile_id=${profileId}` : ''}`),
    exportUrl: (profileId?: string) =>
      `${BASE}/api/trades/export${profileId ? `?profile_id=${profileId}` : ''}`,
    equityCurve: (days?: number) =>
      request<EquityCurveResponse>(`/api/trades/equity-curve${days ? `?days=${days}` : ''}`),
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
    clearErrors: () =>
      request<{ status: string }>('/api/system/errors', { method: 'DELETE' }),
    modelHealth: () =>
      request<ModelHealthResponse>('/api/system/model-health'),
    trainingQueue: () =>
      request<TrainingQueueStatus>('/api/system/training-queue'),
  },

  learning: {
    state: () =>
      request<LearningStateResponse>('/api/learning/state'),
    resume: (profileName: string) =>
      request<ResumeResponse>(`/api/learning/resume/${profileName}`, { method: 'POST' }),
  },

  context: {
    regime: () =>
      request<RegimeResponse>('/api/context/regime'),
  },

  scanner: {
    active: () =>
      request<ScannerResponse>('/api/scanner/active'),
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

  trading: {
    status: () =>
      request<TradingStatusResponse>('/api/trading/status'),
    start: (profileIds: string[]) =>
      request<TradingStartResponse>('/api/trading/start', {
        method: 'POST',
        body: JSON.stringify({ profile_ids: profileIds }),
      }),
    stop: (profileIds?: string[]) =>
      request<TradingStopResponse>('/api/trading/stop', {
        method: 'POST',
        body: JSON.stringify({ profile_ids: profileIds ?? null }),
      }),
    restart: (profileIds: string[]) =>
      request<TradingStartResponse>('/api/trading/restart', {
        method: 'POST',
        body: JSON.stringify({ profile_ids: profileIds }),
      }),
    startableProfiles: () =>
      request<StartableProfile[]>('/api/trading/startable-profiles'),
    resetErrors: () =>
      request<{ reset: string[]; count: number }>('/api/trading/reset-errors', { method: 'POST' }),
  },

  signals: {
    list: (profileId: string, limit = 50, since?: string) => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (since) params.set('since', since);
      return request<SignalLogEntry[]>(`/api/signals/${profileId}?${params}`);
    },
    exportUrl: (profileId?: string) =>
      `${BASE}/api/signals/export${profileId ? `?profile_id=${profileId}` : ''}`,
  },

  v2signals: {
    list: (params?: { profile_name?: string; symbol?: string; entered?: number; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.profile_name) q.set('profile_name', params.profile_name);
      if (params?.symbol) q.set('symbol', params.symbol);
      if (params?.entered !== undefined) q.set('entered', String(params.entered));
      q.set('limit', String(params?.limit ?? 200));
      return request<V2SignalLogEntry[]>(`/api/v2signals?${q}`);
    },
    exportUrl: (params?: { profile_name?: string; symbol?: string; entered?: number }) => {
      const q = new URLSearchParams();
      if (params?.profile_name) q.set('profile_name', params.profile_name);
      if (params?.symbol) q.set('symbol', params.symbol);
      if (params?.entered !== undefined) q.set('entered', String(params.entered));
      return `${BASE}/api/v2signals/export${q.toString() ? `?${q}` : ''}`;
    },
    dailySummaryUrl: (targetDate?: string) =>
      `${BASE}/api/v2signals/daily-summary${targetDate ? `?date=${targetDate}` : ''}`,
  },
};
