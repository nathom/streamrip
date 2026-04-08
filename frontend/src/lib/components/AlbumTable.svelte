<script lang="ts">
  let {
    albums,
    onselect,
    selectable = false,
    selectedIds = new Set<string>(),
    ontoggleselect,
  }: {
    albums: any[];
    onselect?: (album: any) => void;
    selectable?: boolean;
    selectedIds?: Set<string>;
    ontoggleselect?: (id: string) => void;
  } = $props();

  let sortKey = $state<string>('');
  let sortDir = $state<'asc' | 'desc'>('asc');

  function albumId(album: any): string {
    return album.source_album_id || String(album.id);
  }

  function toggleSort(key: string) {
    if (sortKey === key) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortKey = key;
      sortDir = key === 'added_to_library_at' ? 'desc' : 'asc';
    }
  }

  function getSortValue(album: any, key: string): string | number {
    switch (key) {
      case 'title': return (album.title || '').toLowerCase();
      case 'artist': return (album.artist || '').toLowerCase();
      case 'year': return getYear(album);
      case 'format': return getFormat(album);
      case 'track_count': return album.track_count ?? 0;
      case 'status': return getStatus(album);
      case 'added_to_library_at': return album.added_to_library_at || '';
      default: return '';
    }
  }

  let sortedAlbums = $derived(() => {
    if (!sortKey) return albums;
    const sorted = [...albums].sort((a, b) => {
      const va = getSortValue(a, sortKey);
      const vb = getSortValue(b, sortKey);
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return sorted;
  });

  function sortIndicator(key: string): string {
    if (sortKey !== key) return '';
    return sortDir === 'asc' ? ' ▴' : ' ▾';
  }

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

  function formatDateAdded(ts: string | null | undefined): string {
    if (!ts) return '—';
    try {
      const d = new Date(ts);
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return '—';
    }
  }

  function handleRowClick(album: any) {
    if (selectable) {
      ontoggleselect?.(albumId(album));
    } else {
      onselect?.(album);
    }
  }

  // Select-all derived state
  let allSelected = $derived(
    albums.length > 0 && albums.every((a) => selectedIds.has(albumId(a)))
  );

  function toggleAll() {
    const listed = sortedAlbums();
    if (allSelected) {
      listed.forEach((a) => {
        if (selectedIds.has(albumId(a))) ontoggleselect?.(albumId(a));
      });
    } else {
      listed.forEach((a) => {
        if (!selectedIds.has(albumId(a))) ontoggleselect?.(albumId(a));
      });
    }
  }
</script>

<div class="album-table-wrapper">
  <table class="album-table">
    <thead>
      <tr>
        {#if selectable}
          <th class="col-check">
            <label class="checkbox-label">
              <input
                type="checkbox"
                class="sr-only"
                checked={allSelected}
                onchange={toggleAll}
              />
              <span class="checkbox-visual" class:checked={allSelected}></span>
            </label>
          </th>
        {/if}
        <th class="col-cover"></th>
        <th class="col-title sortable" onclick={() => toggleSort('title')}>Title{sortIndicator('title')}</th>
        <th class="col-artist sortable" onclick={() => toggleSort('artist')}>Artist{sortIndicator('artist')}</th>
        <th class="col-year sortable" onclick={() => toggleSort('year')}>Year{sortIndicator('year')}</th>
        <th class="col-format sortable" onclick={() => toggleSort('format')}>Format{sortIndicator('format')}</th>
        <th class="col-tracks sortable" onclick={() => toggleSort('track_count')}>Tracks{sortIndicator('track_count')}</th>
        <th class="col-added sortable" onclick={() => toggleSort('added_to_library_at')}>Added{sortIndicator('added_to_library_at')}</th>
        <th class="col-status sortable" onclick={() => toggleSort('status')}>Status{sortIndicator('status')}</th>
      </tr>
    </thead>
    <tbody>
      {#each sortedAlbums() as album, i (album.source_album_id ?? album.id ?? i)}
        <tr
          class="album-row"
          class:row-selected={selectable && selectedIds.has(albumId(album))}
          onclick={() => handleRowClick(album)}
          tabindex="0"
          onkeydown={(e) => e.key === 'Enter' && handleRowClick(album)}
        >
          {#if selectable}
            <td class="col-check" onclick={(e) => e.stopPropagation()}>
              <label class="checkbox-label">
                <input
                  type="checkbox"
                  class="sr-only"
                  checked={selectedIds.has(albumId(album))}
                  onchange={() => ontoggleselect?.(albumId(album))}
                />
                <span class="checkbox-visual" class:checked={selectedIds.has(albumId(album))}></span>
              </label>
            </td>
          {/if}
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
          <td class="col-added mono">{formatDateAdded(album.added_to_library_at)}</td>
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
    user-select: none;
  }

  th.sortable {
    cursor: pointer;
  }
  th.sortable:hover {
    color: var(--text-primary);
  }

  .album-row {
    border-bottom: 1px solid var(--border-subtle);
    cursor: pointer;
  }

  .album-row:hover {
    background: var(--pop-subtle);
    transition: background-color 80ms;
  }

  .album-row.row-selected {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }

  .album-row.row-selected:hover {
    background: color-mix(in srgb, var(--accent) 20%, transparent);
  }

  td {
    padding: var(--space-2) var(--space-3);
    vertical-align: middle;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 300px;
  }

  .col-check { width: 36px; padding: var(--space-1) var(--space-2); }
  .col-cover { width: 40px; padding: var(--space-1) var(--space-2); }
  .col-year, .col-tracks { width: 60px; }
  .col-format { width: 120px; }
  .col-added { width: 100px; }
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

  .title-text { font-weight: 600; }
  .col-artist { color: var(--text-secondary); }

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
  .status-text { font-size: var(--text-xs); color: var(--text-tertiary); }

  /* Checkbox */
  .checkbox-label {
    display: inline-flex;
    cursor: pointer;
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0,0,0,0);
    white-space: nowrap;
  }
  .checkbox-visual {
    display: block;
    width: 16px;
    height: 16px;
    border: 2px solid var(--border);
    background: var(--canvas-raised);
    flex-shrink: 0;
  }
  .checkbox-visual.checked {
    background: var(--accent);
    border-color: var(--accent);
  }
  .checkbox-visual.checked::after {
    content: '✓';
    display: block;
    color: var(--text-inverse);
    font-size: 11px;
    line-height: 1;
    text-align: center;
    font-weight: 800;
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
