from typing import Optional

from streamrip.media import Album, Artist
from streamrip.metadata import AlbumInfo, AlbumMetadata

# helper function to create an album with given parameters


def create_album(
    title: str,
    explicit: bool,
    sampling_rate: Optional[float],
    bit_depth: Optional[int],
    id: str,
) -> Album:
    info = AlbumInfo(
        id=id,
        quality=0,
        container="mp3",
        explicit=explicit,
        sampling_rate=sampling_rate,
        bit_depth=bit_depth,
    )
    metadata = AlbumMetadata(
        info=info,
        album=title,
        albumartist="artist",
        year="2020",
        genre=["genre"],
        covers=None,  # type: ignore
        tracktotal=10,
    )
    return Album(meta=metadata, tracks=[], config=None, folder="folder", db=None)  # type: ignore


# tests


def test_single_album():
    # one album should simply be returned
    album = create_album("Test Album", False, 44.1, 16, id="a1")
    result = Artist._filter_repeats([album])
    assert len(result) == 1
    assert result[0] == album


def test_different_titles():
    # albums with different titles should not be grouped
    album1 = create_album("Test Album", False, 44.1, 16, id="a1")
    album2 = create_album("Another Album", True, 96, 24, id="a2")
    result = Artist._filter_repeats([album1, album2])
    assert len(result) == 2
    titles = {a.meta.album.strip().lower() for a in result}
    assert "test album" in titles
    assert "another album" in titles


def test_same_title_different_bit_depth():
    # when bit_depth differs, the album with higher bit_depth wins
    album1 = create_album("Test Album", False, 44.1, 16, id="a1")
    album2 = create_album("Test Album (Deluxe)", False, 44.1, 24, id="a2")
    result = Artist._filter_repeats([album1, album2])
    assert len(result) == 1
    assert result[0] == album2


def test_same_title_tie_bit_depth_different_sampling():
    # same bit_depth; higher sampling_rate should win
    album1 = create_album("Test Album", False, 44.1, 24, id="a1")
    album2 = create_album("Test Album (Live)", False, 96, 24, id="a2")
    result = Artist._filter_repeats([album1, album2])
    assert len(result) == 1
    assert result[0] == album2


def test_same_title_tie_bit_depth_and_sampling_different_explicit():
    # if bit_depth and sampling_rate are tied, explicit true is prioritized
    album1 = create_album("Test Album", False, 96, 24, id="a1")
    album2 = create_album("Test Album (Edited)", True, 96, 24, id="a2")
    result = Artist._filter_repeats([album1, album2])
    assert len(result) == 1
    assert result[0] == album2


def test_grouping_normalization():
    # titles differing only by bracketed parts should be grouped together
    album1 = create_album("Album X", False, 44.1, 16, id="a1")
    album2 = create_album("Album X (Deluxe)", False, 96, 24, id="a2")
    album3 = create_album("Album X [Special Edition]", True, 44.1, 16, id="a3")
    result = Artist._filter_repeats([album1, album2, album3])
    assert len(result) == 1
    # album2 wins due to higher bit_depth and sampling_rate
    assert result[0] == album2


def test_multiple_groups():
    # multiple groups should yield one winner per group
    album_a1 = create_album("Album A", False, 44.1, 16, id="a1")
    album_a2 = create_album("Album A (Remastered)", True, 96, 24, id="a2")
    album_b1 = create_album("Album B", False, 96, 24, id="b1")
    album_b2 = create_album("Album B (Live)", True, 44.1, 16, id="b2")
    album_c1 = create_album("Album C", False, None, None, id="c1")
    result = Artist._filter_repeats([album_a1, album_a2, album_b1, album_b2, album_c1])
    assert len(result) == 3
    winners = {a.meta.info.id for a in result}
    # expected winners: album a2, album b1, album c1
    assert winners == {"a2", "b1", "c1"}


def test_missing_values():
    # albums with missing sampling_rate and bit_depth (treated as 0) should be sorted by explicit flag
    album1 = create_album("Test Album", False, None, None, id="a1")
    album2 = create_album("Test Album", True, None, None, id="a2")
    result = Artist._filter_repeats([album1, album2])
    assert len(result) == 1
    # explicit true wins over false when other quality metrics are equal (or missing)
    assert result[0] == album2
