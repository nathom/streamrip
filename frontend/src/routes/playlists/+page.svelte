<script lang="ts">
  import { onMount } from 'svelte';
  import { currentSource } from '$lib/stores/library';
  import { api } from '$lib/api/client';

  let source = $derived($currentSource);

  interface PlaylistSummary {
    id: number;
    name: string;
    description?: string;
    tracks_count?: number;
    duration?: number;
    is_public?: boolean;
    owner?: string;
    updated_at?: number;
  }

  interface PlaylistTrack {
    id: number;
    title: string;
    artist?: string;
    duration_seconds?: number;
    album_title?: string;
    album_id?: string;
    track_number?: number;
  }

  interface PlaylistDetail extends PlaylistSummary {
    tracks: PlaylistTrack[];
  }

  let playlists = $state<PlaylistSummary[]>([]);
  let loading = $state(false);
  let error = $state('');

  let selected = $state<PlaylistDetail | null>(null);
  let detailLoading = $state(false);
  let detailOpen = $state(false);

  async function loadPlaylists() {
    loading = true;
    error = '';
    try {
      const data = await api.library.listPlaylists(source);
      playlists = Array.isArray(data) ? data : [];
    } catch (e: any) {
      error = e?.message ?? 'Failed to load playlists';
      playlists = [];
    } finally {
      loading = false;
    }
  }

  async function selectPlaylist(p: PlaylistSummary) {
    selected = { ...p, tracks: [] } as PlaylistDetail;
    detailOpen = true;
    detailLoading = true;
    try {
      const data = await api.library.getPlaylist(source, p.id);
      selected = data;
    } catch (e) {
      console.error('Failed to load playlist detail', e);
    } finally {
      detailLoading = false;
    }
  }

  function closeDetail() {
    detailOpen = false;
  }

  async function downloadPlaylistAlbums() {
    if (!selected || !selected.tracks) return;
    // Distinct album IDs from the playlist's tracks
    const albumIds = Array.from(
      new Set(selected.tracks.map(t => t.album_id).filter((x): x is string => !!x))
    );
    if (albumIds.length === 0) return;
    try {
      await api.downloads.enqueue(source, albumIds);
    } catch (e) {
      console.error('Failed to enqueue playlist downloads', e);
    }
  }

  function formatDuration(seconds?: number): string {
    if (!seconds) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  // Re-load on source change
  $effect(() => {
    const _s = source;
    loadPlaylists();
  });

  onMount(() => {
    loadPlaylists();
  });
</script>

<div class="page-header">
  <div>
    <div class="page-title">Playlists</div>
    <div class="page-subtitle">
      {#if loading}
        Loading...
      {:else}
        {playlists.length} playlists · {source.charAt(0).toUpperCase() + source.slice(1)}
      {/if}
    </div>
  </div>
</div>

{#if source !== 'qobuz'}
  <div class="banner">
    <span class="banner-icon">★</span>
    <span>Tidal playlists not yet supported. The SDK exposes the <code>Playlist</code> type but doesn't have read methods. Switch to Qobuz in the sidebar to browse playlists.</span>
  </div>
{:else if error}
  <div class="banner banner-error">{error}</div>
{:else if loading}
  <div class="loading-state"><span class="loading-text">Loading playlists...</span></div>
{:else if playlists.length === 0}
  <div class="empty-state">
    <span class="empty-icon">≡</span>
    <p class="empty-text">No playlists found</p>
  </div>
{:else}
  <div class="section-title">
    <span>My Playlists</span>
    <span class="decoration">░▒▓</span>
  </div>
  <div class="playlist-list">
    {#each playlists as pl (pl.id)}
      <button class="playlist-row" onclick={() => selectPlaylist(pl)}>
        <span class="playlist-name">{pl.name}</span>
        <span class="playlist-meta">
          {pl.tracks_count ?? 0} tracks · {formatDuration(pl.duration)}
          {#if pl.is_public}<span class="tag-mini">PUBLIC</span>{/if}
        </span>
      </button>
    {/each}
  </div>
{/if}

<!-- Detail panel -->
{#if detailOpen && selected}
  <div class="detail-panel open">
    <div class="detail-header">
      <div>
        <div class="detail-title">{selected.name}</div>
        <div class="detail-meta">
          {selected.tracks_count ?? selected.tracks?.length ?? 0} tracks ·
          {formatDuration(selected.duration)} ·
          by {selected.owner ?? 'Unknown'}
        </div>
        {#if selected.description}
          <div class="detail-description">{selected.description}</div>
        {/if}
      </div>
      <button class="close-btn" onclick={closeDetail}>×</button>
    </div>

    <div class="detail-actions">
      <button class="btn btn-pop btn-sm" onclick={downloadPlaylistAlbums} disabled={!selected.tracks?.length}>
        ▸ Download All Albums
      </button>
    </div>

    {#if detailLoading}
      <div class="detail-loading">Loading tracks...</div>
    {:else if selected.tracks && selected.tracks.length > 0}
      <div class="track-list">
        {#each selected.tracks as track, i (track.id)}
          <div class="track-row">
            <span class="track-num">{String(i + 1).padStart(2, '0')}</span>
            <div class="track-info">
              <div class="track-title">{track.title}</div>
              {#if track.artist}
                <div class="track-artist">{track.artist}</div>
              {/if}
              {#if track.album_title}
                <div class="track-album">{track.album_title}</div>
              {/if}
            </div>
            <span class="track-duration">{formatDuration(track.duration_seconds)}</span>
          </div>
        {/each}
      </div>
    {:else}
      <div class="empty-state">
        <p class="empty-text">No tracks</p>
      </div>
    {/if}
  </div>
{/if}

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

  .banner {
    border: 2px solid var(--pop);
    background: var(--pop-subtle);
    padding: var(--space-3) var(--space-4);
    margin-bottom: var(--space-6);
    font-size: var(--text-sm);
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .banner-error {
    border-color: var(--destructive);
    color: var(--destructive);
  }

  .banner-icon {
    color: var(--pop);
    font-size: var(--text-base);
  }

  .playlist-list {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .playlist-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-3) var(--space-4);
    background: var(--canvas-raised);
    border: 2px solid var(--border);
    border-bottom: none;
    cursor: pointer;
    text-align: left;
    font-family: var(--font-family);
    color: var(--text-primary);
  }
  .playlist-row:last-child {
    border-bottom: 2px solid var(--border);
  }
  .playlist-row:hover {
    background: var(--canvas-hover);
  }

  .playlist-name {
    font-weight: 700;
    font-size: var(--text-base);
  }

  .playlist-meta {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .tag-mini {
    font-size: 9px;
    background: var(--accent);
    color: var(--text-inverse);
    padding: 1px 6px;
    border: 1px solid var(--border);
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
  }

  .loading-state, .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--space-16);
    gap: var(--space-3);
  }

  .loading-text, .empty-text {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    color: var(--text-tertiary);
    letter-spacing: var(--tracking-mono);
  }

  .empty-icon {
    font-size: 48px;
    color: var(--text-tertiary);
    opacity: 0.3;
  }

  /* ── Detail panel ── */
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

  .detail-title {
    font-size: var(--text-xl);
    font-weight: 800;
  }

  .detail-meta {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    margin-top: var(--space-1);
  }

  .detail-description {
    font-size: var(--text-sm);
    color: var(--text-secondary);
    margin-top: var(--space-2);
  }

  .close-btn {
    background: transparent;
    border: 2px solid var(--border);
    color: var(--text-primary);
    width: 32px;
    height: 32px;
    font-size: var(--text-xl);
    cursor: pointer;
  }
  .close-btn:hover {
    background: var(--canvas-hover);
  }

  .detail-actions {
    padding: var(--space-3) var(--space-5);
    border-bottom: 2px solid var(--border);
  }

  .detail-loading {
    padding: var(--space-8);
    text-align: center;
    color: var(--text-tertiary);
    font-family: var(--font-mono);
    font-size: var(--text-sm);
  }

  .track-list {
    padding: var(--space-2) 0;
  }

  .track-row {
    display: grid;
    grid-template-columns: 36px 1fr auto;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--border-subtle);
  }
  .track-row:hover {
    background: var(--canvas-hover);
  }

  .track-num {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    text-align: right;
  }

  .track-title {
    font-size: var(--text-sm);
    font-weight: 700;
  }

  .track-artist {
    font-size: var(--text-xs);
    color: var(--text-secondary);
  }

  .track-album {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    font-style: italic;
  }

  .track-duration {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
  }

  .btn {
    font-family: var(--font-family);
    font-size: var(--text-sm);
    font-weight: 700;
    padding: var(--space-2) var(--space-5);
    border: 2px solid var(--border);
    border-radius: 0;
    cursor: pointer;
  }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-pop { background: var(--pop); color: var(--text-inverse); box-shadow: var(--shadow-pop); }
  .btn-sm  { font-size: var(--text-xs); padding: var(--space-1) var(--space-3); }
</style>
