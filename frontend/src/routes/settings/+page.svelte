<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';

  // Config state
  let qobuzUserId = $state('');
  let qobuzAuthToken = $state('');
  let qobuzQuality = $state('3');
  let qobuzDownloadBooklets = $state(true);
  let qobuzConnected = $state(false);

  let tidalConnected = $state(false);

  let downloadPath = $state('');
  let maxConnections = $state(6);
  let sourceSubdirectories = $state(false);
  let discSubdirectories = $state(true);
  let folderFormat = $state('{albumartist} - {title} ({year}) [{container}]');
  let trackFormat = $state('{tracknumber:02}. {artist} - {title}{explicit}');

  let embedArtwork = $state(true);
  let artworkSize = $state('large');

  let conversionEnabled = $state(false);
  let conversionCodec = $state('FLAC');
  let conversionSamplingRate = $state(48000);
  let conversionBitDepth = $state(24);

  let autoSyncEnabled = $state(false);
  let syncInterval = $state('6h');

  let saving = $state(false);
  let saveError = $state('');
  let saveSuccess = $state(false);

  onMount(async () => {
    try {
      const config = await api.config.get();
      if (config) {
        qobuzUserId = config.qobuz_user_id ?? '';
        qobuzAuthToken = config.qobuz_token ?? '';
        qobuzQuality = String(config.qobuz_quality ?? 3);
        qobuzDownloadBooklets = config.qobuz_download_booklets ?? true;
        // Check actual auth status, not just whether token exists
        try {
          const statuses = await api.auth.status();
          const qobuz = statuses.find((s: any) => s.source === 'qobuz');
          const tidal = statuses.find((s: any) => s.source === 'tidal');
          qobuzConnected = qobuz?.authenticated ?? false;
          tidalConnected = tidal?.authenticated ?? false;
        } catch {
          qobuzConnected = !!config.qobuz_token;
          tidalConnected = !!config.tidal_access_token;
        }

        downloadPath = config.downloads_path ?? '';
        maxConnections = config.max_connections ?? 6;
        sourceSubdirectories = config.source_subdirectories ?? false;
        discSubdirectories = config.disc_subdirectories ?? true;
        folderFormat = config.folder_format ?? '{albumartist} - {title} ({year}) [{container}]';
        trackFormat = config.track_format ?? '{tracknumber:02}. {artist} - {title}{explicit}';

        embedArtwork = config.embed_artwork ?? true;
        artworkSize = config.artwork_size ?? 'large';

        conversionEnabled = config.conversion_enabled ?? false;
        conversionCodec = config.conversion_codec ?? 'FLAC';
        conversionSamplingRate = config.conversion_sampling_rate ?? 48000;
        conversionBitDepth = config.conversion_bit_depth ?? 24;

        autoSyncEnabled = config.auto_sync_enabled ?? false;
        syncInterval = config.auto_sync_interval ?? '6h';
      }
    } catch (e) {
      // Config not yet set — use defaults
    }
  });

  async function saveSettings() {
    saving = true;
    saveError = '';
    saveSuccess = false;
    try {
      await api.config.update({
        qobuz_user_id: qobuzUserId,
        qobuz_token: qobuzAuthToken,
        qobuz_quality: parseInt(qobuzQuality),
        qobuz_download_booklets: qobuzDownloadBooklets,
        downloads_path: downloadPath,
        max_connections: maxConnections,
        source_subdirectories: sourceSubdirectories,
        disc_subdirectories: discSubdirectories,
        folder_format: folderFormat,
        track_format: trackFormat,
        embed_artwork: embedArtwork,
        artwork_size: artworkSize,
        conversion_enabled: conversionEnabled,
        conversion_codec: conversionCodec,
        conversion_sampling_rate: conversionSamplingRate,
        conversion_bit_depth: conversionBitDepth,
        auto_sync_enabled: autoSyncEnabled,
        auto_sync_interval: syncInterval,
      });

      // Refresh auth status after save (backend hot-reloads clients)
      try {
        const statuses = await api.auth.status();
        const qobuz = statuses.find((s: any) => s.source === 'qobuz');
        const tidal = statuses.find((s: any) => s.source === 'tidal');
        qobuzConnected = qobuz?.authenticated ?? false;
        tidalConnected = tidal?.authenticated ?? false;
      } catch {
        // ignore auth check failure
      }

      saveSuccess = true;
      setTimeout(() => { saveSuccess = false; }, 2500);
    } catch (e: any) {
      saveError = e?.message ?? 'Failed to save settings';
    } finally {
      saving = false;
    }
  }
