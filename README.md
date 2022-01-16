# streamrip

[![Downloads](https://pepy.tech/badge/streamrip)](https://pepy.tech/project/streamrip)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/python/black)

A scriptable stream downloader for Qobuz, Tidal, Deezer and SoundCloud.

![Streamrip downloading an album](https://github.com/nathom/streamrip/blob/dev/demo/download_album.png?raw=true)


## Features

- Super fast, as it utilizes concurrent downloads and conversion
- Downloads tracks, albums, playlists, discographies, and labels from Qobuz, Tidal, Deezer, and SoundCloud
- Supports downloads of Spotify and Apple Music playlists through [last.fm](https://www.last.fm)
- Automatically converts files to a preferred format
- Has a database that stores the downloaded tracks' IDs so that repeats are avoided
- Easy to customize with the config file
- Integration with `youtube-dl`

## Installation

First, ensure [Python](https://www.python.org/downloads/) (version 3.8 or greater) and [pip](https://pip.pypa.io/en/stable/installing/) are installed. If you are on Windows, install [Microsoft Visual C++ Tools](https://docs.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170). Then run the following in the command line:

```bash
pip3 install streamrip --upgrade
```

When you type

```bash
rip
```

it should show the main help page. If you have no idea what these mean, or are having other issues installing, check out the [detailed installation instructions](https://github.com/nathom/streamrip/wiki#detailed-installation-instructions).

If you would like to use `streamrip`'s conversion capabilities, download TIDAL videos, or download music from SoundCloud, install [ffmpeg](https://ffmpeg.org/download.html). To download music from YouTube, install [youtube-dl](https://github.com/ytdl-org/youtube-dl#installation).

### Streamrip beta

If you want to get access to the latest and greatest features without waiting for a new release, install
from the `dev` branch with the following command

```bash
pip3 install git+https://github.com/nathom/streamrip.git@dev
```

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
rip url --codec mp3 https://open.qobuz.com/album/0060253780968
```



To set the maximum quality, use the `--max-quality` option to `0, 1, 2, 3, 4`:

| Quality ID | Audio Quality         | Available Sources                            |
| ---------- | --------------------- | -------------------------------------------- |
| 0          | 128 kbps MP3 or AAC   | Deezer, Tidal, SoundCloud (most of the time) |
| 1          | 320 kbps MP3 or AAC   | Deezer, Tidal, Qobuz, SoundCloud (rarely)    |
| 2          | 16 bit, 44.1 kHz (CD) | Deezer, Tidal, Qobuz, SoundCloud (rarely)    |
| 3          | 24 bit, ≤ 96 kHz      | Tidal (MQA), Qobuz, SoundCloud (rarely)      |
| 4          | 24 bit, ≤ 192 kHz     | Qobuz                                        |



```bash
rip url --max-quality 3 https://tidal.com/browse/album/147569387
```

Search for albums matching `lil uzi vert` on SoundCloud

```bash
rip search --source soundcloud 'lil uzi vert'
```

![streamrip interactive search](https://github.com/nathom/streamrip/blob/dev/demo/album_search.png?raw=true)

Search for *Rumours* on Tidal, and download it

```bash
rip search 'fleetwood mac rumours'
```

Want to find some new music? Use the `discover` command (only on Qobuz)

```bash
rip discover --list 'best-sellers'
```

Download a last.fm playlist using the lastfm command

```
rip lastfm https://www.last.fm/user/nathan3895/playlists/12126195
```

For extreme customization, see the config file

```
rip config --open
```



If you're confused about anything, see the help pages. The main help pages can be accessed by typing `rip` by itself in the command line. The help pages for each command can be accessed with the `-h` flag. For example, to see the help page for the `url` command, type

```
rip url -h
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


I will not be responsible for how you use `streamrip`. By using `streamrip`, you agree to the terms and conditions of the Qobuz, Tidal, and Deezer APIs.

## Donations/Sponsorship

<a href="https://www.buymeacoffee.com/nathom" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>


Consider contributing some funds [here](https://www.buymeacoffee.com/nathom), which will go towards holding
the premium subscriptions that I need to debug and improve streamrip. Thanks for your support!
