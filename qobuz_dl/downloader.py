import logging
import os
from typing import Tuple

import requests
from pathvalidate import sanitize_filename
from tqdm import tqdm

import qobuz_dl.metadata as metadata
from qobuz_dl.color import CYAN, GREEN, OFF, RED, YELLOW
from qobuz_dl.exceptions import NonStreamable

QL_DOWNGRADE = "FormatRestrictedByFormatAvailability"
# used in case of error
DEFAULT_FORMATS = {
    "MP3": [
        "{artist} - {album} ({year}) [MP3]",
        "{tracknumber}. {tracktitle}",
    ],
    "Unknown": [
        "{artist} - {album}",
        "{tracknumber}. {tracktitle}",
    ],
}

logger = logging.getLogger(__name__)


def tqdm_download(url, fname, track_name):
    r = requests.get(url, allow_redirects=True, stream=True)
    total = int(r.headers.get("content-length", 0))
    with open(fname, "wb") as file, tqdm(
        total=total,
        unit="iB",
        unit_scale=True,
        unit_divisor=1024,
        desc=track_name,
        bar_format=CYAN + "{n_fmt}/{total_fmt} /// {desc}",
    ) as bar:
        for data in r.iter_content(chunk_size=1024):
            size = file.write(data)
            bar.update(size)


def get_description(u: dict, track_title, multiple=None):
    downloading_title = f"{track_title} "
    f'[{u["bit_depth"]}/{u["sampling_rate"]}]'
    if multiple:
        downloading_title = f"[Disc {multiple}] {downloading_title}"
    return downloading_title


def get_format(
    client, item_dict, quality, is_track_id=False, track_url_dict=None
) -> Tuple[str, bool, int, int]:
    quality_met = True
    if int(quality) == 5:
        return ("MP3", quality_met, None, None)
    track_dict = item_dict
    if not is_track_id:
        track_dict = item_dict["tracks"]["items"][0]

    try:
        new_track_dict = (
            client.get_track_url(track_dict["id"], quality)
            if not track_url_dict
            else track_url_dict
        )
        restrictions = new_track_dict.get("restrictions")
        if isinstance(restrictions, list):
            if any(
                restriction.get("code") == QL_DOWNGRADE for restriction in restrictions
            ):
                quality_met = False

        return (
            "FLAC",
            quality_met,
            new_track_dict["bit_depth"],
            new_track_dict["sampling_rate"],
        )
    except (KeyError, requests.exceptions.HTTPError):
        return ("Unknown", quality_met, None, None)


def get_title(item_dict):
    album_title = item_dict["title"]
    version = item_dict.get("version")
    if version:
        album_title = (
            f"{album_title} ({version})"
            if version.lower() not in album_title.lower()
            else album_title
        )
    return album_title


def get_extra(i, dirn, extra="cover.jpg", og_quality=False):
    extra_file = os.path.join(dirn, extra)
    if os.path.isfile(extra_file):
        logger.info(f"{OFF}{extra} was already downloaded")
        return
    tqdm_download(
        i.replace("_600.", "_org.") if og_quality else i,
        extra_file,
        extra,
    )


