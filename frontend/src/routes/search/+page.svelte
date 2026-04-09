<script lang="ts">
  import { onMount } from 'svelte';
  import AlbumGrid from '$lib/components/AlbumGrid.svelte';
  import AlbumTable from '$lib/components/AlbumTable.svelte';
  import AlbumDetail from '$lib/components/AlbumDetail.svelte';
  import { currentSource, selectedAlbum, loadAlbumDetail } from '$lib/stores/library';
  import { api } from '$lib/api/client';

  let source = $derived($currentSource);
  let detail = $derived($selectedAlbum);

  // ── Query state ──
  let searchValue = $state('');
  let activeQuery = $state('');           // last query that was actually fired
  let results = $state<any[]>([]);
  let total = $state(0);
  let loading = $state(false);
  let loadingMore = $state(false);
  let hasSearched = $state(false);
  let currentPage = $state(1);
  const PAGE_SIZE = 60;

  // ── UI state ──
  let viewMode = $state<'grid' | 'table'>('grid');
  let detailOpen = $state(false);
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  // ── Multi-select ──
  let selectMode = $state(false);
  let selectedAlbums = $state<Set<string>>(new Set());
  let batchDownloading = $state(false);

  function toggleSelectMode() {
    selectMode = !selectMode;
    if (!selectMode) selectedAlbums = new Set();
  }

  function toggleAlbumSelect(id: string) {
    const next = new Set(selectedAlbums);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selectedAlbums = next;
  }

  function clearSelection() {
    selectedAlbums = new Set();
  }

  async function downloadSelected() {
    if (selectedAlbums.size === 0) return;
    batchDownloading = true;
    try {
      await api.downloads.enqueue(source, [...selectedAlbums]);
      selectedAlbums = new Set();
      selectMode = false;
    } finally {
      batchDownloading = false;
    }
  }

  // ── Search execution ──
  async function runSearch(query: string, append = false) {
    if (!query.trim()) {
      results = [];
      total = 0;
      hasSearched = false;
      return;
    }
    if (append) {
      loadingMore = true;
    } else {
      loading = true;
      currentPage = 1;
      hasSearched = true;
    }
    activeQuery = query.trim();
    try {
      const data = await api.library.search(source, activeQuery, {
        page: String(currentPage),
        page_size: String(PAGE_SIZE),
      });
      // Backend now returns {albums, total, limit, offset}
      // Old shape compat: if it's an array, treat it as a single page
      const incoming = Array.isArray(data) ? data : (data.albums ?? []);
      const incomingTotal = Array.isArray(data) ? incoming.length : (data.total ?? incoming.length);
      results = append ? [...results, ...incoming] : incoming;
      total = incomingTotal;
    } catch (err) {
      console.error('Search failed', err);
      if (!append) {
        results = [];
        total = 0;
      }
    } finally {
      loading = false;
      loadingMore = false;
    }
  }

  function handleSearch(e: Event) {
    const value = (e.target as HTMLInputElement).value;
    searchValue = value;
    if (debounceTimer) clearTimeout(debounceTimer);
    if (value.trim().length === 0) {
      results = [];
      total = 0;
      hasSearched = false;
      return;
    }
    debounceTimer = setTimeout(() => runSearch(value), 400);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && searchValue.trim()) {
      if (debounceTimer) clearTimeout(debounceTimer);
      runSearch(searchValue);
    }
  }

  async function loadMore() {
    if (!activeQuery) return;
    currentPage += 1;
    await runSearch(activeQuery, true);
  }

  let hasMore = $derived(total > results.length);

  // ── Album detail ──
  async function handleSelectAlbum(album: any) {
    $selectedAlbum = album;
    detailOpen = true;
    if (album.id && album.id > 0) {
      try {
        await loadAlbumDetail(source, album.id);
      } catch { /* search result may not be in DB */ }
    }
  }

  function closeDetail() {
    detailOpen = false;
  }

  // Re-run search when source changes (if there's an active query)
  $effect(() => {
    const _s = source;
    if (activeQuery) {
      currentPage = 1;
      runSearch(activeQuery);
    }
  });

  let searchInput: HTMLInputElement;
  onMount(() => {
    searchInput?.focus();
  });
</script>

