import { writable } from 'svelte/store';

export interface ToastMessage {
  id: string;
  text: string;
  type: 'success' | 'error' | 'info';
  duration?: number;
}

export const toasts = writable<ToastMessage[]>([]);

export function addToast(text: string, type: 'success' | 'error' | 'info' = 'info', duration = 4000) {
  const id = Math.random().toString(36).slice(2);
  toasts.update(t => [...t, { id, text, type, duration }]);
  if (duration > 0) {
    setTimeout(() => removeToast(id), duration);
  }
}

export function removeToast(id: string) {
  toasts.update(t => t.filter(m => m.id !== id));
}
