import { writable } from 'svelte/store';
import { api } from '$lib/api/client';
import { onEvent } from './websocket';

export const queue = writable<any[]>([]);
export const activeCount = writable(0);
export const totalSpeed = writable(0);

// Exported so components can subscribe to download_complete events
export const lastCompletedDownload = writable<Record<string, unknown> | null>(null);

/**
 * Per-track status for albums currently being downloaded.
 *
 * Keyed by ``source_album_id`` so multiple concurrent downloads (one
 * Qobuz, one Tidal) don't clobber each other.  The value is the latest
 * ``track_statuses`` array from the most recent ``download_progress``
 * event for that album:
 *
 *     [{num, name, status: 'downloading'|'complete'|'failed', progress}]
 *
 * AlbumDetail subscribes to this so each track row can update live as
 * the SDK reports per-track progress callbacks, instead of waiting for
 * the album-level ``download_complete`` event to refetch tracks.
 */
export const liveTrackStatuses = writable<Record<string, any[]>>({});

let loadQueueDebounce: ReturnType<typeof setTimeout> | null = null;

export async function loadQueue() {
  // Debounce — multiple events can fire simultaneously
  if (loadQueueDebounce) clearTimeout(loadQueueDebounce);
  loadQueueDebounce = setTimeout(async () => {
    try {
      const data = await api.downloads.getQueue();
      queue.set(data.items);
      activeCount.set(data.active_count);
      totalSpeed.set(data.total_speed);
    } catch {
      // ignore — API may be unavailable briefly
    }
  }, 300);
}

onEvent('download_progress', (data) => {
  queue.update(items => {
    const updated = items.map(item =>
      item.id === data.item_id ? { ...item, ...data } : item
    );
    // Update speed from all downloading items
    const downloading = updated.filter(i => i.status === 'downloading');
    totalSpeed.set(downloading.reduce((sum: number, i: any) => sum + (i.speed ?? 0), 0));
    activeCount.set(downloading.length);
    return updated;
  });

  // Mirror per-track statuses into liveTrackStatuses keyed by source_album_id
  // so AlbumDetail can render live progress without subscribing to the queue.
  // The progress event itself doesn't carry source_album_id directly, so we
  // look it up from the queue snapshot we just updated.
  const trackStatuses = (data as any).track_statuses;
  if (Array.isArray(trackStatuses) && trackStatuses.length > 0) {
    queue.update(items => {
      const item = items.find(i => i.id === (data as any).item_id);
      if (item?.source_album_id) {
        liveTrackStatuses.update(map => ({
          ...map,
          [String(item.source_album_id)]: trackStatuses,
        }));
      }
      return items;
    });
  }
});

onEvent('download_complete', (data) => {
  queue.update(items =>
    items.map(item =>
      item.id === data.item_id ? { ...item, status: 'complete' } : item
    )
  );
  // Drop live track statuses for this album so the next refetch gets
  // the canonical DB state instead of the stale in-progress map.
  queue.update(items => {
    const item = items.find(i => i.id === (data as any).item_id);
    if (item?.source_album_id) {
      liveTrackStatuses.update(map => {
        const next = { ...map };
        delete next[String(item.source_album_id)];
        return next;
      });
    }
    return items;
  });
  // Refresh full queue state from server after completion
  loadQueue();
  // Notify subscribers (e.g. AlbumDetail) about the completed download
  // AlbumDetail subscribes to this and re-fetches the album data
  lastCompletedDownload.set(data);
});

onEvent('download_failed', (data) => {
  queue.update(items =>
    items.map(item =>
      item.id === data.item_id ? { ...item, status: 'failed' } : item
    )
  );
  // Refresh full queue state from server after failure
  loadQueue();
});
