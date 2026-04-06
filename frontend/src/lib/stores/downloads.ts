import { writable } from 'svelte/store';
import { api } from '$lib/api/client';
import { onEvent } from './websocket';

export const queue = writable<any[]>([]);
export const activeCount = writable(0);
export const totalSpeed = writable(0);

export async function loadQueue() {
  const data = await api.downloads.getQueue();
  queue.set(data.items);
  activeCount.set(data.active_count);
  totalSpeed.set(data.total_speed);
}

onEvent('download_progress', (data) => {
  queue.update(items =>
    items.map(item =>
      item.id === data.item_id ? { ...item, ...data } : item
    )
  );
});

onEvent('download_complete', (data) => {
  queue.update(items =>
    items.map(item =>
      item.id === data.item_id ? { ...item, status: 'complete' } : item
    )
  );
});

onEvent('download_failed', (data) => {
  queue.update(items =>
    items.map(item =>
      item.id === data.item_id ? { ...item, status: 'failed' } : item
    )
  );
});
