from unittest.mock import MagicMock

from streamrip.media.artist import Artist


def _mock_album(title: str, albumartist: str = "Artist", bit_depth=24, sampling_rate=96, explicit=False):
    a = MagicMock()
    a.meta.album = title
    a.meta.albumartist = albumartist
    a.meta.info.bit_depth = bit_depth
    a.meta.info.sampling_rate = sampling_rate
    a.meta.info.explicit = explicit
    return a


def _artist(name: str = "Artist") -> Artist:
    return Artist(name=name, albums=[], client=MagicMock(), config=MagicMock())


class TestExtrasFilter:
    def test_regular_album_kept(self):
        artist = _artist()
        a = _mock_album("Kind of Blue")
        assert artist._extras(a) is True

    def test_deluxe_filtered(self):
        artist = _artist()
        a = _mock_album("Kind of Blue (Deluxe Edition)")
        assert artist._extras(a) is False

    def test_live_filtered(self):
        artist = _artist()
        assert artist._extras(_mock_album("Live at Montreux")) is False

    def test_remix_filtered(self):
        artist = _artist()
        assert artist._extras(_mock_album("Remix Album")) is False

    def test_case_insensitive(self):
        artist = _artist()
        assert artist._extras(_mock_album("LIVE Sessions")) is False


class TestFeaturesFilter:
    def test_matching_artist_kept(self):
        artist = _artist("Miles Davis")
        a = _mock_album("Bitches Brew", albumartist="Miles Davis")
        assert artist._features(a) is True

    def test_different_artist_filtered(self):
        artist = _artist("Miles Davis")
        a = _mock_album("Collaboration", albumartist="Miles Davis & John Coltrane")
        assert artist._features(a) is False


class TestNonStudioAlbumsFilter:
    def test_studio_album_kept(self):
        artist = _artist("Artist")
        a = _mock_album("Studio Album", albumartist="Artist")
        assert artist._non_studio_albums(a) is True

    def test_various_artists_filtered(self):
        artist = _artist("Artist")
        a = _mock_album("Compilation", albumartist="Various Artists")
        assert artist._non_studio_albums(a) is False

    def test_live_album_filtered(self):
        artist = _artist("Artist")
        a = _mock_album("Live in Paris", albumartist="Artist")
        assert artist._non_studio_albums(a) is False


class TestNonRemasterFilter:
    def test_remaster_kept(self):
        artist = _artist()
        a = _mock_album("Dark Side of the Moon (Remastered)")
        assert artist._non_remaster(a) is True

    def test_master_edition_kept(self):
        artist = _artist()
        a = _mock_album("Master Edition")
        assert artist._non_remaster(a) is True

    def test_regular_album_filtered(self):
        artist = _artist()
        a = _mock_album("Regular Album")
        assert artist._non_remaster(a) is False


class TestFilterRepeats:
    def test_keeps_highest_quality(self):
        a_mp3 = _mock_album("Dark Side", bit_depth=None, sampling_rate=None)
        a_flac = _mock_album("Dark Side", bit_depth=24, sampling_rate=96)
        result = Artist._filter_repeats([a_mp3, a_flac])
        assert len(result) == 1
        assert result[0].meta.info.bit_depth == 24

    def test_different_titles_both_kept(self):
        a1 = _mock_album("Album One", bit_depth=16, sampling_rate=44100)
        a2 = _mock_album("Album Two", bit_depth=16, sampling_rate=44100)
        result = Artist._filter_repeats([a1, a2])
        assert len(result) == 2

    def test_bracket_variant_deduplicated(self):
        a1 = _mock_album("Wish You Were Here", bit_depth=16, sampling_rate=44100)
        a2 = _mock_album("Wish You Were Here (2011 Remaster)", bit_depth=24, sampling_rate=96)
        result = Artist._filter_repeats([a1, a2])
        assert len(result) == 1
        assert result[0].meta.info.bit_depth == 24

    def test_explicit_breaks_tie(self):
        a1 = _mock_album("Album", bit_depth=16, sampling_rate=44100, explicit=False)
        a2 = _mock_album("Album", bit_depth=16, sampling_rate=44100, explicit=True)
        result = Artist._filter_repeats([a1, a2])
        assert len(result) == 1
        assert result[0].meta.info.explicit is True


class TestApplyFilters:
    def _make_filter_conf(self, repeats=False, extras=False, features=False,
                          non_studio_albums=False, non_remaster=False):
        f = MagicMock()
        f.repeats = repeats
        f.extras = extras
        f.features = features
        f.non_studio_albums = non_studio_albums
        f.non_remaster = non_remaster
        return f

    def test_no_filters_returns_all(self):
        artist = _artist("A")
        albums = [_mock_album("X"), _mock_album("Y")]
        result = artist._apply_filters(albums, self._make_filter_conf())
        assert len(result) == 2

    def test_extras_filter_applied(self):
        artist = _artist("A")
        albums = [_mock_album("Regular"), _mock_album("Live Edition")]
        result = artist._apply_filters(albums, self._make_filter_conf(extras=True))
        assert len(result) == 1
        assert result[0].meta.album == "Regular"

    def test_features_filter_applied(self):
        artist = _artist("Solo")
        albums = [
            _mock_album("Own Album", albumartist="Solo"),
            _mock_album("Collab", albumartist="Solo & Friend"),
        ]
        result = artist._apply_filters(albums, self._make_filter_conf(features=True))
        assert len(result) == 1
        assert result[0].meta.album == "Own Album"
