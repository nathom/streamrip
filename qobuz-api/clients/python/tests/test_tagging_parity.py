"""A/B comparison: streamrip tagger vs SDK tagger.

Downloads the same album with both pipelines and compares every
ID3/FLAC tag field to verify 100% parity.

Run: QOBUZ_TOKEN=... poetry run pytest tests/test_tagging_parity.py -v -s
"""

import asyncio
import os
import tempfile

import pytest
from mutagen.flac import FLAC

# Harold Budd — Ambient 2 (10 tracks, consistent metadata)
TEST_ALBUM_ID = "0724386649751"
QOBUZ_TOKEN = os.environ.get("QOBUZ_TOKEN", "")

skip_no_creds = pytest.mark.skipif(
    not QOBUZ_TOKEN, reason="Set QOBUZ_TOKEN env var"
)


async def download_with_streamrip(album_id: str, output_dir: str) -> list[str]:
    """Download album using streamrip pipeline, return FLAC paths."""
    from backend.services.config_bridge import build_streamrip_config
    from backend.models.database import AppDatabase
    from streamrip.media import PendingAlbum
    from streamrip.db import build_database

    db_file = os.path.join(output_dir, "app.db")
    db = AppDatabase(db_file)
    db.set_config("qobuz_token", QOBUZ_TOKEN)
    db.set_config("qobuz_user_id", "2113276")
    db.set_config("qobuz_quality", "2")
    db.set_config("downloads_path", output_dir)

    config = build_streamrip_config(db)
    config.session.downloads.folder = output_dir

    from streamrip.client.qobuz import QobuzClient
    client = QobuzClient(config)
    await client.login()

    from streamrip.db import Dummy, Database as SRDatabase
    database = SRDatabase(Dummy(), Dummy(), Dummy())
    pending = PendingAlbum(album_id, client, config, database)
    media = await pending.resolve()
    assert media is not None
    await media.rip()

    await client.session.close()

    flacs = []
    for root, _, files in os.walk(output_dir):
        for f in sorted(files):
            if f.endswith(".flac"):
                flacs.append(os.path.join(root, f))
    return flacs


async def download_with_sdk(album_id: str, output_dir: str) -> list[str]:
    """Download album using SDK pipeline, return FLAC paths."""
    from qobuz import QobuzClient, AlbumDownloader, DownloadConfig
    from streamrip.client.qobuz import QobuzSpoofer

    async with QobuzSpoofer() as spoofer:
        app_id, secrets = await spoofer.get_app_id_and_secrets()

    # Find working secret
    app_secret = None
    for secret in secrets:
        try:
            async with QobuzClient(
                app_id=app_id, user_auth_token=QOBUZ_TOKEN, app_secret=secret
            ) as test_client:
                await test_client.streaming.get_file_url(19512574, quality=2)
                app_secret = secret
                break
        except Exception:
            continue
    assert app_secret is not None

    async with QobuzClient(
        app_id=app_id, user_auth_token=QOBUZ_TOKEN, app_secret=app_secret
    ) as client:
        dl = AlbumDownloader(client, DownloadConfig(
            output_dir=output_dir,
            quality=2,
        ))
        result = await dl.download(album_id)
        assert result.successful > 0

    flacs = []
    for root, _, files in os.walk(output_dir):
        for f in sorted(files):
            if f.endswith(".flac"):
                flacs.append(os.path.join(root, f))
    return flacs


# Tags to compare — covering all fields both taggers write
FLAC_TAGS = [
    "title",
    "artist",
    "albumartist",
    "album",
    "tracknumber",
    "discnumber",
    "genre",
    "date",
    "year",
    "organization",  # label
    "isrc",
]


def read_flac_tags(path: str) -> dict[str, str]:
    """Read all relevant tags from a FLAC file."""
    audio = FLAC(path)
    tags = {}
    for key in FLAC_TAGS:
        values = audio.get(key, [])
        tags[key] = values[0] if values else ""
    tags["_has_cover"] = len(audio.pictures) > 0
    tags["_duration"] = audio.info.length
    tags["_sample_rate"] = audio.info.sample_rate
    tags["_bits_per_sample"] = audio.info.bits_per_sample
    return tags


@skip_no_creds
async def test_tagging_parity():
    """Download same album with both pipelines, compare every tag."""
    with tempfile.TemporaryDirectory() as sr_dir, \
         tempfile.TemporaryDirectory() as sdk_dir:

        print("\n=== Downloading with streamrip ===")
        sr_flacs = await download_with_streamrip(TEST_ALBUM_ID, sr_dir)

        print("\n=== Downloading with SDK ===")
        sdk_flacs = await download_with_sdk(TEST_ALBUM_ID, sdk_dir)

        assert len(sr_flacs) > 0, "streamrip should have downloaded FLACs"
        assert len(sdk_flacs) > 0, "SDK should have downloaded FLACs"
        assert len(sr_flacs) == len(sdk_flacs), (
            f"Track count mismatch: streamrip={len(sr_flacs)}, SDK={len(sdk_flacs)}"
        )

        print(f"\n=== Comparing {len(sr_flacs)} tracks ===\n")

        mismatches = []
        for i, (sr_path, sdk_path) in enumerate(zip(sr_flacs, sdk_flacs)):
            sr_tags = read_flac_tags(sr_path)
            sdk_tags = read_flac_tags(sdk_path)

            track_name = sr_tags.get("title", f"Track {i+1}")
            track_mismatches = []

            for key in FLAC_TAGS + ["_has_cover"]:
                sr_val = str(sr_tags.get(key, ""))
                sdk_val = str(sdk_tags.get(key, ""))

                # Normalize — streamrip may format differently
                sr_norm = sr_val.strip().lower()
                sdk_norm = sdk_val.strip().lower()

                if sr_norm != sdk_norm:
                    track_mismatches.append({
                        "tag": key,
                        "streamrip": sr_val,
                        "sdk": sdk_val,
                    })

            if track_mismatches:
                mismatches.append({"track": track_name, "diffs": track_mismatches})
                print(f"  ✗ Track {i+1}: {track_name}")
                for m in track_mismatches:
                    print(f"    {m['tag']}: SR={m['streamrip']!r} vs SDK={m['sdk']!r}")
            else:
                print(f"  ✓ Track {i+1}: {track_name} — all tags match")

        print(f"\n=== Summary ===")
        print(f"  Tracks compared: {len(sr_flacs)}")
        print(f"  Tracks with mismatches: {len(mismatches)}")

        if mismatches:
            # Print detailed report but don't fail yet — let's see what differs
            print("\n=== Detailed Mismatches ===")
            for m in mismatches:
                print(f"\n  Track: {m['track']}")
                for d in m["diffs"]:
                    print(f"    {d['tag']}:")
                    print(f"      streamrip: {d['streamrip']!r}")
                    print(f"      SDK:       {d['sdk']!r}")

        # organization (label) is an intentional improvement — SDK writes it, streamrip doesn't
        real_mismatches = [
            m for m in mismatches
            if any(d["tag"] != "organization" for d in m["diffs"])
        ]
        assert len(real_mismatches) == 0, (
            f"{len(real_mismatches)} tracks have tag mismatches "
            f"(excluding organization/label which SDK intentionally adds)"
        )
