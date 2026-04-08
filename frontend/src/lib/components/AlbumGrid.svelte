<script lang="ts">
  import AlbumCard from './AlbumCard.svelte';

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

  function albumId(album: any): string {
    return album.source_album_id || String(album.id);
  }

  function handleCardClick(album: any) {
    if (selectable) {
      ontoggleselect?.(albumId(album));
    } else {
      onselect?.(album);
    }
  }
</script>

<div class="album-grid">
  {#each albums as album, i (album.source_album_id ?? album.id ?? i)}
    <div class="card-wrapper" class:selected={selectable && selectedIds.has(albumId(album))}>
      {#if selectable}
        <label class="checkbox-overlay">
          <input
            type="checkbox"
            class="sr-only"
            checked={selectedIds.has(albumId(album))}
            onchange={(e) => { e.stopPropagation(); ontoggleselect?.(albumId(album)); }}
          />
          <span class="checkbox-visual" class:checked={selectedIds.has(albumId(album))}></span>
        </label>
      {/if}
      <AlbumCard {album} onclick={() => handleCardClick(album)} />
    </div>
  {/each}

  {#if albums.length === 0}
    <div class="empty-state">
      <span class="empty-icon">◧</span>
      <p class="empty-label">No albums found</p>
    </div>
  {/if}
</div>

<style>
  .album-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: var(--space-5);
  }

  .card-wrapper {
    position: relative;
  }

  .card-wrapper.selected {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .checkbox-overlay {
    position: absolute;
    top: var(--space-2);
    left: var(--space-2);
    z-index: 2;
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
    width: 18px;
    height: 18px;
    border: 2px solid var(--border);
    background: var(--canvas-raised);
    box-shadow: var(--shadow-sm);
  }

  .checkbox-visual.checked {
    background: var(--accent);
    border-color: var(--accent);
  }

  .checkbox-visual.checked::after {
    content: '✓';
    display: block;
    color: var(--text-inverse);
    font-size: 12px;
    line-height: 1;
    text-align: center;
    font-weight: 800;
  }

  .empty-state {
    grid-column: 1 / -1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--space-16);
    gap: var(--space-3);
    color: var(--text-tertiary);
  }

  .empty-icon {
    font-size: 48px;
    opacity: 0.3;
  }

  .empty-label {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    letter-spacing: var(--tracking-mono);
  }
</style>
