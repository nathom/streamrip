import argparse


def fun_args(subparsers, default_limit):
    interactive = subparsers.add_parser(
        "fun",
        description="Interactively search for tracks and albums.",
        help="interactive mode",
    )
    interactive.add_argument(
        "-l",
        "--limit",
        metavar="int",
        default=default_limit,
        help="limit of search results (default: 20)",
    )
    return interactive


def lucky_args(subparsers):
    lucky = subparsers.add_parser(
        "lucky",
        description="Download the first <n> albums returned from a Qobuz search.",
        help="lucky mode",
    )
    lucky.add_argument(
        "-t",
        "--type",
        default="album",
        help="type of items to search (artist, album, track, playlist) (default: album)",
    )
    lucky.add_argument(
        "-n",
        "--number",
        metavar="int",
        default=1,
        help="number of results to download (default: 1)",
    )
    lucky.add_argument("QUERY", nargs="+", help="search query")
    return lucky


def dl_args(subparsers):
    download = subparsers.add_parser(
        "dl",
        description="Download by album/track/artist/label/playlist/last.fm-playlist URL.",
        help="input mode",
    )
    download.add_argument(
        "SOURCE",
        metavar="SOURCE",
        nargs="+",
        help=("one or more URLs (space separated) or a text file"),
    )
    return download


def add_common_arg(custom_parser, default_folder, default_quality):
    custom_parser.add_argument(
        "-d",
        "--directory",
        metavar="PATH",
        default=default_folder,
        help=f'directory for downloads (default: "{default_folder}")',
    )
    custom_parser.add_argument(
        "-q",
        "--quality",
        metavar="int",
        default=default_quality,
        help=(
            'audio "quality" (5, 6, 7, 27)\n'
            f"[320, LOSSLESS, 24B<=96KHZ, 24B>96KHZ] (default: {default_quality})"
        ),
    )
    custom_parser.add_argument(
        "--albums-only",
        action="store_true",
        help=("don't download singles, EPs and VA releases"),
    )
    custom_parser.add_argument(
        "--no-m3u",
        action="store_true",
        help="don't create .m3u files when downloading playlists",
    )
    custom_parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="disable quality fallback (skip releases not available in set quality)",
    )
    custom_parser.add_argument(
        "-e", "--embed-art", action="store_true", help="embed cover art into files"
    )
    custom_parser.add_argument(
        "--og-cover",
        action="store_true",
        help="download cover art in its original quality (bigger file)",
    )
    custom_parser.add_argument(
        "--no-cover", action="store_true", help="don't download cover art"
    )
    custom_parser.add_argument(
        "--no-db", action="store_true", help="don't call the database"
    )
    custom_parser.add_argument(
        "-ff",
        "--folder-format",
        metavar="PATTERN",
        help="""pattern for formatting folder names, e.g
        "{artist} - {album} ({year})". available keys: artist,
        albumartist, album, year, sampling_rate, bit_rate, tracktitle, version.
        cannot contain characters used by the system, which includes /:<>""",
    )
    custom_parser.add_argument(
        "-tf",
        "--track-format",
        metavar="PATTERN",
        help="pattern for formatting track names. see `folder-format`.",
    )
    # TODO: add customization options
    custom_parser.add_argument(
        "-s",
        "--smart-discography",
        action="store_true",
        help="""Try to filter out spam-like albums when requesting an artist's
        discography, and other optimizations. Filters albums not made by requested
        artist, and deluxe/live/collection albums. Gives preference to remastered
        albums, high bit depth/dynamic range, and low sampling rates (to save space).""",
    )


def qobuz_dl_args(
    default_quality=6, default_limit=20, default_folder="Qobuz Downloads"
):
    parser = argparse.ArgumentParser(
        prog="qobuz-dl",
        description=(
            "The ultimate Qobuz music downloader.\nSee usage"
            " examples on https://github.com/vitiko98/qobuz-dl"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-r", "--reset", action="store_true", help="create/reset config file"
    )
    parser.add_argument(
        "-p",
        "--purge",
        action="store_true",
        help="purge/delete downloaded-IDs database",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        description="run qobuz-dl <command> --help for more info\n(e.g. qobuz-dl fun --help)",
        dest="command",
    )

    interactive = fun_args(subparsers, default_limit)
    download = dl_args(subparsers)
    lucky = lucky_args(subparsers)
    [
        add_common_arg(i, default_folder, default_quality)
        for i in (interactive, download, lucky)
    ]

    return parser
