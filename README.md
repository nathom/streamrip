# streamrip

A scriptable stream downloader for Qobuz, Tidal, Deezer and SoundCloud.

## Attention

The Deezloader server is currently down. This means Deezer downloads are currently not working.
Stay posted for updates.

## Features

- Super fast, as it utilizes concurrent downloads and conversion
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

## The Config File

This is where most of streamrip's functionality can be controlled. Here are
the descriptions of the fields. They can also be found inside the file, which
can be accessed with `rip config --open`.

```yaml
qobuz:
        quality: '1: 320kbps MP3, 2: 16/44.1, 3: 24/<=96, 4: 24/>=96'
        app_id: 'Do not change'
        secrets: 'Do not change'
    tidal:
        quality: '0, 1, 2, or 3'
        user_id: 'Do not change any of the fields below'
        token_expiry: 'Tokens last 1 week after refresh. This is the Unix timestamp of the expiration time.'
    deezer: "Deezer doesn't require login"
        quality: '0, 1, or 2'
    soundcloud:
        quality: 'Only 0 is available'
    database: 'This stores a list of item IDs so that repeats are not downloaded.'
    filters: "Filter a Qobuz artist's discography. Set to 'true' to turn on a filter."
        extras: 'Remove Collectors Editions, live recordings, etc.'
        repeats: 'Picks the highest quality out of albums with identical titles.'
        non_albums: 'Remove EPs and Singles'
        features: 'Remove albums whose artist is not the one requested'
        non_remaster: 'Only download remastered albums'
    downloads:
        folder: 'Folder where tracks are downloaded to'
        source_subdirectories: "Put Qobuz albums in a 'Qobuz' folder, Tidal albums in 'Tidal' etc."
    artwork:
        embed: 'Write the image to the audio file'
        size: "The size of the artwork to embed. Options: thumbnail, small, large, original. 'original' images can be up to 30MB, and may fail embedding. Using 'large' is recommended."
        keep_hires_cover: 'Save the cover image at the highest quality as a seperate jpg file'
    metadata: 'Only applicable for playlist downloads.'
        set_playlist_to_album: "Sets the value of the 'ALBUM' field in the metadata to the playlist's name. This is useful if your music library software organizes tracks based on album name."
        new_playlist_tracknumbers: "Replaces the original track's tracknumber with it's position in the playlist"
    path_format: 'Changes the folder and file names generated by streamrip.'
        folder: 'Available keys: "albumartist", "title", "year", "bit_depth", "sampling_rate", and "container"'
        track: 'Available keys: "tracknumber", "artist", "albumartist", "composer", and "title"'
    lastfm: 'Last.fm playlists are downloaded by searching for the titles of the tracks'
        source: 'The source on which to search for the tracks.'
    concurrent_downloads: 'Download (and convert) tracks all at once, instead of sequentially. If you are converting the tracks, and/or have fast internet, this will substantially improve processing speed.'
```



## Troubleshooting

If you're having issues with the tool, try the following:

- Consult the help pages and their example commands.
    ```bash
    rip --help
rip filter --help
    rip search --help
rip discover --help
    rip config --help
rip lastfm --help
    ```
- Update `streamrip` with by running `pip3 install streamrip --upgrade`
- Reset the config file with `rip config --reset`

If none of the above work, open an [issue](#guidelines-for-opening-issues).


## Contributions

All contributions are appreciated! You can help out the project by opening an issue
or by submitting code.

### Guidelines for opening issues

- Include a general description of the feature request or bug in the title
- Limit each Issue to a single subject
- For bug reports, include the traceback, command (including the url) you used,
and version of `streamrip`

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
