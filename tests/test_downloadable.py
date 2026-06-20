"""Tests for client/downloadable.py — constructors, quality clipping, crypto helpers."""

from unittest.mock import MagicMock

import pytest

from streamrip.client.downloadable import (
    BasicDownloadable,
    DeezerDownloadable,
    SoundcloudDownloadable,
    TidalDownloadable,
    generate_temp_path,
)
from streamrip.exceptions import NonStreamableError

# ── generate_temp_path ───────────────────────────────────────────────────────

class TestGenerateTempPath:
    def test_returns_string(self):
        path = generate_temp_path("https://example.com/track.mp3")
        assert isinstance(path, str)

    def test_contains_streamrip_prefix(self):
        path = generate_temp_path("https://example.com/track.mp3")
        assert "__streamrip_" in path

    def test_ends_with_download_extension(self):
        path = generate_temp_path("https://example.com/track.mp3")
        assert path.endswith(".download")

    def test_different_urls_give_different_paths(self):
        p1 = generate_temp_path("https://example.com/a.mp3")
        p2 = generate_temp_path("https://example.com/b.mp3")
        # hash part differs
        assert p1 != p2


# ── BasicDownloadable ────────────────────────────────────────────────────────

class TestBasicDownloadable:
    def _make(self, url="https://ex.com/a.flac", ext="flac", source="qobuz"):
        return BasicDownloadable(MagicMock(), url, ext, source)

    def test_attributes_set(self):
        d = self._make()
        assert d.url == "https://ex.com/a.flac"
        assert d.extension == "flac"
        assert d.source == "qobuz"
        assert d._size is None

    def test_default_source_unknown(self):
        d = BasicDownloadable(MagicMock(), "https://ex.com/a.mp3", "mp3")
        assert d.source == "Unknown"


# ── DeezerDownloadable ───────────────────────────────────────────────────────

def _deezer_info(quality=2, quality_to_size=None, url="https://cdn.deezer.com/track.flac"):
    if quality_to_size is None:
        quality_to_size = [3_000_000, 8_000_000, 20_000_000]  # mp3-128, mp3-320, flac
    return {
        "quality": quality,
        "id": "12345",
        "quality_to_size": quality_to_size,
        "url": url,
    }


class TestDeezerDownloadable:
    def test_flac_extension(self):
        d = DeezerDownloadable(MagicMock(), _deezer_info(quality=2))
        assert d.extension == "flac"
        assert d.quality == 2

    def test_mp3_extension_quality_1(self):
        d = DeezerDownloadable(MagicMock(), _deezer_info(quality=1))
        assert d.extension == "mp3"

    def test_mp3_extension_quality_0(self):
        d = DeezerDownloadable(MagicMock(), _deezer_info(quality=0))
        assert d.extension == "mp3"

    def test_quality_clipped_to_max_available(self):
        # Requested quality=2 (FLAC) but FLAC size is 0 → max available is 1
        info = _deezer_info(quality=2, quality_to_size=[3_000_000, 8_000_000, 0])
        d = DeezerDownloadable(MagicMock(), info)
        assert d.quality == 1
        assert d.extension == "mp3"

    def test_quality_clipped_when_only_mp3_128(self):
        info = _deezer_info(quality=2, quality_to_size=[5_000_000, 0, 0])
        d = DeezerDownloadable(MagicMock(), info)
        assert d.quality == 0

    def test_no_available_quality_raises(self):
        info = _deezer_info(quality=2, quality_to_size=[0, 0, 0])
        with pytest.raises(NonStreamableError):
            DeezerDownloadable(MagicMock(), info)

    def test_size_set_from_quality_to_size(self):
        info = _deezer_info(quality=2, quality_to_size=[3_000_000, 8_000_000, 20_000_000])
        d = DeezerDownloadable(MagicMock(), info)
        assert d._size == 20_000_000

    def test_id_stored_as_str(self):
        d = DeezerDownloadable(MagicMock(), _deezer_info())
        assert d.id == "12345"


