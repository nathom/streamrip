<script lang="ts">
  import type { Snippet } from 'svelte';
  import '$lib/design-system/tokens.css';
  import { currentSource } from '$lib/stores/library';
  import { activeCount } from '$lib/stores/downloads';
  import { onMount } from 'svelte';
  import { connectWebSocket, onEvent } from '$lib/stores/websocket';
  import { api } from '$lib/api/client';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { addToast } from '$lib/stores/toast';
  import Toast from '$lib/components/Toast.svelte';

  let { children }: { children: Snippet } = $props();

  let activePage = $derived(page.url.pathname.split('/')[1] || 'library');
  let source = $derived($currentSource);
  let downloadCount = $derived($activeCount);
  let authStatuses = $state<any[]>([]);
  let sourceAuth = $derived(authStatuses.find(a => a.source === source));
  let isConnected = $derived(sourceAuth?.authenticated ?? false);

  function setSource(s: string) {
    $currentSource = s;
  }

  function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
  }

  async function loadAuthStatus() {
    try {
      authStatuses = await api.auth.status();
    } catch {
      // ignore
    }
  }

  function isInputFocused(): boolean {
    const el = document.activeElement;
    if (!el) return false;
    const tag = el.tagName.toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || (el as HTMLElement).isContentEditable;
  }

  function handleKeydown(e: KeyboardEvent) {
    // / or Ctrl+K → navigate to /search, focus search input
    if (e.key === '/' || (e.ctrlKey && e.key === 'k')) {
      if (e.key === '/' && isInputFocused()) return;
      e.preventDefault();
      goto('/search').then(() => {
        const input = document.querySelector<HTMLInputElement>('.search-input');
        input?.focus();
      });
      return;
    }

    // Escape → close album detail panel
    if (e.key === 'Escape') {
      window.dispatchEvent(new CustomEvent('close-detail'));
      return;
    }

    // Number shortcuts — only when no input is focused
    if (isInputFocused()) return;

    if (e.key === '1') goto('/library');
    else if (e.key === '2') goto('/search');
    else if (e.key === '3') goto('/downloads');
    else if (e.key === '4') goto('/settings');
  }

  onMount(() => {
    // Task 2: Persist theme preference
    const saved = localStorage.getItem('theme') ?? 'dark';
    document.documentElement.setAttribute('data-theme', saved);

    if (typeof window !== 'undefined') {
      connectWebSocket();
    }
    loadAuthStatus();

    // Task 1: Wire up WebSocket events to toasts
    onEvent('download_complete', (data) => {
      const title = (data.title as string) ?? 'Unknown';
      addToast(`Downloaded: ${title}`, 'success');
    });

    onEvent('download_failed', (data) => {
      const title = (data.title as string) ?? 'Unknown';
      addToast(`Download failed: ${title}`, 'error');
    });

    onEvent('library_updated', (data) => {
      const count = (data.new_count as number) ?? 0;
      addToast(`Library synced: ${count} new albums`, 'info');
    });

    // Task 3: Keyboard shortcuts
    window.addEventListener('keydown', handleKeydown);
    return () => {
      window.removeEventListener('keydown', handleKeydown);
    };
  });
</script>

