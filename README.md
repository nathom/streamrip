# streamrip

A scriptable stream downloader for Qobuz, Tidal, and Deezer.

## Features

- Downloads tracks, albums, playlists, discographies, and labels from Qobuz, Tidal, and Deezer

- Automatically converts files to a preferred format
- Has a database that stores the downloaded tracks' IDs so that repeats are avoided
- Easy to customize with the config file

## Installation

First, ensure [pip](https://pip.pypa.io/en/stable/installing/) is installed. Then run the following in the command line:

```bash
pip3 install streamrip --upgrade
```

If you would like to use `streamrip`'s conversion capabilities, install [ffmpeg](https://ffmpeg.org/download.html).

## Example Usage

**For Tidal and Qobuz, you NEED a premium subscription.**

Download an album from Qobuz

```bash
rip -u https://open.qobuz.com/album/0060253780968
```

Download the album and convert it to `mp3`

```bash
rip --convert mp3 -u https://open.qobuz.com/album/0060253780968
```



To set the quality, use the `--quality` option to `0, 1, 2, 3, 4`:

| Quality ID | Audio Quality         | Available Sources    |
| ---------- | --------------------- | -------------------- |
| 0          | 128 kbps MP3 or AAC   | Deezer, Tidal        |
| 1          | 320 kbps MP3 or AAC   | Deezer, Tidal, Qobuz |
| 2          | 16 bit, 44.1 kHz (CD) | Deezer, Tidal, Qobuz |
| 3          | 24 bit, ≤ 96 kHz      | Tidal (MQA), Qobuz   |
| 4          | 24 bit, ≤ 192 kHz     | Qobuz                |





```bash
rip --quality 3 https://tidal.com/browse/album/147569387
```

Search for *Fleetwood Mac - Rumours* on Qobuz

```bash
rip search 'fleetwood mac rumours'
```

![streamrip interactive search](https://github.com/nathom/streamrip/blob/main/demo/interactive_search.png?raw=true)

Search for *Rumours* on Tidal, download it, convert it to `ALAC`

```bash
rip -c alac search 'fleetwood mac rumours'
```

Qobuz discographies can be filtered using the `filter` subcommand

```bash
rip filter --repeats --features 'https://open.qobuz.com/artist/22195'
```



Want to find some new music? Use the `discover` command (only on Qobuz)

```bash
rip discover --list 'best-sellers'
```

> Avaiable options for `--list`:
>
> - most-streamed
> - recent-releases
> - best-sellers
> - press-awards
> - ideal-discography
> - editor-picks
> - most-featured
> - qobuzissims
> - new-releases
> - new-releases-full
> - harmonia-mundi
> - universal-classic
> - universal-jazz
> - universal-jeunesse
> - universal-chanson



For more help and examples

```bash
rip --help
```

```bash
rip filter --help
```

```bash
rip search --help
```

```bash
rip discover --help
```

```bash
rip config --help
```

**This tool is still in development. If there are any features you would like to see, please open an issue.**



## Acknowledgements

Thanks to Vitiko98, Sorrow446, and DashLt for their contributions to this project, and the previous projects that made this one possible.



`streamrip` was inspired by:

- [qobuz-dl](https://github.com/vitiko98/qobuz-dl)
- [Qo-DL Reborn](https://github.com/badumbass/Qo-DL-Reborn)
- [Tidal-Media-Downloader](https://github.com/yaronzz/Tidal-Media-Downloader)



## Disclaimer


I will not be responsible for how you use `streamrip`. By using `streamrip`, you agree to the terms and conditions of the Qobuz, Tidal, and Deezer APIs.