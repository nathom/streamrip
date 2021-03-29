# streamrip

A scriptable stream downloader for Qobuz, Tidal, and Deezer.



## Installation

```bash
pip3 install streamrip --upgrade
```



## Basic Usage

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

| Quality ID | Audio Quality       | Available Sources    |
| ---------- | ------------------- | -------------------- |
| 0          | 128 kbps MP3 or AAC | Deezer, Tidal        |
| 1          | 320 kbps MP3 or AAC | Deezer, Tidal, Qobuz |
| 2          | 16 bit / 44.1 kHz   | Deezer, Tidal, Qobuz |
| 3          | 24 bit / ≤ 96 kHz   | Tidal (MQA), Qobuz   |
| 4          | 24 bit / ≤ 192 kHz  | Qobuz                |

```bash
rip --quality 3 https://tidal.com/browse/album/147569387
```

Search for *Fleetwood Mac - Rumours* on Qobuz

```bash
rip search 'fleetwood mac rumours'
```

![streamrip interactive search](demo/interactive_search.png)

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

