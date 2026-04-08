<script lang="ts">
  import { toasts, removeToast } from '$lib/stores/toast';
</script>

{#if $toasts.length > 0}
  <div class="toast-container">
    {#each $toasts as toast (toast.id)}
      <div class="toast toast-{toast.type}">
        <span class="toast-text">{toast.text}</span>
        <button class="toast-close" onclick={() => removeToast(toast.id)}>✕</button>
      </div>
    {/each}
  </div>
{/if}

<style>
  .toast-container {
    position: fixed;
    top: var(--space-5);
    right: var(--space-5);
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    max-width: 360px;
    width: 100%;
  }

  .toast {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border: 2px solid var(--border);
    background: var(--canvas-raised);
    box-shadow: var(--shadow-md);
    font-family: var(--font-family);
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-primary);
  }

  .toast-success {
    border-color: var(--positive);
    box-shadow: 5px 5px 0px rgba(56, 161, 105, 0.30);
  }

  .toast-error {
    border-color: var(--destructive);
    box-shadow: 5px 5px 0px rgba(197, 48, 48, 0.30);
  }

  .toast-info {
    border-color: var(--accent);
    box-shadow: var(--shadow-accent);
  }

  .toast-text {
    flex: 1;
    line-height: var(--leading-normal);
  }

  .toast-close {
    flex-shrink: 0;
    background: none;
    border: none;
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    cursor: pointer;
    padding: 0;
    line-height: 1;
    margin-top: 2px;
  }

  .toast-close:hover {
    color: var(--text-primary);
  }
</style>
