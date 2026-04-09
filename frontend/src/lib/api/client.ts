import { addToast } from '$lib/stores/toast';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const errorText = await resp.text().catch(() => `HTTP ${resp.status}`);
    addToast(`API error: ${errorText}`, 'error');
    throw new Error(`API error: ${resp.status}`);
  }
  return resp.json();
}

export const api = {
  library: {
    getAlbums: (source: string, params?: Record<string, string>) => {
      const qs = params ? `?${new URLSearchParams(params)}` : '';
      return request<any>(`/library/${source}/albums${qs}`);
    },
    getAlbum: (source: string, id: number) =>
      request<any>(`/library/${source}/albums/${id}`),
    refresh: (source: string) =>
      request<any>(`/library/refresh/${source}`, { method: 'POST' }),
    search: (source: string, query: string, params?: Record<string, string>) => {
      const qs = new URLSearchParams({ q: query, ...(params ?? {}) });
      return request<any>(`/library/search/${source}?${qs}`);
    },
    listPlaylists: (source: string) =>
      request<any[]>(`/library/${source}/playlists`),
    getPlaylist: (source: string, id: number) =>
      request<any>(`/library/${source}/playlists/${id}`),
  },
  downloads: {
    getQueue: () => request<any>('/downloads/queue'),
    enqueue: (source: string, albumIds: string[]) =>
      request<any>('/downloads/queue', {
        method: 'POST',
        body: JSON.stringify({ source, album_ids: albumIds }),
      }),
    cancel: (itemId: string) =>
      request<any>(`/downloads/queue/${itemId}`, { method: 'DELETE' }),
    cancelAll: () =>
      request<any>('/downloads/cancel', { method: 'POST' }),
  },
  config: {
    get: () => request<any>('/config'),
    update: (data: Record<string, unknown>) =>
      request<any>('/config', { method: 'PATCH', body: JSON.stringify(data) }),
  },
  auth: {
    status: () => request<any[]>('/auth/status'),
  },
};
