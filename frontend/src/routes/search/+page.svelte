<script lang="ts">
  import { onMount } from 'svelte';
  import AlbumGrid from '$lib/components/AlbumGrid.svelte';
  import AlbumDetail from '$lib/components/AlbumDetail.svelte';
  import { currentSource, selectedAlbum, loadAlbumDetail } from '$lib/stores/library';
  import { api } from '$lib/api/client';

  let source = $derived($currentSource);
  let detail = $derived($selectedAlbum);

  let searchValue = $state('');
  let results = $state<any[]>([]);
  let loading = $state(false);
  let hasSearched = $state(false);
  let detailOpen = $state(false);
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  function handleSearch(e: Event) {
    const value = (e.target as HTMLInputElement).value;
    searchValue = value;
    if (debounceTimer) clearTimeout(debounceTimer);
    if (value.trim().length === 0) {
      results = [];
      hasSearched = false;
      return;
    }
    debounceTimer = setTimeout(async () => {
      loading = true;
      hasSearched = true;
      try {
        const data = await api.library.search(source, value.trim());
        results = Array.isArray(data) ? data : (data.albums ?? []);
      } catch (err) {
        console.error('Search failed', err);
        results = [];
      } finally {
        loading = false;
      }
    }, 400);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && searchValue.trim()) {
      if (debounceTimer) clearTimeout(debounceTimer);
      loading = true;
      hasSearched = true;
      api.library.search(source, searchValue.trim()).then(data => {
        results = Array.isArray(data) ? data : (data.albums ?? []);
      }).catch(err => {
        console.error('Search failed', err);
        results = [];
      }).finally(() => {
        loading = false;
      });
    }
  }

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
        {results.length} results · {source.charAt(0).toUpperCase() + source.slice(1)}
      {:else}
        Search albums on {source.charAt(0).toUpperCase() + source.slice(1)}
      {/if}
    </div>
  </div>
</div>

<div class="search-bar">
  <input
    bind:this={searchInput}
    class="search-input"
    type="text"
    placeholder="Search albums, artists..."
    value={searchValue}
    oninput={handleSearch}
    onkeydown={handleKeydown}
  />
</div>

{#if loading}
  <div class="loading-state">
    <span class="loading-text">Searching {source.charAt(0).toUpperCase() + source.slice(1)}...</span>
  </div>
{:else if results.length > 0}
  <div class="section-title">
    <span>Results</span>
    <span class="decoration">░▒▓</span>
  </div>
  <AlbumGrid albums={results} onselect={handleSelectAlbum} />
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

  .search-bar {
    margin-bottom: var(--space-8);
  }

  .search-input {
    font-family: var(--font-family);
    font-size: var(--text-lg);
    padding: var(--space-3) var(--space-4);
    border: 2px solid var(--border-subtle);
    border-radius: 0;
    background: var(--canvas-inset);
    color: var(--text-primary);
    outline: none;
    width: 100%;
    max-width: 600px;
  }
  .search-input:focus {
    border-color: var(--accent);
    box-shadow: var(--shadow-accent);
  }
  .search-input::placeholder { color: var(--text-tertiary); }

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
</style>
