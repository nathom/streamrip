import { writable } from 'svelte/store';
import { api } from '$lib/api/client';

export const albums = writable<any[]>([]);
export const totalAlbums = writable(0);
export const currentSource = writable('qobuz');
export const searchQuery = writable('');
export const sortBy = writable('added_to_library_at');
export const filterStatus = writable('all');
export const selectedAlbum = writable<any | null>(null);

export async function loadAlbums(source: string, params?: Record<string, string>) {
  const data = await api.library.getAlbums(source, params);
  albums.set(data.albums);
  totalAlbums.set(data.total);
}

export async function loadAlbumDetail(source: string, id: number) {
  const data = await api.library.getAlbum(source, id);
  selectedAlbum.set(data);
}