class TestDeezerBlowfishKey:
    def test_returns_bytes(self):
        key = DeezerDownloadable._generate_blowfish_key("77874822")
        assert isinstance(key, bytes)

    def test_deterministic(self):
        k1 = DeezerDownloadable._generate_blowfish_key("12345")
        k2 = DeezerDownloadable._generate_blowfish_key("12345")
        assert k1 == k2

    def test_different_ids_different_keys(self):
        k1 = DeezerDownloadable._generate_blowfish_key("11111")
        k2 = DeezerDownloadable._generate_blowfish_key("22222")
        assert k1 != k2

    def test_key_length_16(self):
        key = DeezerDownloadable._generate_blowfish_key("77874822")
        assert len(key) == 16


class TestDeezerDecryptChunk:
    def test_decrypt_encrypt_roundtrip(self):
        key = DeezerDownloadable._generate_blowfish_key("77874822")
        from Cryptodome.Cipher import Blowfish

        data = b"A" * 2048  # Blowfish requires multiple of 8 bytes
        encrypted = Blowfish.new(
            key, Blowfish.MODE_CBC, b"\x00\x01\x02\x03\x04\x05\x06\x07"
        ).encrypt(data)
        decrypted = DeezerDownloadable._decrypt_chunk(key, encrypted)
        assert decrypted == data


# ── TidalDownloadable ────────────────────────────────────────────────────────

class TestTidalDownloadable:
    def test_flac_codec_gives_flac_extension(self):
        d = TidalDownloadable(MagicMock(), "https://tidal.com/track.flac", "flac", None, None)
        assert d.extension == "flac"

    def test_mqa_codec_gives_flac_extension(self):
        d = TidalDownloadable(MagicMock(), "https://tidal.com/track.mqa", "MQA", None, None)
        assert d.extension == "flac"

    def test_aac_codec_gives_m4a_extension(self):
        d = TidalDownloadable(MagicMock(), "https://tidal.com/track.m4a", "AAC", None, None)
        assert d.extension == "m4a"

    def test_url_none_with_restrictions_raises(self):
        restrictions = [{"code": "PremiumRequired"}]
        with pytest.raises(NonStreamableError, match=r"(?i)premium"):
            TidalDownloadable(MagicMock(), None, "flac", None, restrictions)

    def test_url_none_without_restrictions_raises(self):
        with pytest.raises(NonStreamableError):
            TidalDownloadable(MagicMock(), None, "flac", None, None)

    def test_url_none_empty_restrictions_raises(self):
        with pytest.raises(NonStreamableError):
            TidalDownloadable(MagicMock(), None, "flac", None, [])

    def test_enc_key_stored(self):
        d = TidalDownloadable(
            MagicMock(), "https://tidal.com/t.flac", "FLAC", "abc123=", None
        )
        assert d.enc_key == "abc123="

    def test_no_enc_key_stored_as_none(self):
        d = TidalDownloadable(MagicMock(), "https://tidal.com/t.flac", "FLAC", None, None)
        assert d.enc_key is None


# ── SoundcloudDownloadable ───────────────────────────────────────────────────

class TestSoundcloudDownloadable:
    def test_mp3_type(self):
        d = SoundcloudDownloadable(MagicMock(), {"type": "mp3", "url": "https://sc.com/t.mp3"})
        assert d.extension == "mp3"
        assert d.file_type == "mp3"

    def test_original_type_gives_flac(self):
        d = SoundcloudDownloadable(MagicMock(), {"type": "original", "url": "https://sc.com/t.flac"})
        assert d.extension == "flac"

    def test_invalid_type_raises(self):
        with pytest.raises(Exception, match="Invalid file type"):
            SoundcloudDownloadable(MagicMock(), {"type": "wav", "url": "https://sc.com/t.wav"})

    def test_source_is_soundcloud(self):
        d = SoundcloudDownloadable(MagicMock(), {"type": "mp3", "url": "https://sc.com/t.mp3"})
        assert d.source == "soundcloud"

    def test_url_stored(self):
        url = "https://sc.com/track.mp3"
        d = SoundcloudDownloadable(MagicMock(), {"type": "mp3", "url": url})
        assert d.url == url