# Download and tag a file
def download_and_tag(
    root_dir,
    tmp_count,
    track_url_dict,
    track_metadata,
    album_or_track_metadata,
    is_track,
    is_mp3,
    embed_art=False,
    multiple=None,
    track_format="{tracknumber}. {tracktitle}",
):
    """
    Download and tag a file

    :param str root_dir: Root directory where the track will be stored
    :param int tmp_count: Temporal download file number
    :param dict track_url_dict: get_track_url dictionary from Qobuz client
    :param dict track_metadata: Track item dictionary from Qobuz client
    :param dict album_or_track_metadata: Album/track dict from Qobuz client
    :param bool is_track
    :param bool is_mp3
    :param bool embed_art: Embed cover art into file (FLAC-only)
    :param str track_format format-string that determines file naming
    :param multiple: Multiple disc integer
    :type multiple: integer or None
    """

    extension = ".mp3" if is_mp3 else ".flac"

    try:
        url = track_url_dict["url"]
    except KeyError:
        logger.info(f"{OFF}Track not available for download")
        return

    if multiple:
        root_dir = os.path.join(root_dir, f"Disc {multiple}")
        os.makedirs(root_dir, exist_ok=True)

    filename = os.path.join(root_dir, f".{tmp_count:02}.tmp")

    # Determine the filename
    track_title = track_metadata.get("title")
    artist = _safe_get(track_metadata, "performer", "name")
    filename_attr = {
        "artist": artist,
        "albumartist": _safe_get(
            track_metadata, "album", "artist", "name", default=artist
        ),
        "bit_depth": track_metadata["maximum_bit_depth"],
        "sampling_rate": track_metadata["maximum_sampling_rate"],
        "tracktitle": track_title,
        "version": track_metadata.get("version"),
        "tracknumber": f"{track_metadata['track_number']:02}",
    }
    # track_format is a format string
    # e.g. '{tracknumber}. {artist} - {tracktitle}'
    formatted_path = sanitize_filename(track_format.format(**filename_attr))
    final_file = os.path.join(root_dir, formatted_path)[:250] + extension

    if os.path.isfile(final_file):
        logger.info(f"{OFF}{track_title} was already downloaded")
        return

    desc = get_description(track_url_dict, track_title, multiple)
    tqdm_download(url, filename, desc)
    tag_function = metadata.tag_mp3 if is_mp3 else metadata.tag_flac
    try:
        tag_function(
            filename,
            root_dir,
            final_file,
            track_metadata,
            album_or_track_metadata,
            is_track,
            embed_art,
        )
    except Exception as e:
        logger.error(f"{RED}Error tagging the file: {e}", exc_info=True)


