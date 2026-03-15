/**
 * ConnectorOS Scout — API Client
 *
 * Centralized API calls with error handling.
 * Security: all calls go through the Vite proxy (no CORS leaks).
 */

const BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

async function fetchJSON(url, options = {}) {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error: ${res.status}`);
  }

  return res.json();
}

// ── Pipeline ────────────────────────────────────────────────
export const startPipeline = (payload = {}) =>
  fetchJSON('/pipeline/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const stopPipeline = () =>
  fetchJSON('/pipeline/stop', { method: 'POST' });

export const getPipelineStatus = () => fetchJSON('/pipeline/status');
export const getPipelineRuns = (limit = 20) => fetchJSON(`/pipeline/runs?limit=${limit}`);
export const getRunPreview = (runId) => fetchJSON(`/pipeline/runs/${runId}/preview`);
export const getPipelineStream = () => new EventSource(BASE + '/pipeline/stream');

// ── Leads ───────────────────────────────────────────────────
export const getLeads = (params = {}) => {
  const query = new URLSearchParams(params).toString();
  return fetchJSON(`/leads?${query}`);
};
export const getLeadStats = () => fetchJSON('/leads/stats');
export const getLead = (id) => fetchJSON(`/leads/${id}`);
export const getRunLeads = (runId) => fetchJSON(`/leads/run/${runId}`);
export const updateLead = (id, data) =>
  fetchJSON(`/leads/${id}`, { method: 'PATCH', body: JSON.stringify(data) });

// ── Agencies ────────────────────────────────────────────────
export const getAgencies = () => fetchJSON('/agencies');
export const createAgency = (data) =>
  fetchJSON('/agencies', { method: 'POST', body: JSON.stringify(data) });
export const getAgency = (id) => fetchJSON(`/agencies/${id}`);
export const updateAgency = (id, data) =>
  fetchJSON(`/agencies/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
export const deleteAgency = (id) =>
  fetchJSON(`/agencies/${id}`, { method: 'DELETE' });

// ── Search ──────────────────────────────────────────────────
export const searchCompany = (domain) =>
  fetchJSON('/search/company', { method: 'POST', body: JSON.stringify({ domain }) });
export const searchContact = (domain, title) =>
  fetchJSON('/search/contact', { method: 'POST', body: JSON.stringify({ domain, title }) });
export const searchMarket = (market, max_results = 20) =>
  fetchJSON('/search/market', { method: 'POST', body: JSON.stringify({ market, max_results }) });
export const getSearchHistory = () => fetchJSON('/search/history');

// ── Analytics ───────────────────────────────────────────────
export const getOverview = () => fetchJSON('/analytics/overview');
export const getTrends = (days = 30) => fetchJSON(`/analytics/trends?days=${days}`);
export const getDistributions = () => fetchJSON('/analytics/distributions');
export const getIndustries = () => fetchJSON('/analytics/industries');
export const getCostBreakdown = (days = 30) => fetchJSON(`/analytics/cost-breakdown?days=${days}`);

// ── Notifications ───────────────────────────────────────────
export const getNotifications = (unread = false) =>
  fetchJSON(`/notifications?unread_only=${unread}`);
export const getUnreadCount = () => fetchJSON('/notifications/count');
export const markRead = (id) =>
  fetchJSON(`/notifications/${id}/read`, { method: 'PATCH' });
export const dismissNotification = (id) =>
  fetchJSON(`/notifications/${id}/dismiss`, { method: 'PATCH' });
export const markAllRead = () =>
  fetchJSON('/notifications/mark-all-read', { method: 'POST' });

// ── Settings ────────────────────────────────────────────────
export const getSettings = () => fetchJSON('/settings');
export const updateSettings = (updates) =>
  fetchJSON('/settings', { method: 'PATCH', body: JSON.stringify(updates) });
export const testApiKey = (apiName, apiKey) =>
  fetchJSON(`/settings/test-api-key?api_name=${apiName}&api_key=${apiKey}`, { method: 'POST' });

// ── Health ──────────────────────────────────────────────────
export const healthCheck = () => fetchJSON('/health');
