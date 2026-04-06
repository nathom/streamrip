<script lang="ts">
  import SyncDiff from '$lib/components/SyncDiff.svelte';

  // ── Static placeholder data (API will be wired in Phase 5) ──────────────────

  const stats = {
    inLibrary: 247,
    downloaded: 198,
    newCount: 6,
    missing: 2,
  };

  const newAlbums = [
    { id: 1, title: 'Brat',                  artist: 'Charli xcx',       meta: 'FLAC 24/44 · 2024' },
    { id: 2, title: 'GNX',                   artist: 'Kendrick Lamar',   meta: 'FLAC 24/96 · 2024' },
    { id: 3, title: 'Bright Future',          artist: 'Adrianne Lenker',  meta: 'FLAC 24/96 · 2024' },
    { id: 4, title: 'Lives Outgrown',         artist: 'Beth Gibbons',     meta: 'FLAC 24/96 · 2024' },
    { id: 5, title: 'Imaginal Disk',          artist: 'Magdalena Bay',    meta: 'FLAC 16/44 · 2024' },
    { id: 6, title: 'Only God Was Above Us',  artist: 'Vampire Weekend',  meta: 'FLAC 24/96 · 2024' },
  ];

  const removedAlbums = [
    { id: 7, title: 'Random Album Title', artist: 'Deadmau5',  meta: 'removed 3 days ago' },
    { id: 8, title: 'Trilithon',          artist: 'Kiasmos',   meta: 'removed 1 week ago' },
  ];

  function handleSyncNow() {
    // TODO Phase 5: trigger sync API call
    console.log('Sync Now');
  }

  function handleSchedule() {
    // TODO Phase 5: open schedule modal
    console.log('Schedule');
  }

  function handleDownloadAll() {
    // TODO Phase 5: download all new albums
    console.log('Download All');
  }
</script>

<div class="page-header">
  <div>
    <div class="page-title">Sync</div>
    <div class="page-subtitle">Last sync: 2 hours ago · Qobuz</div>
  </div>
  <div class="header-actions">
    <button class="btn btn-primary btn-sm" onclick={handleSyncNow}>▸ Sync Now</button>
    <button class="btn btn-secondary btn-sm" onclick={handleSchedule}>Schedule</button>
  </div>
</div>

<!-- ── Stats row ──────────────────────────────────────────────────────────── -->
<div class="stats-row">
  <div class="stat-card">
    <div class="stat-label">In Library</div>
    <div class="stat-value">{stats.inLibrary}</div>
    <div class="stat-sub">albums on Qobuz</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Downloaded</div>
    <div class="stat-value" style="color: var(--positive);">{stats.downloaded}</div>
    <div class="stat-sub">albums local</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">New</div>
    <div class="stat-value" style="color: var(--pop);">{stats.newCount}</div>
    <div class="stat-sub">not yet downloaded</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Missing</div>
    <div class="stat-value" style="color: var(--destructive);">{stats.missing}</div>
    <div class="stat-sub">removed from library</div>
  </div>
</div>

<!-- ── New in Library ─────────────────────────────────────────────────────── -->
<div class="section-title">
  <span>New in Library</span>
  <span class="decoration">░▒▓</span>
</div>

<div class="diff-wrapper">
  <SyncDiff
    label="Added since last sync"
    icon_color="var(--pop)"
    items={newAlbums}
    selectable={true}
  />
  <div class="diff-toolbar">
    <button class="btn btn-pop btn-sm" onclick={handleDownloadAll}>▸ Download All</button>
  </div>
</div>

<!-- ── Removed from Library ───────────────────────────────────────────────── -->
<div class="section-title" style="margin-top: var(--space-8);">
  <span>Removed from Library</span>
  <span class="decoration">░▒▓</span>
</div>

<SyncDiff
  label="No longer in streaming library"
  icon_color="var(--destructive)"
  items={removedAlbums}
  selectable={false}
/>

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
    gap: var(--space-3);
    align-items: center;
  }

  /* ── Stats ── */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-4);
    margin-bottom: var(--space-6);
  }

  .stat-card {
    border: 2px solid var(--border);
    padding: var(--space-4);
    background: var(--canvas-raised);
    box-shadow: var(--shadow-sm);
  }

  .stat-label {
    font-size: var(--text-xs);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    color: var(--text-tertiary);
    margin-bottom: var(--space-1);
  }

  .stat-value {
    font-size: var(--text-2xl);
    font-weight: 800;
    letter-spacing: var(--tracking-tight);
  }

  .stat-sub {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-tertiary);
    letter-spacing: var(--tracking-mono);
    margin-top: 2px;
  }

  /* ── Section title (matches global .section-title from mockup) ── */
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

  /* ── Diff wrapper: positions the Download All button below the diff ── */
  .diff-wrapper {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin-bottom: var(--space-2);
  }

  .diff-toolbar {
    display: flex;
    justify-content: flex-end;
  }

  /* ── Button base (mirrors global .btn) ── */
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

  .btn-sm {
    font-size: var(--text-xs);
    padding: var(--space-1) var(--space-3);
  }

  .btn-primary {
    background: var(--accent);
    color: var(--text-inverse);
    box-shadow: var(--shadow-accent);
  }
  .btn-primary:hover { box-shadow: var(--shadow-lg); }
  .btn-primary:active { box-shadow: 1px 1px 0 rgba(0, 0, 0, 0.3); transform: translate(1px, 1px); }

  .btn-secondary {
    background: var(--canvas-raised);
    color: var(--text-primary);
    box-shadow: var(--shadow-sm);
  }

  .btn-pop {
    background: var(--pop);
    color: var(--text-inverse);
    box-shadow: var(--shadow-pop);
  }
  .btn-pop:hover { box-shadow: var(--shadow-lg); }
  .btn-pop:active { box-shadow: 1px 1px 0 rgba(0, 0, 0, 0.3); transform: translate(1px, 1px); }
</style>
