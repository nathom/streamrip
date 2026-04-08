<script lang="ts">
  let {
    albums,
    onselect,
  }: {
    albums: any[];
    onselect?: (album: any) => void;
  } = $props();

  function getYear(a: any): string {
    if (a.year) return String(a.year);
    if (a.release_date) return a.release_date.slice(0, 4);
    return '—';
  }

  function getFormat(a: any): string {
    return a.format || a.quality || '—';
  }

  function getStatus(a: any): string {
    return a.download_status || a.status || 'not_downloaded';
  }

  function statusLabel(s: string): string {
    switch (s.toLowerCase()) {
      case 'complete': case 'downloaded': return 'Downloaded';
      case 'queued': return 'Queued';
      case 'downloading': return 'Downloading';
      case 'partial': return 'Partial';
      default: return '—';
    }
  }

  function statusClass(s: string): string {
    switch (s.toLowerCase()) {
      case 'complete': case 'downloaded': return 'status-complete';
      case 'queued': case 'downloading': return 'status-active';
      default: return 'status-none';
    }
  }

  function formatDuration(seconds: number | undefined): string {
    if (!seconds) return '—';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  }
</script>

<div class="album-table-wrapper">
  <table class="album-table">
    <thead>
      <tr>
        <th class="col-cover"></th>
        <th class="col-title">Title</th>
        <th class="col-artist">Artist</th>
        <th class="col-year">Year</th>
        <th class="col-format">Format</th>
        <th class="col-tracks">Tracks</th>
        <th class="col-status">Status</th>
      </tr>
    </thead>
    <tbody>
      {#each albums as album, i (album.source_album_id ?? album.id ?? i)}
        <tr class="album-row" onclick={() => onselect?.(album)} tabindex="0" onkeydown={(e) => e.key === 'Enter' && onselect?.(album)}>
          <td class="col-cover">
            {#if album.cover_url}
              <img src={album.cover_url} alt="" class="row-cover" />
            {:else}
              <div class="row-cover-placeholder">♪</div>
            {/if}
          </td>
          <td class="col-title">
            <span class="title-text">{album.title}</span>
          </td>
          <td class="col-artist">{album.artist}</td>
          <td class="col-year mono">{getYear(album)}</td>
          <td class="col-format mono">{getFormat(album)}</td>
          <td class="col-tracks mono">{album.track_count ?? '—'}</td>
          <td class="col-status">
            <span class="status-dot {statusClass(getStatus(album))}"></span>
            <span class="status-text">{statusLabel(getStatus(album))}</span>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>

  {#if albums.length === 0}
    <div class="empty-state">
      <span class="empty-icon">◧</span>
      <p class="empty-label">No albums found</p>
    </div>
  {/if}
</div>

<style>
  .album-table-wrapper {
    border: 2px solid var(--border);
    box-shadow: var(--shadow-sm);
    background: var(--canvas-raised);
    overflow-x: auto;
  }

  .album-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }

  thead tr {
    background: var(--canvas-inset);
    border-bottom: 2px solid var(--border);
  }

  th {
    text-align: left;
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    color: var(--text-tertiary);
    white-space: nowrap;
  }

  .album-row {
    border-bottom: 1px solid var(--border-subtle);
    cursor: pointer;
  }

  .album-row:hover {
    background: var(--pop-subtle);
    transition: background-color 80ms;
  }

  td {
    padding: var(--space-2) var(--space-3);
    vertical-align: middle;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 300px;
  }

  .col-cover { width: 40px; padding: var(--space-1) var(--space-2); }
  .col-year, .col-tracks { width: 60px; }
  .col-format { width: 120px; }
  .col-status { width: 100px; }

  .row-cover {
    width: 36px;
    height: 36px;
    object-fit: cover;
    border: 1px solid var(--border);
    display: block;
  }

  .row-cover-placeholder {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--canvas-inset);
    border: 1px solid var(--border);
    color: var(--text-tertiary);
    font-size: 16px;
  }

  .title-text {
    font-weight: 600;
  }

  .col-artist {
    color: var(--text-secondary);
  }

  .mono {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    letter-spacing: var(--tracking-mono);
  }

  .status-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border: 1px solid var(--border);
    margin-right: var(--space-1);
    vertical-align: middle;
  }

  .status-complete { background: var(--positive); }
  .status-active { background: var(--accent); }
  .status-none { background: var(--canvas-inset); }

  .status-text {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: var(--space-16);
    gap: var(--space-3);
    color: var(--text-tertiary);
  }

  .empty-icon { font-size: 48px; opacity: 0.3; }
  .empty-label { font-family: var(--font-mono); font-size: var(--text-sm); letter-spacing: var(--tracking-mono); }
</style>
