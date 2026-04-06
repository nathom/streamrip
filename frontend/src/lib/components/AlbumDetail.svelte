<script lang="ts">
  interface Track {
    number?: number;
    title: string;
    duration?: string;
    status?: string;
  }

  interface AlbumFull {
    id: number;
    title: string;
    artist: string;
    year?: number | string;
    label?: string;
    format?: string;
    size?: string;
    tracks?: Track[];
    duration?: string;
    genre?: string;
    status?: string;
    cover_url?: string;
  }

  let {
    album,
    open,
    onclose,
  }: {
    album: AlbumFull | null;
    open: boolean;
    onclose?: () => void;
  } = $props();

  function trackStatusClass(status?: string): string {
    switch (status?.toLowerCase()) {
      case 'downloaded':
      case 'complete':
        return 'tag-positive';
      case 'queued':
      case 'downloading':
        return 'tag-accent';
      case 'partial':
        return 'tag-warning';
      default:
        return 'tag-default';
    }
  }

  function trackStatusLabel(status?: string): string {
    switch (status?.toLowerCase()) {
      case 'downloaded':
      case 'complete':
        return 'DL';
      case 'queued':
        return 'Q';
      case 'downloading':
        return '▸';
      case 'partial':
        return '~';
      default:
        return '—';
    }
  }

  function albumStatusClass(status?: string): string {
    switch (status?.toLowerCase()) {
      case 'complete':
      case 'downloaded':
        return 'tag-positive';
      case 'queued':
      case 'downloading':
        return 'tag-accent';
      case 'partial':
        return 'tag-warning';
      default:
        return 'tag-default';
    }
  }

  function albumStatusLabel(status?: string): string {
    switch (status?.toLowerCase()) {
      case 'complete':
      case 'downloaded':
        return 'Downloaded';
      case 'queued':
        return 'Queued';
      case 'downloading':
        return 'Downloading';
      case 'partial':
        return 'Partial';
      default:
        return 'Not Downloaded';
    }
  }

  function formatTrackNumber(n?: number, total?: number): string {
    if (n == null) return '—';
    const pad = total && total >= 100 ? 3 : 2;
    return String(n).padStart(pad, '0');
  }
</script>

