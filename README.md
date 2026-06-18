![streamrip logo](https://github.com/nathom/streamrip/blob/dev/demo/logo.svg?raw=true)

[![Downloads](https://pepy.tech/badge/streamrip)](https://pepy.tech/project/streamrip)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/python/black)

> **Note:** This is a personal fork of [nathom/streamrip](https://github.com/nathom/streamrip) used to test and integrate pending patches, primarily related to Deezer. It is not intended for general use — refer to the upstream project for stable releases.

## Changes from upstream

The following fixes and improvements are present in this fork on top of [`nathom/streamrip:dev`](https://github.com/nathom/streamrip/tree/dev):

**Deezer**
- Support for `link.deezer.com/s/` short URLs ([#887](https://github.com/nathom/streamrip/pull/887))
- Download liked tracks from a user profile URL (`/profile/USER_ID/loved`)
- Use the GW API for playlist fetching to avoid breakage on the public API ([#973](https://github.com/nathom/streamrip/pull/973))
- Include all artists from the `contributors` array in track and album metadata ([#907](https://github.com/nathom/streamrip/pull/907))
- Automatic redirect resolution for albums, playlists and artists (handles moved/deleted IDs)
- In-memory album metadata cache — avoids redundant API calls when the same album is fetched multiple times in one session ([#1000](https://github.com/nathom/streamrip/pull/1000))
- In-memory GW track data cache — `get_track()` stores the GW response so that `get_downloadable()` can reuse it without a second `song.getData` call, halving GW API requests per album download
- Connection pool sized to `max(max_connections × 4, 32)` to prevent urllib3 "pool full" warnings under concurrent downloads ([#997](https://github.com/nathom/streamrip/pull/997))
- REST API rate limiter capped at 10 req/sec — Deezer's public API returns errors above this threshold; the limiter prevents throttling under concurrent downloads
- Playlist tracks skip the per-track album fetch (saves 2 REST calls per track); GENRE, TRACKTOTAL, and DISCTOTAL tags are omitted for playlist tracks as a result. Reduces download time by 10 seconds for 100 tracks.
- Quality fallback: if the requested quality is unavailable, silently falls back to a lower tier instead of crashing
- Composer tag sourced from `SNG_CONTRIBUTORS` via the GW API (absent from the public REST API)
- Lyricist/author tag sourced from `SNG_CONTRIBUTORS` → `LYRICIST` (FLAC), `TEXT` (MP3), iTunes freeform atom (MP4)
- BPM tag written when available
- ReplayGain track gain (`GAIN` field from GW API) written as `REPLAYGAIN_TRACK_GAIN` to FLAC, `TXXX:replaygain_track_gain` to MP3, and iTunes freeform atom to MP4
- Fix `KeyError` when `disk_number` is absent from the last track in a Deezer album response ([#994](https://github.com/nathom/streamrip/pull/994))

**Tidal**
- MPEG-DASH manifest (`application/dash+xml`) support for `HI_RES_LOSSLESS` streams — required since Tidal dropped MQA ([#974](https://github.com/nathom/streamrip/issues/974), [#981](https://github.com/nathom/streamrip/issues/981))
- Updated quality tier name `HI_RES` → `HI_RES_LOSSLESS` throughout the quality maps ([#974](https://github.com/nathom/streamrip/issues/974))
- Composer tag populated from the `/contributors` endpoint (fetched concurrently with lyrics)
- Fix `AttributeError` when the DASH `SegmentTemplate` has no `media` attribute
- Fix infinite recursion / `KeyError` when BTS manifest decode fails at quality 0 ([#892](https://github.com/nathom/streamrip/issues/892))
- Fix `TypeError: len(None)` when the `artists` field is absent from a track response
- Fix `KeyError` when `audioQuality` returns an unknown value (e.g. new tiers)

**Qobuz**
- Fall back to `album.artist.name` when the track-level `performer` field is absent — fixes `AssertionError` on compilation albums ([#610](https://github.com/nathom/streamrip/issues/610))
- Replace `assert status == 200` guards with proper `NonStreamableError` exceptions (asserts are silently disabled by Python's `-O` flag) ([#780](https://github.com/nathom/streamrip/issues/780))
- Fix silent wrong-quality bug in `get_quality()`: passing `quality=0` would return the 24-bit format via Python's negative index instead of raising an error

**SoundCloud**
- Replace `assert url is not None` with a graceful `NON_STREAMABLE` return when no HLS stream is found for a track
- Replace all remaining `assert status == 200` guards in `search`, `resolve_url`, `_get_track`, `_get_playlist`, and `get_downloadable` with `NonStreamableError` exceptions

**All clients**
- `asyncio.Lock` on each client prevents concurrent login races when multiple URLs from the same source are resolved in parallel

**Downloads**
- `fast_async_download` runs the `requests` HTTP call inside `asyncio.to_thread` so it no longer blocks the event loop during concurrent downloads ([#982](https://github.com/nathom/streamrip/pull/982))
- `fast_async_download` now calls `raise_for_status()` so HTTP errors (4xx/5xx) surface as exceptions instead of silently writing the error body to disk; the partial file is removed on failure
- Fix `truncate_str` to explicitly use UTF-8 encoding and skip the encode/decode round-trip when the filename is already within the 255-byte limit

**Converter**
- OGG/OPUS: cover art is embedded post-conversion via `mutagen` (`METADATA_BLOCK_PICTURE`), and `-vn` prevents an unwanted Theora video stream ([#992](https://github.com/nathom/streamrip/pull/992))
- AAC: uses `libfdk_aac` when available, falls back to the native FFmpeg `aac` encoder ([#990](https://github.com/nathom/streamrip/pull/990))
- `OPUS` exposed as a `-c`/`--codec` option in the CLI ([#989](https://github.com/nathom/streamrip/pull/989))
- FFmpeg `stdin` redirected to `/dev/null` to prevent terminal echo/raw-mode corruption after a rip ([#996](https://github.com/nathom/streamrip/pull/996))

**CLI / misc**
- `-l`/`--log-file` option writes all log messages at DEBUG level to a file for post-mortem analysis ([#81](https://github.com/nathom/streamrip/issues/81))
- Version check is resilient to network errors and non-JSON responses (e.g. GitHub 504) ([#995](https://github.com/nathom/streamrip/pull/995))
- Version comparison is numeric (`1.10 > 1.9`) rather than lexicographic

---

A scriptable stream downloader for Qobuz, Tidal, Deezer and SoundCloud.

![downloading an album](https://github.com/nathom/streamrip/blob/dev/demo/download_album.png?raw=true)

## Features

- Fast, concurrent downloads powered by `aiohttp`
- Downloads tracks, albums, playlists, discographies, and labels from Qobuz, Tidal, Deezer, and SoundCloud
- Downloads Deezer liked tracks from a user profile (`/profile/USER_ID/loved`)
- Supports downloads of Spotify and Apple Music playlists through [last.fm](https://www.last.fm)
- Automatically converts files to a preferred format
- Has a database that stores the downloaded tracks' IDs so that repeats are avoided
- Concurrency and rate limiting
- Interactive search for all sources
- Highly customizable through the config file
- Integration with `youtube-dl`

## Installation

First, ensure [Python](https://www.python.org/downloads/) (version 3.10 or greater) and [pip](https://pip.pypa.io/en/stable/installing/) are installed. Then install `ffmpeg`. You may choose not to install this, but some functionality will be limited.

Install this fork directly from the `dev` branch:

```bash
pip3 install git+https://github.com/berettavexee/streamrip.git@dev
```

> **Note:** `pip3 install streamrip --upgrade` installs the upstream release from PyPI, not this fork. Use the command above to get the patches listed below.

When you type

```bash
rip
```

it should show the main help page. If you have no idea what these mean, or are having other issues installing, check out the [detailed installation instructions](https://github.com/nathom/streamrip/wiki#detailed-installation-instructions).

## Example Usage

**For Tidal and Qobuz, you NEED a premium subscription.**

Download an album from Qobuz

```bash
rip url https://www.qobuz.com/us-en/album/rumours-fleetwood-mac/0603497941032
```

Download multiple albums from Qobuz

```bash
rip url https://www.qobuz.com/us-en/album/back-in-black-ac-dc/0886444889841 https://www.qobuz.com/us-en/album/blue-train-john-coltrane/0060253764852
```

Download the album and convert it to `mp3`

```bash
rip --codec mp3 url https://open.qobuz.com/album/0060253780968
```

To set the maximum quality, use the `--quality` option to `0, 1, 2, 3, 4`:

| Quality ID | Audio Quality         | Available Sources                            |
| ---------- | --------------------- | -------------------------------------------- |
| 0          | 128 kbps MP3 or AAC   | Deezer, Tidal, SoundCloud (most of the time) |
| 1          | 320 kbps MP3 or AAC   | Deezer, Tidal, Qobuz, SoundCloud (rarely)    |
| 2          | 16 bit, 44.1 kHz (CD) | Deezer, Tidal, Qobuz, SoundCloud (rarely)    |
| 3          | 24 bit, ≤ 96 kHz      | Tidal (MQA), Qobuz, SoundCloud (rarely)      |
| 4          | 24 bit, ≤ 192 kHz     | Qobuz                                        |

```bash
rip --quality 3 url https://tidal.com/browse/album/147569387
```

> Using `4` is generally a waste of space. It is impossible for humans to perceive the difference between sampling rates higher than 44.1 kHz. It may be useful if you're processing/slowing down the audio.

Search for playlists matching `rap` on Tidal

```bash
rip search tidal playlist 'rap'
```

![streamrip interactive search](https://github.com/nathom/streamrip/blob/dev/demo/playlist_search.png?raw=true)

Search for *Rumours* on Tidal, and download it

```bash
rip search tidal album 'fleetwood mac rumours'
```

Download a last.fm playlist using the lastfm command

```
rip lastfm https://www.last.fm/user/nathan3895/playlists/12126195
```

Download your Deezer liked tracks

```bash
rip url https://www.deezer.com/fr/profile/USER_ID/loved
```

For more customization, see the config file

```
rip config open
```

If you're confused about anything, see the help pages. The main help pages can be accessed by typing `rip` by itself in the command line. The help pages for each command can be accessed with the `--help` flag. For example, to see the help page for the `url` command, type

```
rip url --help
```

![example_help_page.png](https://github.com/nathom/streamrip/blob/dev/demo/example_help_page.png?raw=true)

## Other information

For more in-depth information about `streamrip`, see the help pages and the [wiki](https://github.com/nathom/streamrip/wiki/).

## Contributions

All contributions are appreciated! You can help out the project by opening an issue
or by submitting code.

### Issues

If you're opening an issue **use the Feature Request or Bug Report templates properly**. This ensures
that I have all of the information necessary to debug the issue. If you do not follow the templates,
**I will silently close the issue** and you'll have to deal with it yourself.

### Code

If you're new to Git, follow these steps to open your first Pull Request (PR):

- Fork this repository
- Clone the new repository
- Commit your changes
- Open a pull request to the `dev` branch

Please document any functions or obscure lines of code.

### The Wiki

To help out `streamrip` users that may be having trouble, consider contributing some information to the wiki.
Nothing is too obvious and everything is appreciated.

## Acknowledgements

Thanks to Vitiko98, Sorrow446, and DashLt for their contributions to this project, and the previous projects that made this one possible.

`streamrip` was inspired by:

- [qobuz-dl](https://github.com/vitiko98/qobuz-dl)
- [Qo-DL Reborn](https://github.com/badumbass/Qo-DL-Reborn)
- [Tidal-Media-Downloader](https://github.com/yaronzz/Tidal-Media-Downloader)
- [scdl](https://github.com/flyingrub/scdl)

## Disclaimer

I will not be responsible for how **you** use `streamrip`. By using `streamrip`, you agree to the terms and conditions of the Qobuz, Tidal, and Deezer APIs.

## Sponsorship

Consider becoming a Github sponsor for me if you enjoy my open source software.