<div class="page-header">
  <div>
    <div class="page-title">Search</div>
    <div class="page-subtitle">
      {#if loading}
        Searching {source}...
      {:else if hasSearched}
        {results.length} of {total} results · {source.charAt(0).toUpperCase() + source.slice(1)}
      {:else}
        Search albums on {source.charAt(0).toUpperCase() + source.slice(1)}
      {/if}
    </div>
  </div>
</div>

<!-- ═══ SEARCH ═══ -->
<div class="section-title">
  <span>Catalog Search</span>
  <span class="decoration">░▒▓</span>
</div>

<div class="toolbar">
  <input
    bind:this={searchInput}
    class="search-input"
    type="text"
    placeholder="Search albums, artists..."
    value={searchValue}
    oninput={handleSearch}
    onkeydown={handleKeydown}
  />

  <div class="toolbar-right">
    <div class="view-toggle">
      <button class="view-btn" class:active={viewMode === 'grid'} onclick={() => viewMode = 'grid'} title="Grid view">◧</button>
      <button class="view-btn" class:active={viewMode === 'table'} onclick={() => viewMode = 'table'} title="Table view">═</button>
    </div>
    <button
      class="view-btn select-toggle"
      class:active={selectMode}
      onclick={toggleSelectMode}
      title="Multi-select"
    >☑</button>
  </div>
</div>

{#if loading}
  <div class="loading-state">
    <span class="loading-text">Searching {source.charAt(0).toUpperCase() + source.slice(1)}...</span>
  </div>
{:else if results.length > 0}
  {#if viewMode === 'grid'}
    <AlbumGrid
      albums={results}
      onselect={handleSelectAlbum}
      selectable={selectMode}
      selectedIds={selectedAlbums}
      ontoggleselect={toggleAlbumSelect}
    />
  {:else}
    <AlbumTable
      albums={results}
      onselect={handleSelectAlbum}
      selectable={selectMode}
      selectedIds={selectedAlbums}
      ontoggleselect={toggleAlbumSelect}
    />
  {/if}

  {#if hasMore}
    <div class="load-more">
      <button class="btn btn-secondary btn-sm" onclick={loadMore} disabled={loadingMore}>
        {#if loadingMore}Loading...{:else}Load More ({total - results.length} remaining){/if}
      </button>
    </div>
  {/if}
{:else if hasSearched && searchValue.trim().length > 0}
  <div class="empty-state">
    <span class="empty-icon">◧</span>
    <p class="empty-text">No results for "{searchValue}"</p>
  </div>
{:else}
  <div class="empty-state">
    <span class="empty-icon">◧</span>
    <p class="empty-text">Type to search {source.charAt(0).toUpperCase() + source.slice(1)}</p>
  </div>
{/if}

<AlbumDetail album={detail} open={detailOpen} onclose={closeDetail} />

<!-- Floating batch action bar -->
{#if selectMode && selectedAlbums.size > 0}
  <div class="batch-bar">
    <span class="batch-count">{selectedAlbums.size} selected</span>
    <div class="batch-actions">
      <button class="btn btn-pop btn-sm" onclick={downloadSelected} disabled={batchDownloading}>
        {#if batchDownloading}Queuing...{:else}▸ Download{/if}
      </button>
      <button class="btn btn-secondary btn-sm" onclick={clearSelection}>Clear</button>
    </div>
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
    width: 360px;
  }
  .search-input:focus {
    border-color: var(--accent);
    box-shadow: var(--shadow-accent);
  }
  .search-input::placeholder { color: var(--text-tertiary); }

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

  .view-toggle {
    display: flex;
    border: 2px solid var(--border);
  }

  .view-btn {
    padding: var(--space-1) var(--space-2);
    font-size: var(--text-sm);
    background: var(--canvas-raised);
    color: var(--text-secondary);
    border: 2px solid var(--border);
    border-radius: 0;
    cursor: pointer;
    font-family: var(--font-family);
  }
  .view-toggle .view-btn { border: none; }
  .view-toggle .view-btn + .view-btn { border-left: 2px solid var(--border); }
  .view-btn.active { background: var(--accent); color: var(--text-inverse); }

  .select-toggle {
    font-size: var(--text-sm);
  }

  .load-more {
    display: flex;
    justify-content: center;
    padding: var(--space-8) 0;
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

  /* Floating batch action bar */
  .batch-bar {
    position: fixed;
    bottom: var(--space-6);
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: var(--space-4);
    background: var(--canvas-raised);
    border: 2px solid var(--accent);
    box-shadow: var(--shadow-md);
    padding: var(--space-3) var(--space-5);
    z-index: 100;
    white-space: nowrap;
  }

  .batch-count {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    font-weight: 700;
    letter-spacing: var(--tracking-mono);
    color: var(--text-primary);
  }

  .batch-actions {
    display: flex;
    gap: var(--space-2);
  }
</style>