<div class="detail-panel" class:open>
  <div class="detail-header">
    <span class="overline">Album Detail</span>
    <button class="detail-close" onclick={onclose}>✕</button>
  </div>

  {#if album}
    <div class="detail-cover">
      {#if album.cover_url}
        <img src={album.cover_url} alt={album.title} />
      {:else}
        <div class="cover-placeholder">♪</div>
      {/if}
    </div>

    <div class="detail-album-info">
      <div class="detail-album-title">{album.title}</div>
      <div class="detail-album-artist">{album.artist}</div>

      <div class="detail-meta-grid">
        <div>
          <div class="detail-meta-label">Year</div>
          <div class="detail-meta-value mono">{album.year ?? '—'}</div>
        </div>
        <div>
          <div class="detail-meta-label">Label</div>
          <div class="detail-meta-value">{album.label ?? '—'}</div>
        </div>
        <div>
          <div class="detail-meta-label">Format</div>
          <div class="detail-meta-value mono">{album.format ?? '—'}</div>
        </div>
        <div>
          <div class="detail-meta-label">Size</div>
          <div class="detail-meta-value mono">{album.size ?? '—'}</div>
        </div>
        <div>
          <div class="detail-meta-label">Tracks</div>
          <div class="detail-meta-value mono">{album.tracks?.length ?? '—'}</div>
        </div>
        <div>
          <div class="detail-meta-label">Duration</div>
          <div class="detail-meta-value mono">{album.duration ?? '—'}</div>
        </div>
        <div>
          <div class="detail-meta-label">Genre</div>
          <div class="detail-meta-value">{album.genre ?? '—'}</div>
        </div>
        <div>
          <div class="detail-meta-label">Status</div>
          <div class="detail-meta-value">
            <span class="tag {albumStatusClass(album.status)}">{albumStatusLabel(album.status)}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="detail-actions">
      <button class="btn btn-primary btn-sm">▸ Download</button>
      <button class="btn btn-secondary btn-sm">Open Folder</button>
    </div>

    {#if album.tracks && album.tracks.length > 0}
      <div class="track-list">
        <div class="track-list-header">
          <span>#</span>
          <span>Title</span>
          <span>Duration</span>
          <span>Status</span>
        </div>
        {#each album.tracks as track, i}
          <div class="track-row">
            <span class="track-num">{formatTrackNumber(track.number ?? i + 1, album.tracks?.length)}</span>
            <div class="track-title-col">
              <div class="track-title">{track.title}</div>
            </div>
            <span class="track-duration">{track.duration ?? '—'}</span>
            <span class="track-status">
              <span class="tag {trackStatusClass(track.status)}" style="font-size:10px;">{trackStatusLabel(track.status)}</span>
            </span>
          </div>
        {/each}
      </div>
    {/if}
  {:else}
    <div class="detail-loading">
      <span class="mono">Loading…</span>
    </div>
  {/if}
</div>

<style>
  .detail-panel {
    position: fixed;
    top: 0;
    right: 0;
    width: 520px;
    height: 100vh;
    background: var(--canvas);
    border-left: 3px solid var(--border);
    box-shadow: -8px 0 0 rgba(0, 0, 0, 0.55);
    z-index: 100;
    overflow-y: auto;
    display: none;
    transform: translateX(100%);
    transition: transform 180ms ease, display 0ms;
  }

  .detail-panel.open {
    display: block;
    transform: translateX(0);
  }

  .detail-header {
    padding: var(--space-5);
    border-bottom: 2px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    position: sticky;
    top: 0;
    background: var(--canvas);
    z-index: 1;
  }

  .overline {
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    color: var(--text-tertiary);
  }

  .detail-close {
    font-family: var(--font-mono);
    font-weight: 700;
    font-size: var(--text-base);
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: var(--space-1);
    line-height: 1;
  }

  .detail-close:hover {
    color: var(--text-primary);
  }

  .detail-cover {
    margin: var(--space-5);
    border: 2px solid var(--border);
    box-shadow: var(--shadow-md);
    overflow: hidden;
  }

  .detail-cover img {
    display: block;
    width: 100%;
    aspect-ratio: 1;
    object-fit: cover;
  }

  .cover-placeholder {
    width: 100%;
    aspect-ratio: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 80px;
    color: var(--text-tertiary);
    opacity: 0.2;
    background: var(--canvas-inset);
  }

  .detail-album-info {
    padding: 0 var(--space-5) var(--space-5);
  }

  .detail-album-title {
    font-size: var(--text-2xl);
    font-weight: 800;
    letter-spacing: var(--tracking-tight);
    line-height: var(--leading-tight);
    margin-bottom: var(--space-1);
  }

  .detail-album-artist {
    font-size: var(--text-lg);
    color: var(--text-secondary);
    margin-bottom: var(--space-4);
  }

  .detail-meta-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-2) var(--space-6);
    margin-bottom: var(--space-5);
  }

  .detail-meta-label {
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    color: var(--text-tertiary);
  }

  .detail-meta-value {
    font-size: var(--text-sm);
    color: var(--text-primary);
  }

  .detail-meta-value.mono {
    font-family: var(--font-mono);
    letter-spacing: var(--tracking-mono);
  }

  /* inline .mono utility via class on element */
  :global(.detail-meta-value .mono),
  .mono {
    font-family: var(--font-mono);
    letter-spacing: var(--tracking-mono);
  }

  .detail-actions {
    padding: 0 var(--space-5) var(--space-5);
    display: flex;
    gap: var(--space-3);
  }

  /* Buttons */
  .btn {
    font-family: var(--font-family);
    font-size: var(--text-sm);
    font-weight: 700;
    padding: var(--space-2) var(--space-5);
    border: 2px solid var(--border);
    border-radius: 0;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .btn-primary  { background: var(--accent); color: var(--text-inverse); box-shadow: var(--shadow-accent); }
  .btn-primary:hover { box-shadow: var(--shadow-lg); }
  .btn-primary:active { box-shadow: 1px 1px 0 rgba(0,0,0,0.3); transform: translate(1px,1px); }
  .btn-secondary { background: var(--canvas-raised); color: var(--text-primary); box-shadow: var(--shadow-sm); }
  .btn-sm { font-size: var(--text-xs); padding: var(--space-1) var(--space-3); }

  /* Track list */
  .track-list {
    border-top: 2px solid var(--border);
  }

  .track-list-header {
    padding: var(--space-2) var(--space-5);
    background: var(--canvas-inset);
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    color: var(--text-tertiary);
    display: grid;
    grid-template-columns: 36px 1fr 60px 80px;
    gap: var(--space-3);
    border-bottom: 2px solid var(--border);
  }

  .track-row {
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--border-subtle);
    display: grid;
    grid-template-columns: 36px 1fr 60px 80px;
    gap: var(--space-3);
    align-items: center;
    font-size: var(--text-sm);
    transition: background-color 80ms;
  }

  .track-row:hover {
    background: var(--pop-subtle);
  }

  .track-num {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    text-align: right;
    letter-spacing: var(--tracking-mono);
  }

  .track-title-col {
    overflow: hidden;
  }

  .track-title {
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .track-duration {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    text-align: right;
    letter-spacing: var(--tracking-mono);
  }

  .track-status {
    text-align: right;
  }

  /* Tags */
  .tag {
    font-size: 11px;
    font-weight: 700;
    padding: 2px var(--space-2);
    border: 1.5px solid var(--border);
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    display: inline-block;
  }
  .tag-positive { background: var(--positive); color: var(--text-primary); }
  .tag-accent   { background: var(--accent);   color: var(--text-inverse); }
  .tag-warning  { background: var(--warning);  color: var(--text-inverse); }
  .tag-default  { background: var(--canvas-raised); color: var(--text-secondary); }

  .detail-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-16);
    color: var(--text-tertiary);
  }
</style>
