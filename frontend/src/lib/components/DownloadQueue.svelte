<script lang="ts">
  import { api } from '$lib/api/client';

  interface QueueItem {
    id: string;
    title: string;
    artist: string;
    track_count?: number;
    tracks_done?: number;
    cover_url?: string;
    bytes_done?: number;
    bytes_total?: number;
    speed?: number;
    status?: string;
  }

  let { items = [], mode = 'active' }: { items: QueueItem[]; mode?: 'active' | 'completed' } = $props();

  async function cancelItem(id: string) {
    try {
      await api.downloads.cancel(id);
    } catch (e) {
      console.error('Failed to cancel download', e);
    }
  }

  function statusLabel(item: QueueItem): string {
    switch (item.status) {
      case 'complete': return 'Done';
      case 'failed': return 'Failed';
      case 'cancelled': return 'Cancelled';
      case 'downloading': return 'Downloading';
      default: return 'Pending';
    }
  }

  function progressText(item: QueueItem): string {
    if (item.status === 'complete') return 'Complete';
    if (item.status === 'failed') return 'Failed';
    if (item.status === 'cancelled') return 'Cancelled';
    if (item.status === 'pending') return 'Pending';

    const parts: string[] = [];
    if (item.tracks_done !== undefined && item.track_count) {
      parts.push(`${item.tracks_done}/${item.track_count} tracks`);
    }
    if (item.speed && item.speed > 0) {
      parts.push(`${item.speed.toFixed(1)} MB/s`);
    }
    return parts.length > 0 ? parts.join(' · ') : 'Downloading...';
  }

  function progressPct(item: QueueItem): number {
    if (item.status === 'complete') return 100;
    if (item.tracks_done && item.track_count && item.track_count > 0) {
      return Math.round((item.tracks_done / item.track_count) * 100);
    }
    if (item.bytes_done && item.bytes_total && item.bytes_total > 0) {
      return Math.round((item.bytes_done / item.bytes_total) * 100);
    }
    if (item.status === 'downloading') return 5; // Show a sliver for "in progress"
    return 0;
  }

  function statusTagClass(item: QueueItem): string {
    switch (item.status) {
      case 'complete': return 'tag-positive';
      case 'failed': return 'tag-destructive';
      case 'cancelled': return 'tag-default';
      default: return 'tag-accent';
    }
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
            class:complete={item.status === 'complete'}
            class:failed={item.status === 'failed'}
            style="width: {progressPct(item)}%;"
          ></div>
        </div>
        <div class="progress-text">{progressText(item)}</div>
      </div>

      <div class="queue-actions">
        {#if item.status === 'complete' || item.status === 'failed' || item.status === 'cancelled'}
          <span class="tag {statusTagClass(item)}" style="font-size: 10px;">{statusLabel(item)}</span>
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

  .progress-fill.failed {
    background: var(--destructive);
  }

  .tag-destructive {
    background: var(--destructive);
    color: var(--text-primary);
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
