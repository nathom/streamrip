<script lang="ts">
  import { api } from '$lib/api/client';

  interface QueueItem {
    id: string;
    title: string;
    artist: string;
    track_count?: number;
    downloaded_tracks?: number;
    cover_url?: string;
    progress?: number;
    speed?: number;
    status?: string;
    size_mb?: number;
  }

  let { items = [], mode = 'active' }: { items: QueueItem[]; mode?: 'active' | 'completed' } = $props();

  async function cancelItem(id: string) {
    try {
      await api.downloads.cancel(id);
    } catch (e) {
      console.error('Failed to cancel download', e);
    }
  }

  function progressText(item: QueueItem): string {
    if (item.status === 'complete') {
      return `Complete${item.size_mb ? ` · ${item.size_mb} MB` : ''}`;
    }
    if (item.status === 'failed') return 'Failed';
    if (!item.progress || item.progress === 0) return 'Pending';
    const trackInfo = (item.downloaded_tracks !== undefined && item.track_count)
      ? `${item.downloaded_tracks}/${item.track_count} tracks`
      : '';
    const speedInfo = item.speed ? `${item.speed.toFixed(1)} MB/s` : '';
    return [trackInfo, speedInfo].filter(Boolean).join(' · ');
  }

  function progressPct(item: QueueItem): number {
    if (item.status === 'complete') return 100;
    return item.progress ?? 0;
  }

  function isComplete(item: QueueItem): boolean {
    return item.status === 'complete';
  }
</script>

<div class="download-queue">
  <div class="queue-header">
    <span class="queue-header-title">{mode === 'completed' ? 'History' : 'Queue'}</span>
    <span class="overline">{items.length} items</span>
  </div>

  {#each items as item (item.id)}
    <div class="queue-item">
      <div class="queue-cover">
        {#if item.cover_url}
          <img src={item.cover_url} alt="{item.title} cover" />
        {/if}
      </div>

      <div class="queue-info">
        <div class="queue-title">{item.title}</div>
        <div class="queue-artist">
          {item.artist}{item.track_count ? ` · ${item.track_count} tracks` : ''}
        </div>
      </div>

      <div class="queue-progress">
        <div class="progress-bar">
          <div
            class="progress-fill"
            class:complete={isComplete(item)}
            style="width: {progressPct(item)}%;"
          ></div>
        </div>
        <div class="progress-text">{progressText(item)}</div>
      </div>

      <div class="queue-actions">
        {#if isComplete(item)}
          <span class="tag tag-positive" style="font-size: 10px;">Done</span>
        {:else}
          <button class="btn btn-ghost btn-sm" onclick={() => cancelItem(item.id)} title="Cancel">✕</button>
        {/if}
      </div>
    </div>
  {/each}

  {#if items.length === 0}
    <div class="queue-empty">No items</div>
  {/if}
</div>

<style>
  .download-queue {
    border: 2px solid var(--border);
    box-shadow: var(--shadow-md);
    background: var(--canvas-raised);
  }

  .queue-header {
    padding: var(--space-3) var(--space-4);
    border-bottom: 2px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--canvas-inset);
  }

  .queue-header-title {
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
  }

  .queue-item {
    padding: var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
    display: grid;
    grid-template-columns: 48px 1fr 180px 80px;
    gap: var(--space-4);
    align-items: center;
  }

  .queue-item:hover {
    background: var(--pop-subtle);
    transition: background-color 80ms;
  }

  .queue-item:last-child {
    border-bottom: none;
  }

  .queue-cover {
    width: 48px;
    height: 48px;
    border: 1.5px solid var(--border);
    background: var(--canvas-inset);
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    flex-shrink: 0;
  }

  .queue-cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .queue-info {
    overflow: hidden;
  }

  .queue-title {
    font-size: var(--text-sm);
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .queue-artist {
    font-size: var(--text-xs);
    color: var(--text-secondary);
  }

  .queue-progress {
    min-width: 0;
  }

  .progress-bar {
    height: 6px;
    background: var(--canvas-inset);
    border: 1px solid var(--border-subtle);
    position: relative;
    margin-bottom: 4px;
  }

  .progress-fill {
    height: 100%;
    background: var(--accent);
    position: absolute;
    left: 0;
    top: 0;
    transition: width 300ms ease;
  }

  .progress-fill.complete {
    background: var(--positive);
  }

  .progress-text {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--text-tertiary);
    letter-spacing: var(--tracking-mono);
  }

  .queue-actions {
    text-align: right;
  }

  .queue-empty {
    padding: var(--space-6) var(--space-4);
    text-align: center;
    font-size: var(--text-sm);
    color: var(--text-tertiary);
    font-family: var(--font-mono);
    letter-spacing: var(--tracking-mono);
  }
</style>
