<script lang="ts">
  import { onMount } from 'svelte';
  import AlbumGrid from '$lib/components/AlbumGrid.svelte';
  import AlbumDetail from '$lib/components/AlbumDetail.svelte';
  import {
    albums,
    totalAlbums,
    currentSource,
    selectedAlbum,
    loadAlbumDetail,
  } from '$lib/stores/library';
  import { api } from '$lib/api/client';

  let albumList = $derived($albums);
  let total = $derived($totalAlbums);
  let source = $derived($currentSource);
  let detail = $derived($selectedAlbum);

  // UI state
  let detailOpen = $state(false);
  let sort = $state('added_to_library_at');
  let filter = $state('all');
  let loading = $state(false);
  let refreshing = $state(false);
  let isConnected = $state(false);
  let refreshResult = $state<string | null>(null);

  // Library filter (local DB search)
  let librarySearch = $state('');
  let libraryDebounce: ReturnType<typeof setTimeout> | null = null;


  async function fetchAlbums() {
    loading = true;
    try {
      const params: Record<string, string> = {
        sort_by: sort,
        page_size: '500',
      };
      if (filter !== 'all') params['status'] = filter;
      if (librarySearch.trim()) params['search'] = librarySearch.trim();
      const data = await api.library.getAlbums(source, params);
      $albums = data.albums;
      $totalAlbums = data.total;
    } catch (err) {
      console.error('Failed to load albums', err);
    } finally {
      loading = false;
    }
  }

  async function refreshLibrary() {
    refreshing = true;
    refreshResult = null;
    try {
      const result = await api.library.refresh(source);
      await fetchAlbums();
      refreshResult = `Synced: ${result.total} albums, ${result.new} new`;
      setTimeout(() => { refreshResult = null; }, 5000);
    } catch (err) {
      refreshResult = 'Sync failed — check Settings';
      console.error('Failed to refresh library', err);
    } finally {
      refreshing = false;
    }
  }

  async function checkAuth() {
    try {
      const statuses = await api.auth.status();
      const s = statuses.find((a: any) => a.source === source);
      isConnected = s?.authenticated ?? false;
    } catch { /* ignore */ }
  }

  function handleLibrarySearch(e: Event) {
    librarySearch = (e.target as HTMLInputElement).value;
    if (libraryDebounce) clearTimeout(libraryDebounce);
    libraryDebounce = setTimeout(() => fetchAlbums(), 300);
  }


  async function handleSelectAlbum(album: any) {
    $selectedAlbum = album;
    detailOpen = true;
    if (album.id && album.id > 0) {
      try {
        await loadAlbumDetail(source, album.id);
      } catch (err) {
        console.error('Failed to load album detail', err);
      }
    }
  }

  function closeDetail() {
    detailOpen = false;
  }

  async function downloadAllNew() {
    const newAlbums = albumList.filter((a) => {
      const status = (a.download_status || a.status || '').toLowerCase();
      return !status || status === 'not_downloaded';
    });
    if (newAlbums.length === 0) return;
    try {
      await api.downloads.enqueue(
        source,
        newAlbums.map((a) => a.source_album_id || String(a.id))
      );
    } catch (err) {
      console.error('Failed to queue downloads', err);
    }
  }

  // Reload when source, sort, or filter changes
  $effect(() => {
    const _s = source;
    const _so = sort;
    const _f = filter;
    fetchAlbums();
  });

  onMount(() => {
    checkAuth();
    fetchAlbums();
  });
</script>

