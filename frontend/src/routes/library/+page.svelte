<script lang="ts">
  import { onMount } from 'svelte';
  import AlbumGrid from '$lib/components/AlbumGrid.svelte';
  import AlbumDetail from '$lib/components/AlbumDetail.svelte';
  import {
    albums,
    totalAlbums,
    currentSource,
    searchQuery,
    sortBy,
    filterStatus,
    selectedAlbum,
    loadAlbums,
    loadAlbumDetail,
  } from '$lib/stores/library';
  import { api } from '$lib/api/client';

  // Reactive store values (Svelte 5 runes)
  let albumList = $derived($albums);
  let total = $derived($totalAlbums);
  let source = $derived($currentSource);
  let detail = $derived($selectedAlbum);

  // Local UI state
  let detailOpen = $state(false);
  let searchValue = $state($searchQuery);
  let sort = $state($sortBy);
  let filter = $state($filterStatus);
  let searchDebounce: ReturnType<typeof setTimeout> | null = null;

  // Reload albums when source, sort, or filter changes
  $effect(() => {
    const s = source;
    const so = sort;
    const f = filter;
    const params: Record<string, string> = { sort: so };
    if (f !== 'all') params['status'] = f;
    loadAlbums(s, params).catch(console.error);
  });

  // Debounced search
  function handleSearch(e: Event) {
    const value = (e.target as HTMLInputElement).value;
    searchValue = value;
    $searchQuery = value;
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(async () => {
      if (value.trim().length === 0) {
        // Restore library view
        const params: Record<string, string> = { sort };
        if (filter !== 'all') params['status'] = filter;
        await loadAlbums(source, params);
      } else {
        try {
          const data = await api.library.search(source, value.trim());
          $albums = data.albums ?? data;
          $totalAlbums = Array.isArray(data.albums) ? data.albums.length : (data.total ?? $albums.length);
        } catch (err) {
          console.error('Search failed', err);
        }
      }
    }, 300);
  }

  async function handleSelectAlbum(album: any) {
    $selectedAlbum = album;
    detailOpen = true;
    try {
      await loadAlbumDetail(source, album.id);
    } catch (err) {
      console.error('Failed to load album detail', err);
    }
  }

  function closeDetail() {
    detailOpen = false;
  }

  async function downloadAllNew() {
    const newAlbums = albumList.filter(
      (a) => !a.status || a.status.toLowerCase() === 'not downloaded'
    );
    if (newAlbums.length === 0) return;
    try {
      await api.downloads.enqueue(
        source,
        newAlbums.map((a) => String(a.id))
      );
    } catch (err) {
      console.error('Failed to queue downloads', err);
    }
  }

  onMount(() => {
    const params: Record<string, string> = { sort };
    if (filter !== 'all') params['status'] = filter;
    loadAlbums(source, params).catch(console.error);
  });
</script>

<div class="page-header">
  <div>
    <div class="page-title">Library</div>
    <div class="page-subtitle">{total} albums · {source.charAt(0).toUpperCase() + source.slice(1)}</div>
  </div>
</div>

<div class="toolbar">
  <input
    class="search-input"
    type="text"
    placeholder="Search albums, artists…"
    value={searchValue}
    oninput={handleSearch}
  />

  <select
    class="toolbar-select"
    value={sort}
    onchange={(e) => {
      sort = (e.target as HTMLSelectElement).value;
      $sortBy = sort;
    }}
  >
    <option value="added_to_library_at">Sort: Added</option>
    <option value="artist">Sort: Artist</option>
    <option value="title">Sort: Title</option>
    <option value="year">Sort: Year</option>
  </select>

  <select
    class="toolbar-select"
    value={filter}
    onchange={(e) => {
      filter = (e.target as HTMLSelectElement).value;
      $filterStatus = filter;
    }}
  >
    <option value="all">All</option>
    <option value="downloaded">Downloaded</option>
    <option value="not_downloaded">Not Downloaded</option>
    <option value="partial">Partial</option>
  </select>

  <div class="toolbar-right">
    <button class="btn btn-pop btn-sm" onclick={downloadAllNew}>▸ Download All New</button>
  </div>
</div>

<div class="section-title">
  <span>Albums</span>
  <span class="decoration">░▒▓</span>
</div>

<AlbumGrid albums={albumList} onselect={handleSelectAlbum} />

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

  /* Buttons (local scope) */
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
  .btn-pop { background: var(--pop); color: var(--text-inverse); box-shadow: var(--shadow-pop); }
  .btn-sm  { font-size: var(--text-xs); padding: var(--space-1) var(--space-3); }
</style>