</script>

<div class="page-header">
  <div>
    <div class="page-title">Settings</div>
    <div class="page-subtitle">Configuration</div>
  </div>
  <div class="header-actions">
    {#if saveError}
      <span class="save-error">{saveError}</span>
    {/if}
    {#if saveSuccess}
      <span class="save-ok">Saved</span>
    {/if}
    <button class="btn btn-primary btn-sm" onclick={saveSettings} disabled={saving}>
      {saving ? 'Saving…' : 'Save Changes'}
    </button>
  </div>
</div>

<!-- ── Qobuz ── -->
<div class="settings-section">
  <div class="settings-section-header">
    <span>◆ Qobuz</span>
    {#if qobuzConnected}
      <span class="tag tag-positive">Connected</span>
    {:else}
      <span class="tag tag-default">Not Connected</span>
    {/if}
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">User ID</div>
      <div class="settings-label-sub">Numeric ID from API</div>
    </div>
    <input
      class="settings-input"
      type="text"
      placeholder="2113276"
      bind:value={qobuzUserId}
      style="max-width: 200px;"
    />
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Auth Token</div>
      <div class="settings-label-sub">From browser DevTools</div>
    </div>
    <input
      class="settings-input"
      type="password"
      placeholder="kwycOGex9OgEhfym8MFUxf…"
      bind:value={qobuzAuthToken}
      style="max-width: 400px;"
    />
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Quality</div>
    </div>
    <select class="settings-select" bind:value={qobuzQuality} style="max-width: 220px;">
      <option value="1">320kbps MP3</option>
      <option value="2">16-bit / 44.1kHz</option>
      <option value="3">24-bit / up to 96kHz</option>
      <option value="4">24-bit / up to 192kHz</option>
    </select>
  </div>
  <div class="settings-row">
    <div>
      <div class="settings-label">Download Booklets</div>
      <div class="settings-label-sub">Download PDF booklets included with albums</div>
    </div>
    <div class="toggle-track" class:on={qobuzDownloadBooklets} onclick={() => qobuzDownloadBooklets = !qobuzDownloadBooklets}>
      <div class="toggle-thumb"></div>
    </div>
  </div>
</div>

<!-- ── Tidal ── -->
<div class="settings-section">
  <div class="settings-section-header">
    <span>◆ Tidal</span>
    {#if tidalConnected}
      <span class="tag tag-positive">Connected</span>
    {:else}
      <span class="tag tag-default">Not Connected</span>
    {/if}
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Login</div>
      <div class="settings-label-sub">OAuth device flow</div>
    </div>
    <button class="btn btn-secondary btn-sm">Connect Tidal</button>
  </div>
</div>

<!-- ── Downloads ── -->
<div class="settings-section">
  <div class="settings-section-header">
    <span>◆ Downloads</span>
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Download Path</div>
    </div>
    <input
      class="settings-input"
      type="text"
      placeholder="/mnt/music/StreamripDownloads"
      bind:value={downloadPath}
    />
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Max Connections</div>
    </div>
    <input
      class="settings-input"
      type="number"
      min="1"
      max="20"
      bind:value={maxConnections}
      style="max-width: 80px;"
    />
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Folder Format</div>
      <div class="settings-label-sub">{'{albumartist}'}, {'{title}'}, {'{year}'}, etc.</div>
    </div>
    <input
      class="settings-input"
      type="text"
      bind:value={folderFormat}
    />
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Track Format</div>
    </div>
    <input
      class="settings-input"
      type="text"
      bind:value={trackFormat}
    />
  </div>
  <div class="settings-row">
    <div>
      <div class="settings-label">Source Subdirectories</div>
      <div class="settings-label-sub">Put albums in Qobuz/, Tidal/ subfolders</div>
    </div>
    <div class="toggle-track" class:on={sourceSubdirectories} onclick={() => sourceSubdirectories = !sourceSubdirectories}>
      <div class="toggle-thumb"></div>
    </div>
  </div>
  <div class="settings-row" style="border-bottom: none;">
    <div>
      <div class="settings-label">Disc Subdirectories</div>
      <div class="settings-label-sub">Create Disc N subfolders for multi-disc albums</div>
    </div>
    <div class="toggle-track" class:on={discSubdirectories} onclick={() => discSubdirectories = !discSubdirectories}>
      <div class="toggle-thumb"></div>
    </div>
  </div>
</div>

<!-- ── Artwork ── -->
<div class="settings-section">
  <div class="settings-section-header">
    <span>◆ Artwork</span>
  </div>
  <div class="settings-row">
    <div>
      <div class="settings-label">Embed Artwork</div>
      <div class="settings-label-sub">Write cover art into audio file tags</div>
    </div>
    <div class="toggle-track" class:on={embedArtwork} onclick={() => embedArtwork = !embedArtwork}>
      <div class="toggle-thumb"></div>
    </div>
  </div>
  <div class="settings-row" style="border-bottom: none;">
    <div>
      <div class="settings-label">Artwork Size</div>
    </div>
    <select class="settings-select" bind:value={artworkSize} style="max-width: 160px;">
      <option value="thumbnail">Thumbnail</option>
      <option value="small">Small</option>
      <option value="large">Large</option>
      <option value="original">Original (up to 30MB)</option>
    </select>
  </div>
</div>

<!-- ── Conversion ── -->
<div class="settings-section">
  <div class="settings-section-header">
    <span>◆ Conversion</span>
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Enable Conversion</div>
    </div>
    <button
      class="toggle-track"
      class:on={conversionEnabled}
      onclick={() => { conversionEnabled = !conversionEnabled; }}
      aria-pressed={conversionEnabled}
      aria-label="Enable conversion"
    >
      <div class="toggle-thumb"></div>
    </button>
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Codec</div>
    </div>
    <select class="settings-select" bind:value={conversionCodec} style="max-width: 160px;">
      <option value="FLAC">FLAC</option>
      <option value="ALAC">ALAC</option>
      <option value="OGG">OGG Vorbis</option>
      <option value="MP3">MP3</option>
      <option value="AAC">AAC</option>
    </select>
  </div>
  <div class="settings-row">
    <div>
      <div class="settings-label">Max Sampling Rate</div>
      <div class="settings-label-sub">Downsample if higher (Hz)</div>
    </div>
    <select class="settings-select" bind:value={conversionSamplingRate} style="max-width: 160px;">
      <option value={44100}>44.1 kHz</option>
      <option value={48000}>48 kHz</option>
      <option value={96000}>96 kHz</option>
      <option value={192000}>192 kHz</option>
    </select>
  </div>
  <div class="settings-row" style="border-bottom: none;">
    <div>
      <div class="settings-label">Max Bit Depth</div>
    </div>
    <select class="settings-select" bind:value={conversionBitDepth} style="max-width: 160px;">
      <option value={16}>16-bit</option>
      <option value={24}>24-bit</option>
    </select>
  </div>
</div>

<!-- ── Auto Sync ── -->
<div class="settings-section">
  <div class="settings-section-header">
    <span>◆ Auto Sync</span>
  </div>

  <div class="settings-row">
    <div>
      <div class="settings-label">Enable Auto Sync</div>
      <div class="settings-label-sub">Automatically download new library additions</div>
    </div>
    <button
      class="toggle-track"
      class:on={autoSyncEnabled}
      onclick={() => { autoSyncEnabled = !autoSyncEnabled; }}
      aria-pressed={autoSyncEnabled}
      aria-label="Enable auto sync"
    >
      <div class="toggle-thumb"></div>
    </button>
  </div>

  <div class="settings-row" style="border-bottom: none;">
    <div>
      <div class="settings-label">Sync Interval</div>
    </div>
    <select class="settings-select" bind:value={syncInterval} style="max-width: 160px;">
      <option value="1h">Every hour</option>
      <option value="6h">Every 6 hours</option>
      <option value="daily">Daily</option>
      <option value="custom">Custom cron</option>
    </select>
  </div>
</div>

<style>
  /* ── Page header ── */
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
    margin-top: var(--space-1);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .save-error {
    font-size: var(--text-xs);
    color: var(--destructive);
    font-weight: 600;
  }

  .save-ok {
    font-size: var(--text-xs);
    color: var(--positive);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
  }

  /* ── Settings section card ── */
  .settings-section {
    border: 2px solid var(--border);
    box-shadow: var(--shadow-sm);
    background: var(--canvas-raised);
    margin-bottom: var(--space-5);
  }

  .settings-section-header {
    padding: var(--space-3) var(--space-4);
    border-bottom: 2px solid var(--border);
    font-size: var(--text-sm);
    font-weight: 700;
    background: var(--canvas-inset);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  /* ── Settings rows ── */
  .settings-row {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: var(--space-4);
    align-items: center;
  }

  .settings-label {
    font-size: var(--text-sm);
    font-weight: 600;
  }

  .settings-label-sub {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    margin-top: 2px;
  }

  /* ── Inputs ── */
  .settings-input {
    font-family: var(--font-family);
    font-size: var(--text-sm);
    padding: var(--space-2) var(--space-3);
    border: 2px solid var(--border-subtle);
    border-radius: 0;
    background: var(--canvas-inset);
    color: var(--text-primary);
    outline: none;
    width: 100%;
  }

  .settings-input:focus {
    border-color: var(--accent);
    box-shadow: var(--shadow-accent);
  }

  .settings-input::placeholder {
    color: var(--text-tertiary);
  }

  .settings-select {
    font-family: var(--font-family);
    font-size: var(--text-sm);
    padding: var(--space-2) var(--space-3);
    border: 2px solid var(--border-subtle);
    border-radius: 0;
    background: var(--canvas-inset);
    color: var(--text-primary);
    outline: none;
    -webkit-appearance: none;
    width: 100%;
    cursor: pointer;
  }

  .settings-select:focus {
    border-color: var(--accent);
    box-shadow: var(--shadow-accent);
  }

  /* ── Toggle ── */
  .toggle-track {
    width: 40px;
    height: 20px;
    border: 2px solid var(--border);
    background: var(--canvas-inset);
    cursor: pointer;
    position: relative;
    display: inline-block;
    border-radius: 0;
    padding: 0;
    flex-shrink: 0;
  }

  .toggle-track.on {
    background: var(--accent);
    border-color: var(--accent);
  }

  .toggle-thumb {
    width: 12px;
    height: 12px;
    background: var(--text-primary);
    position: absolute;
    top: 2px;
    left: 2px;
    transition: left 80ms ease;
  }

  .toggle-track.on .toggle-thumb {
    left: 22px;
    background: #1a1918;
  }

  /* ── Shared btn/tag (re-used from global tokens) ── */
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

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary {
    background: var(--accent);
    color: var(--text-inverse);
    box-shadow: var(--shadow-accent);
  }

  .btn-primary:hover:not(:disabled) { box-shadow: var(--shadow-lg); }
  .btn-primary:active:not(:disabled) { box-shadow: 1px 1px 0 rgba(0,0,0,0.3); transform: translate(1px, 1px); }

  .btn-secondary {
    background: var(--canvas-raised);
    color: var(--text-primary);
    box-shadow: var(--shadow-sm);
  }

  .btn-sm {
    font-size: var(--text-xs);
    padding: var(--space-1) var(--space-3);
  }

  .tag {
    font-size: 10px;
    font-weight: 700;
    padding: 2px var(--space-2);
    border: 1.5px solid var(--border);
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    display: inline-block;
  }

  .tag-positive {
    background: var(--positive);
    color: var(--text-primary);
  }

  .tag-default {
    background: var(--canvas-raised);
    color: var(--text-secondary);
  }
</style>
