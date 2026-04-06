import { writable } from 'svelte/store';

type EventHandler = (data: Record<string, unknown>) => void;
const handlers = new Map<string, EventHandler[]>();

let socket: WebSocket | null = null;

export function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  socket = new WebSocket(`${protocol}//${window.location.host}/api/ws`);

  socket.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    const eventHandlers = handlers.get(msg.type) || [];
    for (const handler of eventHandlers) {
      handler(msg.data);
    }
  };

  socket.onclose = () => {
    setTimeout(connectWebSocket, 3000);
  };
}

export function onEvent(type: string, handler: EventHandler) {
  if (!handlers.has(type)) handlers.set(type, []);
  handlers.get(type)!.push(handler);
}

export const connected = writable(false);
