/* API service — all backend calls. */

const BASE = '/api';

async function request<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...(opts?.headers as any) },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }
  return res.json();
}

/* ── Trips ──────────────────────────────── */

export function createTrip(message: string) {
  return request<any>('/trips', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export function getTrip(tripId: string) {
  return request<any>(`/trips/${tripId}`);
}

export function listTrips() {
  return request<{ trips: any[] }>('/trips');
}

export function sendChatMessage(tripId: string, message: string) {
  return request<any>(`/trips/${tripId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export function submitCheckpoint(
  tripId: string,
  checkpoint: string,
  action: string,
  selectedOptionId?: string,
  modifications?: Record<string, any>,
) {
  return request<any>(`/trips/${tripId}/checkpoint`, {
    method: 'POST',
    body: JSON.stringify({
      checkpoint,
      action,
      selected_option_id: selectedOptionId ?? null,
      modifications: modifications ?? null,
    }),
  });
}

export function requestReplan(tripId: string, message: string) {
  return request<any>(`/trips/${tripId}/replan`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

/* ── Export ──────────────────────────────── */

export function getExportHtmlUrl(tripId: string) {
  return `${BASE}/trips/${tripId}/export/html`;
}

export function getExportPdfUrl(tripId: string) {
  return `${BASE}/trips/${tripId}/export/pdf`;
}

/* ── SSE ──────────────────────────────── */

export function createSSEConnection(tripId: string): EventSource {
  return new EventSource(`${BASE}/trips/${tripId}/stream`);
}
