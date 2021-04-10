# streamrip

A scriptable stream downloader for Qobuz, Tidal, Deezer and SoundCloud.

## Features

- Downloads tracks, albums, playlists, discographies, and labels from Qobuz, Tidal, Deezer, and SoundCloud

- Automatically converts files to a preferred format
- Has a database that stores the downloaded tracks' IDs so that repeats are avoided
- Easy to customize with the config file

## Installation

First, ensure [pip](https://pip.pypa.io/en/stable/installing/) is installed. Then run the following in the command line:



macOS/Linux:

```bash
pip3 install streamrip simple-term-menu --upgrade
```

Windows:

```bash
pip3 install streamrip windows-curses --upgrade
```



If you would like to use `streamrip`'s conversion capabilities, or download music from SoundCloud, install [ffmpeg](https://ffmpeg.org/download.html).

## Example Usage

**For Tidal and Qobuz, you NEED a premium subscription.**

Download an album from Qobuz

```bash
rip -u https://open.qobuz.com/album/0060253780968
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



## Troubleshooting

First, consult the help pages and their example commands.

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

```bash
rip lastfm --help
```

Second, try resetting the config file with `rip config —reset`. Config errors often arise after an update where a new feature was added.



If that doesn't work, open an issue on GitHub. Please include the traceback and the command you used. 



## Contributions

All contributions are appreciated! If you're new to Git, follow these steps to open your first Pull Request (PR):

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