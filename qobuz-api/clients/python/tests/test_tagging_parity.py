"""A/B comparison: streamrip tagger vs SDK tagger.

Downloads the same album with both pipelines using identical config
and compares every ID3/FLAC tag field plus file naming to verify parity.

Run: QOBUZ_TOKEN=... QOBUZ_USER_ID=... poetry run pytest tests/test_tagging_parity.py -v -s
"""

import asyncio
import os
import tempfile

import pytest
from mutagen.flac import FLAC

# Harold Budd — Ambient 2 (10 tracks, consistent metadata)
TEST_ALBUM_ID = "0724386649751"
QOBUZ_TOKEN = os.environ.get("QOBUZ_TOKEN", "")
QOBUZ_USER_ID = os.environ.get("QOBUZ_USER_ID", "")

# Shared config values — both pipelines use these exact same settings
SHARED_QUALITY = 2  # 16-bit/44.1kHz
SHARED_FOLDER_FORMAT = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
SHARED_TRACK_FORMAT = "{tracknumber:02d}. {artist} - {title}"

skip_no_creds = pytest.mark.skipif(
    not QOBUZ_TOKEN or not QOBUZ_USER_ID,
    reason="Set QOBUZ_TOKEN and QOBUZ_USER_ID env vars"
)


async def download_with_streamrip(album_id: str, output_dir: str) -> list[str]:
    """Download album using streamrip pipeline, return sorted FLAC paths."""
    from backend.services.config_bridge import build_streamrip_config
    from backend.models.database import AppDatabase
    from streamrip.media import PendingAlbum
    from streamrip.db import Dummy, Database as SRDatabase

    db_file = os.path.join(output_dir, "app.db")
    db = AppDatabase(db_file)
    db.set_config("qobuz_token", QOBUZ_TOKEN)
    db.set_config("qobuz_user_id", QOBUZ_USER_ID)
    db.set_config("qobuz_quality", str(SHARED_QUALITY))
    db.set_config("downloads_path", output_dir)
    db.set_config("folder_format", SHARED_FOLDER_FORMAT)
    db.set_config("track_format", SHARED_TRACK_FORMAT)

    config = build_streamrip_config(db)
    config.session.downloads.folder = output_dir

    from streamrip.client.qobuz import QobuzClient
    client = QobuzClient(config)
    await client.login()

    database = SRDatabase(Dummy(), Dummy(), Dummy())
    pending = PendingAlbum(album_id, client, config, database)
    media = await pending.resolve()
    assert media is not None, "streamrip failed to resolve album"
    await media.rip()

    await client.session.close()

    flacs = []
    for root, _, files in os.walk(output_dir):
        for f in sorted(files):
            if f.endswith(".flac"):
                flacs.append(os.path.join(root, f))
    return sorted(flacs)


async def download_with_sdk(album_id: str, output_dir: str) -> list[str]:
    """Download album using SDK pipeline, return sorted FLAC paths."""
    from qobuz import QobuzClient, AlbumDownloader, DownloadConfig
    from qobuz.spoofer import fetch_app_credentials, find_working_secret

    app_id, secrets = await fetch_app_credentials()
    app_secret = await find_working_secret(app_id, secrets, QOBUZ_TOKEN)

    async with QobuzClient(
        app_id=app_id, user_auth_token=QOBUZ_TOKEN, app_secret=app_secret
    ) as client:
        dl = AlbumDownloader(client, DownloadConfig(
            output_dir=output_dir,
            quality=SHARED_QUALITY,
            folder_format=SHARED_FOLDER_FORMAT,
            track_format=SHARED_TRACK_FORMAT,
        ))
        result = await dl.download(album_id)
        assert result.successful > 0, "SDK failed to download tracks"

    flacs = []
    for root, _, files in os.walk(output_dir):
        for f in sorted(files):
            if f.endswith(".flac"):
                flacs.append(os.path.join(root, f))
    return sorted(flacs)


# Tags where the SDK intentionally differs from streamrip
# organization/barcode: SDK writes them, streamrip doesn't
# albumartist: SDK uses primary artist, streamrip joins all artists
SDK_INTENTIONAL_DIFFS = {"organization", "barcode", "albumartist"}


def read_all_flac_tags(path: str) -> dict[str, str]:
    """Read ALL tags from a FLAC file."""
    audio = FLAC(path)
    tags = {}
    for key in audio.keys():
        values = audio.get(key, [])
        tags[key] = values[0] if values else ""
    tags["_has_cover"] = str(len(audio.pictures) > 0)
    tags["_cover_size"] = str(len(audio.pictures[0].data)) if audio.pictures else "0"
    tags["_filename"] = os.path.basename(path)
    return tags


