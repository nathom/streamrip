<script lang="ts">
  interface Album {
    id: number;
    source_album_id?: string;
    title: string;
    artist: string;
    year?: number | string;
    release_date?: string;
    format?: string;
    quality?: string;
    cover_url?: string;
    status?: string;
    download_status?: string;
  }

  function getYear(album: Album): string {
    if (album.year) return String(album.year);
    if (album.release_date) return album.release_date.slice(0, 4);
    return '—';
  }

  function getFormat(album: Album): string | undefined {
    return album.format || album.quality;
  }

  function getStatus(album: Album): string | undefined {
    return album.status || album.download_status;
  }

  let {
    album,
    onclick,
  }: {
    album: Album;
    onclick?: () => void;
  } = $props();

  function statusTagClass(status?: string): string {
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

  function statusLabel(status?: string): string {
    switch (status?.toLowerCase()) {
      case 'complete':
      case 'downloaded':
        return 'Complete';
      case 'queued':
        return 'Queued';
      case 'downloading':
        return 'Downloading';
      case 'partial':
        return 'Partial';
      default:
        return 'Not DL';
    }
  }
</script>

<div class="album-card" onclick={onclick} role="button" tabindex="0"
  onkeydown={(e) => e.key === 'Enter' && onclick?.()}>
  <div class="album-cover">
    {#if album.cover_url}
      <img src={album.cover_url} alt={album.title} />
    {:else}
      <span class="placeholder-icon">♪</span>
    {/if}
    <div class="album-status">
      <span class="tag {statusTagClass(getStatus(album))}">{statusLabel(getStatus(album))}</span>
    </div>
  </div>
  <div class="album-info">
    <div class="album-title" title={album.title}>{album.title}</div>
    <div class="album-artist" title={album.artist}>{album.artist}</div>
    <div class="album-meta">
      <span class="album-year">{getYear(album)}</span>
      {#if getFormat(album)}
        <span class="album-format">{getFormat(album)}</span>
      {/if}
    </div>
  </div>
</div>

<style>
  .album-card {
    border: 2px solid var(--border);
    background: var(--canvas-raised);
    box-shadow: var(--shadow-sm);
    cursor: pointer;
    position: relative;
    transition: box-shadow 80ms;
  }

  .album-card:hover {
    box-shadow: var(--shadow-md);
  }

  .album-cover {
    aspect-ratio: 1;
    border-bottom: 2px solid var(--border);
    background: var(--canvas-inset);
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* Scanline overlay */
  .album-cover::after {
    content: '';
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 3px,
      rgba(232, 230, 225, 0.02) 3px,
      rgba(232, 230, 225, 0.02) 4px
    );
    pointer-events: none;
  }

  .album-cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .placeholder-icon {
    font-size: 48px;
    color: var(--text-tertiary);
    opacity: 0.3;
  }

  .album-status {
    position: absolute;
    top: var(--space-2);
    right: var(--space-2);
    z-index: 1;
  }

  .album-info {
    padding: var(--space-3);
  }

  .album-title {
    font-size: var(--text-sm);
    font-weight: 700;
    line-height: var(--leading-tight);
    margin-bottom: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .album-artist {
    font-size: var(--text-xs);
    color: var(--text-secondary);
    margin-bottom: var(--space-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .album-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .album-year {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-tertiary);
    letter-spacing: var(--tracking-mono);
  }

  .album-format {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--accent);
    letter-spacing: var(--tracking-mono);
  }

  /* tag styles (local scope, matches design system) */
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
</style>
