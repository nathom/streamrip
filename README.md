# streamrip

[![Downloads](https://static.pepy.tech/personalized-badge/streamrip?period=total&units=international_system&left_color=black&right_color=green&left_text=Downloads)](https://pepy.tech/project/streamrip)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/python/black)


A scriptable stream downloader for Qobuz, Tidal, Deezer and SoundCloud.


## Features

- Super fast, as it utilizes concurrent downloads and conversion
- Downloads tracks, albums, playlists, discographies, and labels from Qobuz, Tidal, Deezer, and SoundCloud
- Supports downloads of Spotify and Apple Music playlists through [last.fm](https://www.last.fm)
- Automatically converts files to a preferred format
- Has a database that stores the downloaded tracks' IDs so that repeats are avoided
- Easy to customize with the config file
- Integration with `youtube-dl`

## Installation

First, ensure [Python](https://www.python.org/downloads/) (version 3.8 or greater) and [pip](https://pip.pypa.io/en/stable/installing/) are installed. Then run the following in the command line:

```bash
pip3 install streamrip --upgrade
```

If you would like to use `streamrip`'s conversion capabilities, download TIDAL videos, or download music from SoundCloud, install [ffmpeg](https://ffmpeg.org/download.html). To download music from YouTube, install [youtube-dl](https://github.com/ytdl-org/youtube-dl#installation).


## Example Usage

**For Tidal and Qobuz, you NEED a premium subscription.**

Download an album from Qobuz

```bash
rip -u https://open.qobuz.com/album/0060253780968
```

Download multiple albums from Qobuz
```bash
rip -u https://www.qobuz.com/us-en/album/back-in-black-ac-dc/0886444889841 -u https://www.qobuz.com/us-en/album/blue-train-john-coltrane/0060253764852
```

![Streamrip downloading an album](https://github.com/nathom/streamrip/blob/main/demo/download_url.png?raw=true)

Download the album and convert it to `mp3`

```bash
rip --convert mp3 -u https://open.qobuz.com/album/0060253780968
```



To set the quality, use the `--quality` option to `0, 1, 2, 3, 4`:

| Quality ID | Audio Quality         | Available Sources                            |
| ---------- | --------------------- | -------------------------------------------- |
| 0          | 128 kbps MP3 or AAC   | Deezer, Tidal, SoundCloud (most of the time) |
| 1          | 320 kbps MP3 or AAC   | Deezer, Tidal, Qobuz, SoundCloud (rarely)    |
| 2          | 16 bit, 44.1 kHz (CD) | Deezer, Tidal, Qobuz, SoundCloud (rarely)    |
| 3          | 24 bit, ≤ 96 kHz      | Tidal (MQA), Qobuz, SoundCloud (rarely)      |
| 4          | 24 bit, ≤ 192 kHz     | Qobuz                                        |





```bash
rip --quality 3 https://tidal.com/browse/album/147569387
```

Search for albums matching `lil uzi vert` on SoundCloud

```bash
rip search -s soundcloud 'lil uzi vert'
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

## Other information

For more in-depth information about `streamrip`, see the [wiki](https://github.com/nathom/streamrip/wiki/).


## Contributions

All contributions are appreciated! You can help out the project by opening an issue
or by submitting code.

### Guidelines for opening issues

- Include a general description of the feature request or bug in the title
- Limit each Issue to a single subject
- For bug reports, include the traceback, command (including the url) you used,
and version of `streamrip`
- If you do not follow the template provided, I will not respond

### Contributing code

If you're new to Git, follow these steps to open your first Pull Request (PR):

- Fork this repository
- Clone the new repository
- Commit your changes
- Open a pull request to the `dev` branch

Please document any functions or obscure lines of code.


## Acknowledgements

Thanks to Vitiko98, Sorrow446, and DashLt for their contributions to this project, and the previous projects that made this one possible.

`streamrip` was inspired by:

- [qobuz-dl](https://github.com/vitiko98/qobuz-dl)
- [Qo-DL Reborn](https://github.com/badumbass/Qo-DL-Reborn)
- [Tidal-Media-Downloader](https://github.com/yaronzz/Tidal-Media-Downloader)
- [scdl](https://github.com/flyingrub/scdl)



## Disclaimer


I will not be responsible for how you use `streamrip`. By using `streamrip`, you agree to the terms and conditions of the Qobuz, Tidal, and Deezer APIs.