<div class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-logo">
        <span class="logo-accent">◆</span> streamrip
      </div>
      <div class="sidebar-version">v3.0.0 — library manager</div>
    </div>

    <div class="source-selector">
      <div class="source-label">Source</div>
      <div class="source-tabs">
        <button class="source-tab" class:active={source === 'qobuz'} onclick={() => setSource('qobuz')}>Qobuz</button>
        <button class="source-tab" class:active={source === 'tidal'} onclick={() => setSource('tidal')}>Tidal</button>
      </div>
    </div>

    <nav class="sidebar-nav">
      <a href="/library" class="nav-item" class:active={activePage === 'library' || activePage === ''}>
        <span class="nav-icon">◧</span> Library
      </a>
      <a href="/search" class="nav-item" class:active={activePage === 'search'}>
        <span class="nav-icon">◆</span> Search
      </a>
      <a href="/downloads" class="nav-item" class:active={activePage === 'downloads'}>
        <span class="nav-icon">▸</span> Downloads
        {#if downloadCount > 0}
          <span class="nav-badge">{downloadCount}</span>
        {/if}
      </a>
      <a href="/settings" class="nav-item" class:active={activePage === 'settings'}>
        <span class="nav-icon">★</span> Settings
      </a>
    </nav>

    <div class="sidebar-footer">
      <div class="connection-status">
        <span class="status-dot" class:disconnected={!isConnected}></span>
        {source.charAt(0).toUpperCase() + source.slice(1)} {isConnected ? 'connected' : 'not connected'}
      </div>
      <button class="theme-toggle" onclick={toggleTheme}>░ toggle theme</button>
    </div>
  </aside>

  <main class="main-content">
    {@render children()}
  </main>
</div>

<Toast />

<style>
  .app-shell {
    display: grid;
    grid-template-columns: 220px 1fr;
    height: 100vh;
  }

  .sidebar {
    background: var(--canvas-inset);
    border-right: 2px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }

  .sidebar-header {
    padding: var(--space-5) var(--space-5) var(--space-4);
    border-bottom: 2px solid var(--border);
  }

  .sidebar-logo {
    font-size: var(--text-xl);
    font-weight: 800;
    letter-spacing: var(--tracking-tight);
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .logo-accent { color: var(--accent); }

  .sidebar-version {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--text-tertiary);
    letter-spacing: var(--tracking-mono);
    margin-top: var(--space-1);
  }

  .source-selector {
    padding: var(--space-3) var(--space-4);
    border-bottom: 2px solid var(--border);
  }

  .source-label {
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    color: var(--text-tertiary);
    margin-bottom: var(--space-2);
  }

  .source-tabs {
    display: flex;
    border: 2px solid var(--border);
  }

  .source-tab {
    flex: 1;
    padding: var(--space-2) var(--space-3);
    font-family: var(--font-family);
    font-size: var(--text-sm);
    font-weight: 600;
    text-align: center;
    cursor: pointer;
    background: var(--canvas-raised);
    color: var(--text-secondary);
    border: none;
    border-radius: 0;
  }
  .source-tab + .source-tab { border-left: 2px solid var(--border); }
  .source-tab.active { background: var(--accent); color: var(--text-inverse); font-weight: 700; }

  .sidebar-nav { padding: var(--space-3) 0; flex: 1; }

  .nav-item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-secondary);
    border-left: 3px solid transparent;
    text-decoration: none;
  }
  .nav-item:hover { background: var(--pop-subtle); color: var(--text-primary); transition: background-color 80ms; }
  .nav-item.active { font-weight: 700; color: var(--accent); background: var(--accent-subtle); border-left-color: var(--accent); }

  .nav-icon { font-size: var(--text-base); width: 20px; text-align: center; }

  .nav-badge {
    margin-left: auto;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 700;
    padding: 1px var(--space-2);
    background: var(--pop);
    color: var(--text-inverse);
    border: 1.5px solid var(--border);
  }

  .sidebar-footer {
    padding: var(--space-3) var(--space-4);
    border-top: 2px solid var(--border);
  }

  .connection-status {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
  }

  .status-dot {
    width: 8px;
    height: 8px;
    background: var(--positive);
    border: 1.5px solid var(--border);
  }
  .status-dot.disconnected {
    background: var(--destructive);
  }

  .theme-toggle {
    margin-top: var(--space-2);
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-tertiary);
    cursor: pointer;
    background: none;
    border: none;
    padding: var(--space-1) 0;
    letter-spacing: var(--tracking-mono);
  }
  .theme-toggle:hover { color: var(--text-primary); }

  .main-content {
    overflow-y: auto;
    padding: var(--space-6) var(--space-8);
    background: var(--canvas);
  }
</style>
