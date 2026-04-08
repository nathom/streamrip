<script lang="ts">
  import { onMount } from 'svelte';
  import SyncDiff from '$lib/components/SyncDiff.svelte';
  import { currentSource } from '$lib/stores/library';
  import { api } from '$lib/api/client';

  let source = $derived($currentSource);

  let loading = $state(false);
  let syncing = $state(false);
  let syncResult = $state<string | null>(null);

  let stats = $state({ inLibrary: 0, downloaded: 0, newCount: 0, missing: 0 });
  let newAlbums = $state<any[]>([]);
  let removedAlbums = $state<any[]>([]);
  let lastSync = $state<string | null>(null);
  let syncHistory = $state<any[]>([]);

  async function loadSyncStatus() {
    loading = true;
    try {
      const diff = await fetch(`/api/sync/status/${source}`).then(r => r.json());
      newAlbums = (diff.new_albums || []).map((a: any, i: number) => ({
        id: i,
        title: a.title || 'Unknown',
        artist: a.artist || 'Unknown',
        meta: `${a.quality || 'FLAC'} · ${a.release_date?.slice(0, 4) || ''}`,
      }));
      removedAlbums = (diff.removed_albums || []).map((a: any, i: number) => ({
        id: i + 1000,
        title: a.title || 'Unknown',
        artist: a.artist || 'Unknown',
        meta: '',
      }));
      lastSync = diff.last_sync;

      // Get library stats
      const libraryData = await api.library.getAlbums(source, { page_size: '1' });
      const downloadedData = await api.library.getAlbums(source, { page_size: '1', status: 'complete' });
      stats = {
        inLibrary: libraryData.total || 0,
        downloaded: downloadedData.total || 0,
        newCount: newAlbums.length,
        missing: removedAlbums.length,
      };

      // Get sync history
      const history = await fetch(`/api/sync/history?source=${source}`).then(r => r.json());
      syncHistory = history || [];
    } catch (err) {
      console.error('Failed to load sync status', err);
    } finally {
      loading = false;
    }
  }

  async function handleSyncNow() {
    syncing = true;
    syncResult = null;
    try {
      const result = await fetch(`/api/sync/run/${source}`, { method: 'POST' }).then(r => r.json());
      syncResult = `Synced: ${result.albums_found || 0} albums, ${result.albums_new || 0} new`;
      await loadSyncStatus();
    } catch (err) {
      syncResult = 'Sync failed';
      console.error('Sync failed', err);
    } finally {
      syncing = false;
      setTimeout(() => { syncResult = null; }, 5000);
    }
  }

  function formatLastSync(ts: string | null): string {
    if (!ts) return 'Never';
    const d = new Date(ts);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins} minutes ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} hours ago`;
    return `${Math.floor(hours / 24)} days ago`;
  }

  onMount(() => {
    loadSyncStatus();
  });
</script>

<div class="page-header">
  <div>
    <div class="page-title">Sync</div>
    <div class="page-subtitle">
      {#if loading}Loading...{:else}
        Last sync: {formatLastSync(lastSync)} · {source.charAt(0).toUpperCase() + source.slice(1)}
      {/if}
    </div>
  </div>
  <div class="header-actions">
    {#if syncResult}
      <span class="sync-result">{syncResult}</span>
    {/if}
    <button class="btn btn-primary btn-sm" onclick={handleSyncNow} disabled={syncing}>
      {#if syncing}Syncing...{:else}▸ Sync Now{/if}
    </button>
  </div>
</div>

<div class="stats-row">
  <div class="stat-card">
    <div class="stat-label">In Library</div>
    <div class="stat-value">{stats.inLibrary}</div>
    <div class="stat-sub">albums on {source}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Downloaded</div>
    <div class="stat-value" style="color: var(--positive);">{stats.downloaded}</div>
    <div class="stat-sub">albums local</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">New</div>
    <div class="stat-value" style="color: var(--pop);">{stats.newCount}</div>
    <div class="stat-sub">not yet downloaded</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Missing</div>
    <div class="stat-value" style="color: var(--destructive);">{stats.missing}</div>
    <div class="stat-sub">removed from library</div>
  </div>
</div>

{#if newAlbums.length > 0}
  <div class="section-title">
    <span>New in Library</span>
    <span class="decoration">░▒▓</span>
  </div>
  <div style="margin-bottom: var(--space-8);">
    <SyncDiff
      label="Added since last sync"
      icon_color="var(--pop)"
      items={newAlbums}
      selectable={true}
    />
  </div>
{/if}

{#if removedAlbums.length > 0}
  <div class="section-title">
    <span>Removed from Library</span>
    <span class="decoration">░▒▓</span>
  </div>
  <SyncDiff
    label="No longer in streaming library"
    icon_color="var(--destructive)"
    items={removedAlbums}
    selectable={false}
  />
{/if}

{#if !loading && newAlbums.length === 0 && removedAlbums.length === 0}
  <div class="empty-state">
    <span class="empty-icon">═</span>
    <p class="empty-text">Library is in sync — no changes detected</p>
  </div>
{/if}

<style>
  .page-header { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: var(--space-6); }
  .page-title { font-size: var(--text-3xl); font-weight: 800; letter-spacing: var(--tracking-tight); }
  .page-subtitle { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-tertiary); letter-spacing: var(--tracking-mono); }
  .header-actions { display: flex; gap: var(--space-3); align-items: center; }
  .sync-result { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--positive); letter-spacing: var(--tracking-mono); }

  .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-4); margin-bottom: var(--space-6); }
  .stat-card { border: 2px solid var(--border); padding: var(--space-4); background: var(--canvas-raised); box-shadow: var(--shadow-sm); }
  .stat-label { font-size: var(--text-xs); font-weight: 800; text-transform: uppercase; letter-spacing: var(--tracking-wide); color: var(--text-tertiary); margin-bottom: var(--space-1); }
  .stat-value { font-size: var(--text-2xl); font-weight: 800; letter-spacing: var(--tracking-tight); }
  .stat-sub { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); letter-spacing: var(--tracking-mono); margin-top: 2px; }

  .section-title { font-size: var(--text-xs); font-weight: 800; text-transform: uppercase; letter-spacing: var(--tracking-wide); border-bottom: 2px solid var(--border); padding-bottom: var(--space-2); margin-bottom: var(--space-6); display: flex; justify-content: space-between; }
  .decoration { font-family: var(--font-mono); font-weight: 400; color: var(--text-tertiary); font-size: 11px; }

  .empty-state { display: flex; flex-direction: column; align-items: center; padding: var(--space-16); gap: var(--space-3); }
  .empty-icon { font-size: 48px; color: var(--text-tertiary); opacity: 0.3; }
  .empty-text { font-family: var(--font-mono); font-size: var(--text-sm); color: var(--text-tertiary); }

  .btn { font-family: var(--font-family); font-size: var(--text-sm); font-weight: 700; padding: var(--space-2) var(--space-5); border: 2px solid var(--border); border-radius: 0; cursor: pointer; display: inline-flex; align-items: center; gap: var(--space-2); }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-primary { background: var(--accent); color: var(--text-inverse); box-shadow: var(--shadow-accent); }
  .btn-sm { font-size: var(--text-xs); padding: var(--space-1) var(--space-3); }

  @media (max-width: 768px) {
    .stats-row { grid-template-columns: repeat(2, 1fr); }
  }
</style>
