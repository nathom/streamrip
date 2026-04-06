<script lang="ts">
  import { onMount } from 'svelte';
  import DownloadQueue from '$lib/components/DownloadQueue.svelte';
  import { queue, activeCount, totalSpeed, loadQueue } from '$lib/stores/downloads';
  import { api } from '$lib/api/client';

  let queueItems = $derived($queue);
  let active = $derived($activeCount);
  let speed = $derived($totalSpeed);

  let activeItems = $derived(queueItems.filter((i: any) => i.status !== 'complete'));
  let completedItems = $derived(queueItems.filter((i: any) => i.status === 'complete'));

  // Derived stats
  let downloadedTracks = $derived(
    queueItems.reduce((sum: number, i: any) => sum + (i.downloaded_tracks ?? 0), 0)
  );
  let diskUsageGB = $derived(
    Math.round(queueItems.reduce((sum: number, i: any) => sum + (i.size_mb ?? 0), 0) / 1024)
  );

  async function cancelAll() {
    try {
      await api.downloads.cancelAll();
    } catch (e) {
      console.error('Failed to cancel all downloads', e);
    }
  }

  onMount(() => {
    loadQueue();
  });
</script>

<div class="page">
  <div class="page-header">
    <div>
      <div class="page-title">Downloads</div>
      <div class="page-subtitle">
        {active} active · {completedItems.length} completed today
      </div>
    </div>
    <button class="btn btn-destructive btn-sm" onclick={cancelAll}>✕ Cancel All</button>
  </div>

  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-label">Active</div>
      <div class="stat-value">{active}</div>
      <div class="stat-sub">albums</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Speed</div>
      <div class="stat-value" style="color: var(--positive);">
        {speed > 0 ? speed.toFixed(1) : '—'}
      </div>
      <div class="stat-sub">MB/s</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Downloaded</div>
      <div class="stat-value">{downloadedTracks}</div>
      <div class="stat-sub">tracks total</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Disk Usage</div>
      <div class="stat-value">{diskUsageGB || '—'}</div>
      <div class="stat-sub">GB</div>
    </div>
  </div>

  <div class="section-title">
    <span>Active Downloads</span>
    <span class="decoration">░▒▓</span>
  </div>

  <div style="margin-bottom: var(--space-8);">
    <DownloadQueue items={activeItems} mode="active" />
  </div>

  <div class="section-title">
    <span>Completed Today</span>
    <span class="decoration">░▒▓</span>
  </div>

  <DownloadQueue items={completedItems} mode="completed" />
</div>

<style>
  .page-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: var(--space-6);
  }

  .page-title {
    font-size: var(--text-3xl);
    font-weight: 800;
    letter-spacing: var(--tracking-tight);
    line-height: var(--leading-tight);
  }

  .page-subtitle {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    letter-spacing: var(--tracking-mono);
  }

  .stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-4);
    margin-bottom: var(--space-6);
  }

  .stat-card {
    border: 2px solid var(--border);
    padding: var(--space-4);
    background: var(--canvas-raised);
    box-shadow: var(--shadow-sm);
  }

  .stat-label {
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    color: var(--text-tertiary);
    margin-bottom: var(--space-1);
  }

  .stat-value {
    font-size: var(--text-2xl);
    font-weight: 800;
    letter-spacing: var(--tracking-tight);
  }

  .stat-sub {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-tertiary);
    letter-spacing: var(--tracking-mono);
    margin-top: 2px;
  }

  .section-title {
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    border-bottom: 2px solid var(--border);
    padding-bottom: var(--space-2);
    margin-bottom: var(--space-6);
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }

  .decoration {
    font-family: var(--font-mono);
    font-weight: 400;
    color: var(--text-tertiary);
    font-size: 11px;
  }
</style>