<div class="page-header">
  <div>
    <div class="page-title">Library</div>
    <div class="page-subtitle">
      {#if loading}
        Loading...
      {:else}
        {total} albums · {source.charAt(0).toUpperCase() + source.slice(1)}
      {/if}
    </div>
  </div>
  <div class="header-actions">
    {#if refreshResult}
      <span class="refresh-result">{refreshResult}</span>
    {/if}
    <button class="btn btn-secondary btn-sm" onclick={refreshLibrary} disabled={refreshing || !isConnected}>
      {#if refreshing}Syncing...{:else}▸ Refresh Library{/if}
    </button>
  </div>
</div>

{#if !isConnected}
  <div class="connect-banner">
    <span class="banner-icon">★</span>
    <span>No {source.charAt(0).toUpperCase() + source.slice(1)} account connected. </span>
    <a href="/settings" class="banner-link">Go to Settings</a>
    <span> to add your credentials.</span>
  </div>
{/if}

<!-- ═══ MY LIBRARY ═══ -->
<div class="section-title">
  <span>My Library</span>
  <span class="decoration">░▒▓</span>
</div>

<div class="toolbar">
  <input
    class="search-input"
    type="text"
    placeholder="Filter library..."
    value={librarySearch}
    oninput={handleLibrarySearch}
  />

  <select
    class="toolbar-select"
    value={sort}
    onchange={(e) => { sort = (e.target as HTMLSelectElement).value; }}
  >
    <option value="added_to_library_at">Sort: Added</option>
    <option value="artist">Sort: Artist</option>
    <option value="title">Sort: Title</option>
    <option value="release_date">Sort: Year</option>
  </select>

  <select
    class="toolbar-select"
    value={filter}
    onchange={(e) => { filter = (e.target as HTMLSelectElement).value; }}
  >
    <option value="all">All</option>
    <option value="complete">Downloaded</option>
    <option value="not_downloaded">Not Downloaded</option>
    <option value="partial">Partial</option>
    <option value="queued">Queued</option>
  </select>

  <div class="toolbar-right">
    <button class="btn btn-pop btn-sm" onclick={downloadAllNew}>▸ Download All New</button>
  </div>
</div>

{#if loading}
  <div class="loading-state">
    <span class="loading-text">Loading albums...</span>
  </div>
{:else}
  <AlbumGrid albums={albumList} onselect={handleSelectAlbum} />
{/if}

<AlbumDetail album={detail} open={detailOpen} onclose={closeDetail} />

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

  .header-actions {
    display: flex;
    gap: var(--space-2);
  }

  .toolbar {
    display: flex;
    gap: var(--space-3);
    align-items: center;
    margin-bottom: var(--space-6);
    flex-wrap: wrap;
  }

  .search-input {
    font-family: var(--font-family);
    font-size: var(--text-sm);
    padding: var(--space-2) var(--space-3);
    border: 2px solid var(--border-subtle);
    border-radius: 0;
    background: var(--canvas-inset);
    color: var(--text-primary);
    outline: none;
    width: 280px;
  }
  .search-input:focus {
    border-color: var(--accent);
    box-shadow: var(--shadow-accent);
  }
  .search-input::placeholder { color: var(--text-tertiary); }

  .toolbar-select {
    font-family: var(--font-family);
    font-size: var(--text-sm);
    padding: var(--space-2) var(--space-3);
    border: 2px solid var(--border-subtle);
    border-radius: 0;
    background: var(--canvas-inset);
    color: var(--text-primary);
    outline: none;
    cursor: pointer;
    -webkit-appearance: none;
    padding-right: var(--space-6);
  }

  .toolbar-right {
    margin-left: auto;
    display: flex;
    gap: var(--space-2);
    align-items: center;
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

  .loading-state {
    display: flex;
    justify-content: center;
    padding: var(--space-10);
  }

  .loading-text {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    color: var(--text-tertiary);
    letter-spacing: var(--tracking-mono);
  }

  .connect-banner {
    border: 2px solid var(--pop);
    background: var(--pop-subtle);
    padding: var(--space-3) var(--space-4);
    margin-bottom: var(--space-6);
    font-size: var(--text-sm);
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .banner-icon {
    color: var(--pop);
    font-size: var(--text-base);
  }

  .banner-link {
    color: var(--accent);
    font-weight: 700;
    text-decoration: none;
    border-bottom: 1px solid var(--accent);
  }

  .refresh-result {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--positive);
    letter-spacing: var(--tracking-mono);
  }

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
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-secondary { background: var(--canvas-raised); color: var(--text-primary); box-shadow: var(--shadow-sm); }
  .btn-pop { background: var(--pop); color: var(--text-inverse); box-shadow: var(--shadow-pop); }
  .btn-sm  { font-size: var(--text-xs); padding: var(--space-1) var(--space-3); }
</style>
