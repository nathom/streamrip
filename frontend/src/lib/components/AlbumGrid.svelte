<script lang="ts">
  import AlbumCard from './AlbumCard.svelte';

  let {
    albums,
    onselect,
  }: {
    albums: any[];
    onselect?: (album: any) => void;
  } = $props();
</script>

<div class="album-grid">
  {#each albums as album, i (album.source_album_id ?? album.id ?? i)}
    <AlbumCard {album} onclick={() => onselect?.(album)} />
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
