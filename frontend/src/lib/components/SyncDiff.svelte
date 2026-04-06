<script lang="ts">
  interface Album {
    id: string | number;
    title: string;
    artist: string;
    meta?: string; // e.g. "FLAC 24/96 · 2024" or "removed 3 days ago"
  }

  interface Props {
    label: string;
    icon_color: string;
    items: Album[];
    selectable?: boolean;
  }

  let { label, icon_color, items, selectable = false }: Props = $props();

  // Track checked state per item id
  let checked = $state<Set<string | number>>(new Set(items.map((a) => a.id)));

  function toggle(id: string | number) {
    if (!selectable) return;
    const next = new Set(checked);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    checked = next;
  }
</script>

<div class="sync-diff">
  <div class="diff-section-header">
    <div class="diff-label">
      <span style="color: {icon_color};">◆</span>
      {label}
    </div>
    <span class="diff-count">{items.length} album{items.length === 1 ? '' : 's'}</span>
  </div>

  {#each items as album (album.id)}
    <div
      class="diff-item"
      role={selectable ? 'checkbox' : 'listitem'}
      aria-checked={selectable ? checked.has(album.id) : undefined}
      tabindex={selectable ? 0 : undefined}
      onclick={() => toggle(album.id)}
      onkeydown={(e) => { if (selectable && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); toggle(album.id); } }}
    >
      {#if selectable}
        <div class="diff-checkbox" class:checked={checked.has(album.id)}></div>
      {:else}
        <div class="diff-spacer"></div>
      {/if}

      <div class="diff-item-info">
        <div class="diff-item-title" class:struck={!selectable}>{album.title}</div>
        <div class="diff-item-artist">{album.artist}</div>
      </div>

      {#if album.meta}
        <div class="diff-item-meta">{album.meta}</div>
      {/if}
    </div>
  {/each}
</div>

<style>
  .sync-diff {
    border: 2px solid var(--border);
    box-shadow: var(--shadow-md);
    background: var(--canvas-raised);
  }

  .diff-section-header {
    padding: var(--space-3) var(--space-4);
    background: var(--canvas-inset);
    border-bottom: 2px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .diff-label {
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .diff-count {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-tertiary);
  }

  .diff-item {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    gap: var(--space-3);
    font-size: var(--text-sm);
    cursor: default;
  }
  .diff-item:hover {
    background: var(--pop-subtle);
    transition: background-color 80ms;
  }

  /* Selectable items get pointer cursor */
  [role='checkbox'] { cursor: pointer; }

  .diff-checkbox {
    width: 20px;
    height: 20px;
    border: 2px solid #5e5b55;
    border-radius: 0;
    flex-shrink: 0;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    background: none;
  }
  .diff-checkbox.checked {
    background: var(--accent);
    border-color: var(--accent);
  }
  .diff-checkbox.checked::after {
    content: '';
    width: 8px;
    height: 8px;
    background: #1a1918;
  }

  /* Placeholder to align non-selectable rows with selectable rows */
  .diff-spacer {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }

  .diff-item-info {
    flex: 1;
    overflow: hidden;
  }

  .diff-item-title {
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .diff-item-title.struck {
    color: var(--text-secondary);
    text-decoration: line-through;
  }

  .diff-item-artist {
    font-size: var(--text-xs);
    color: var(--text-secondary);
  }

  .diff-item-meta {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-tertiary);
    text-align: right;
    white-space: nowrap;
  }
</style>