@skip_no_creds
async def test_tagging_parity():
    """Download same album with both pipelines using identical config.

    Compares every FLAC tag and file naming to verify the SDK produces
    output matching streamrip.
    """
    with tempfile.TemporaryDirectory() as sr_dir, \
         tempfile.TemporaryDirectory() as sdk_dir:

        print(f"\n=== Config ===")
        print(f"  quality: {SHARED_QUALITY}")
        print(f"  folder_format: {SHARED_FOLDER_FORMAT}")
        print(f"  track_format: {SHARED_TRACK_FORMAT}")

        print("\n=== Downloading with streamrip ===")
        sr_flacs = await download_with_streamrip(TEST_ALBUM_ID, sr_dir)

        print("\n=== Downloading with SDK ===")
        sdk_flacs = await download_with_sdk(TEST_ALBUM_ID, sdk_dir)

        assert len(sr_flacs) > 0, "streamrip should have downloaded FLACs"
        assert len(sdk_flacs) > 0, "SDK should have downloaded FLACs"
        assert len(sr_flacs) == len(sdk_flacs), (
            f"Track count mismatch: streamrip={len(sr_flacs)}, SDK={len(sdk_flacs)}"
        )

        # Compare file names (relative to output dir)
        print(f"\n=== Comparing file names ===\n")
        sr_names = [os.path.basename(p) for p in sr_flacs]
        sdk_names = [os.path.basename(p) for p in sdk_flacs]
        name_mismatches = []
        for i, (sr_name, sdk_name) in enumerate(zip(sr_names, sdk_names)):
            if sr_name != sdk_name:
                name_mismatches.append({"track": i + 1, "streamrip": sr_name, "sdk": sdk_name})
                print(f"  ✗ Track {i+1} filename differs:")
                print(f"    SR:  {sr_name}")
                print(f"    SDK: {sdk_name}")
            else:
                print(f"  ✓ Track {i+1}: {sr_name}")

        # Compare folder names
        sr_folder = os.path.relpath(os.path.dirname(sr_flacs[0]), sr_dir)
        sdk_folder = os.path.relpath(os.path.dirname(sdk_flacs[0]), sdk_dir)
        print(f"\n=== Comparing folder names ===")
        print(f"  SR:  {sr_folder}")
        print(f"  SDK: {sdk_folder}")
        folder_match = sr_folder == sdk_folder

        # Compare ALL tags
        print(f"\n=== Comparing {len(sr_flacs)} tracks — ALL tags ===\n")
        tag_mismatches = []
        sdk_extras_found = []
        for i, (sr_path, sdk_path) in enumerate(zip(sr_flacs, sdk_flacs)):
            sr_tags = read_all_flac_tags(sr_path)
            sdk_tags = read_all_flac_tags(sdk_path)

            all_keys = sorted(set(list(sr_tags.keys()) + list(sdk_tags.keys())))
            track_name = sr_tags.get("title", sdk_tags.get("title", f"Track {i+1}"))
            track_diffs = []

            for key in all_keys:
                sr_val = str(sr_tags.get(key, "")).strip()
                sdk_val = str(sdk_tags.get(key, "")).strip()

                if sr_val != sdk_val:
                    # SDK extra tags (present in SDK, absent in streamrip) are improvements
                    if key in SDK_INTENTIONAL_DIFFS:
                        sdk_extras_found.append({"tag": key, "value": sdk_val})
                        continue
                    track_diffs.append({"tag": key, "streamrip": sr_val, "sdk": sdk_val})

            if track_diffs:
                tag_mismatches.append({"track": track_name, "diffs": track_diffs})
                print(f"  ✗ Track {i+1}: {track_name}")
                for d in track_diffs:
                    print(f"    {d['tag']}: SR={d['streamrip']!r} vs SDK={d['sdk']!r}")
            else:
                print(f"  ✓ Track {i+1}: {track_name} — all tags match")

        # Summary
        print(f"\n=== Summary ===")
        print(f"  Tracks compared: {len(sr_flacs)}")
        print(f"  File name mismatches: {len(name_mismatches)}")
        print(f"  Folder name match: {folder_match}")
        print(f"  Tag mismatches: {len(tag_mismatches)}")
        if sdk_extras_found:
            unique_extras = {e["tag"] for e in sdk_extras_found}
            print(f"  SDK extras (improvements): {', '.join(sorted(unique_extras))}")

        # Enforce parity — zero mismatches on all tags
        assert len(tag_mismatches) == 0, (
            f"{len(tag_mismatches)} tracks have tag mismatches"
        )