def download_id_by_type(
    client,
    item_id,
    path,
    quality,
    album=False,
    embed_art=False,
    albums_only=False,
    downgrade_quality=True,
    cover_og_quality=False,
    no_cover=False,
    folder_format="{artist} - {album} ({year}) " "[{bit_depth}B-{sampling_rate}kHz]",
    track_format="{tracknumber}. {tracktitle}",
):
    """
    Download and get metadata by ID and type (album or track)

    :param Qopy client: qopy Client
    :param int item_id: Qobuz item id
    :param str path: The root directory where the item will be downloaded
    :param int quality: Audio quality (5, 6, 7, 27)
    :param bool album: album type or not
    :param embed_art album: Embed cover art into files
    :param bool albums_only: Ignore Singles, EPs and VA releases
    :param bool downgrade: Skip releases not available in set quality
    :param bool cover_og_quality: Download cover in its original quality
    :param bool no_cover: Don't download cover art
    :param str folder_format: format string that determines folder naming
    :param str track_format: format string that determines track naming
    """
    count = 0

    if album:
        meta = client.get_album_meta(item_id)

        if not meta.get("streamable"):
            raise NonStreamable("This release is not streamable")

        if albums_only and (
            meta.get("release_type") != "album"
            or meta.get("artist").get("name") == "Various Artists"
        ):
            logger.info(f'{OFF}Ignoring Single/EP/VA: {meta.get("title", "")}')
            return

        album_title = get_title(meta)

        format_info = get_format(client, meta, quality)
        file_format, quality_met, bit_depth, sampling_rate = format_info

        if not downgrade_quality and not quality_met:
            logger.info(
                f"{OFF}Skipping {album_title} as it doesn't " "meet quality requirement"
            )
            return

        logger.info(
            f"\n{YELLOW}Downloading: {album_title}\nQuality: {file_format} ({bit_depth}/{sampling_rate})\n"
        )
        album_attr = {
            "artist": meta["artist"]["name"],
            "album": album_title,
            "year": meta["release_date_original"].split("-")[0],
            "format": file_format,
            "bit_depth": bit_depth,
            "sampling_rate": sampling_rate,
        }
        folder_format, track_format = _clean_format_str(
            folder_format, track_format, file_format
        )
        sanitized_title = sanitize_filename(folder_format.format(**album_attr))
        dirn = os.path.join(path, sanitized_title)
        os.makedirs(dirn, exist_ok=True)

        if no_cover:
            logger.info(f"{OFF}Skipping cover")
        else:
            get_extra(meta["image"]["large"], dirn, og_quality=cover_og_quality)

        if "goodies" in meta:
            try:
                get_extra(meta["goodies"][0]["url"], dirn, "booklet.pdf")
            except:  # noqa
                pass
        media_numbers = [track["media_number"] for track in meta["tracks"]["items"]]
        is_multiple = True if len([*{*media_numbers}]) > 1 else False
        for i in meta["tracks"]["items"]:
            parse = client.get_track_url(i["id"], quality)
            if "sample" not in parse and parse["sampling_rate"]:
                is_mp3 = True if int(quality) == 5 else False
                download_and_tag(
                    dirn,
                    count,
                    parse,
                    i,
                    meta,
                    False,
                    is_mp3,
                    embed_art,
                    i["media_number"] if is_multiple else None,
                    track_format=track_format,
                )
            else:
                logger.info(f"{OFF}Demo. Skipping")
            count = count + 1
    else:
        parse = client.get_track_url(item_id, quality)

        if "sample" not in parse and parse["sampling_rate"]:
            meta = client.get_track_meta(item_id)
            track_title = get_title(meta)
            logger.info(f"\n{YELLOW}Downloading: {track_title}")
            format_info = get_format(
                client, meta, quality, is_track_id=True, track_url_dict=parse
            )
            file_format, quality_met, bit_depth, sampling_rate = format_info

            folder_format, track_format = _clean_format_str(
                folder_format, track_format, bit_depth
            )

            if not downgrade_quality and not quality_met:
                logger.info(
                    f"{OFF}Skipping {track_title} as it doesn't "
                    "meet quality requirement"
                )
                return
            track_attr = {
                "artist": meta["album"]["artist"]["name"],
                "tracktitle": track_title,
                "year": meta["album"]["release_date_original"].split("-")[0],
                "bit_depth": bit_depth,
                "sampling_rate": sampling_rate,
            }
            sanitized_title = sanitize_filename(folder_format.format(**track_attr))

            dirn = os.path.join(path, sanitized_title)
            os.makedirs(dirn, exist_ok=True)
            if no_cover:
                logger.info(f"{OFF}Skipping cover")
            else:
                get_extra(
                    meta["album"]["image"]["large"], dirn, og_quality=cover_og_quality
                )
            is_mp3 = True if int(quality) == 5 else False
            download_and_tag(
                dirn,
                count,
                parse,
                meta,
                meta,
                True,
                is_mp3,
                embed_art,
                track_format=track_format,
            )
        else:
            logger.info(f"{OFF}Demo. Skipping")
    logger.info(f"{GREEN}Completed")


# ----------- Utilities -----------


def _clean_format_str(folder: str, track: str, file_format: str) -> Tuple[str, str]:
    """Cleans up the format strings, avoids errors
    with MP3 files.
    """
    final = []
    for i, fs in enumerate((folder, track)):
        if fs.endswith(".mp3"):
            fs = fs[:-4]
        elif fs.endswith(".flac"):
            fs = fs[:-5]
        fs = fs.strip()

        # default to pre-chosen string if format is invalid
        if file_format in ("MP3", "Unknown") and (
            "bit_depth" in fs or "sampling_rate" in fs
        ):
            default = DEFAULT_FORMATS[file_format][i]
            logger.error(
                f"{RED}invalid format string for format {file_format}"
                f". defaulting to {default}"
            )
            fs = default
        final.append(fs)

    return tuple(final)


def _safe_get(d: dict, *keys, default=None):
    """A replacement for chained `get()` statements on dicts:
    >>> d = {'foo': {'bar': 'baz'}}
    >>> _safe_get(d, 'baz')
    None
    >>> _safe_get(d, 'foo', 'bar')
    'baz'
    """
    curr = d
    res = default
    for key in keys:
        res = curr.get(key, default)
        if res == default or not hasattr(res, "__getitem__"):
            return res
        else:
            curr = res
    return res
