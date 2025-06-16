from string import printable

import pytest

from streamrip.filepath_utils import (
    ALLOWED_CHARS,
    clean_filename,
    clean_filepath,
    truncate_str,
)


@pytest.fixture
def long_unicode_string() -> str:
    """Fixture providing a long string with unicode characters."""
    return "test_" + "ñ" * 100  # Each ñ is 2 bytes in UTF-8


@pytest.fixture
def problematic_filename() -> str:
    """Fixture providing a filename with problematic characters."""
    return "file<>|*?/with\\invalid:chars.mp3"


@pytest.fixture
def real_world_long_paths() -> list[str]:
    """Fixture providing real-world problematic paths from error messages."""
    return [
        "M:/The London Metropolitan Orchestra, Elliot Goldenthal, Steven Mercurio, Jonathan Sheffer, The Mask Orchestra, The Pickled Heads Band - Titus - Original Motion Picture Soundtrack (2000) [FLAC] [16B-44.1kHz]/11. Elliot Goldenthal - Pickled Heads (Instrumental).flac",
        "M:/Toronto Symphony Orchestra, Gustavo Gimeno, Isabel Leonard, Paul Appleby, Derek Welton - Stravinsky Pulcinella, ballet with song in one act, K034 XIV. Tarantella (2025) [FLAC] [24B-96kHz]/01. Toronto Symphony Orchestra - Pulcinella, ballet with song in one act, K034 XIV. Tarantella.flac",
        "Very/Long/Path/With/Many/Nested/Directories/And/A/Very/Long/Filename/That/Could/Cause/Issues.flac",
    ]


@pytest.mark.parametrize(
    ("input_str", "expected_max_bytes"),
    [
        ("short", 255),
        ("a" * 255, 255),
        ("a" * 300, 255),
        ("", 255),
    ],
)
def test_truncate_str_respects_byte_limit(
    input_str: str, expected_max_bytes: int
) -> None:
    """Test that truncate_str respects byte length limits."""
    result = truncate_str(input_str)
    assert len(result.encode()) <= expected_max_bytes
    if len(input_str.encode()) <= expected_max_bytes:
        assert result == input_str


def test_truncate_str_unicode_handling(long_unicode_string: str) -> None:
    """Test that truncate_str handles unicode characters properly."""
    result = truncate_str(long_unicode_string)

    # Result should be valid UTF-8 (no broken characters)
    assert result.encode("utf-8")  # Should not raise exception
    assert len(result.encode()) <= 255


def test_truncate_str_empty_string() -> None:
    """Test truncate_str with empty string."""
    assert truncate_str("") == ""


@pytest.mark.parametrize(
    ("filename", "restrict", "expected_behavior"),
    [
        ("normal_file.mp3", False, "exact_match"),
        ("file with spaces.flac", False, "exact_match"),
        ("very_long_filename_" + "a" * 300 + ".mp3", False, "truncated"),
    ],
)
def test_clean_filename_basic_functionality(
    filename: str, restrict: bool, expected_behavior: str
) -> None:
    """Test basic filename cleaning functionality."""
    result = clean_filename(filename, restrict=restrict)

    if expected_behavior == "exact_match" and len(filename.encode()) <= 255:
        assert filename in result or result == filename
    elif expected_behavior == "truncated":
        # For very long filenames, just ensure it's truncated and valid
        assert len(result.encode()) <= 255
        assert result  # Should not be empty

    assert len(result.encode()) <= 255


def test_clean_filename_sanitizes_invalid_chars(problematic_filename: str) -> None:
    """Test that clean_filename sanitizes invalid characters."""
    result = clean_filename(problematic_filename, restrict=False)
    # Should not contain the problematic characters after sanitization
    invalid_chars = ["<", ">", "|", "*", "?"]
    # pathvalidate should handle these, result should be safe
    for char in invalid_chars:
        assert char not in result, (
            f"Invalid character '{char}' found in sanitized filename: {result}"
        )
    assert len(result.encode()) <= 255


@pytest.mark.parametrize(
    ("filename", "restrict"),
    [
        ("file with spaces.mp3", True),
        ("file\x00\x01\x02.mp3", True),
        ("file\n\t.mp3", True),
    ],
)
def test_clean_filename_restrict_characters(filename: str, restrict: bool) -> None:
    """Test filename cleaning with character restriction."""
    result = clean_filename(filename, restrict=restrict)

    if restrict:
        # All characters should be in ALLOWED_CHARS
        assert all(c in ALLOWED_CHARS for c in result)


def test_clean_filename_unicode_handling() -> None:
    """Test filename cleaning with unicode characters."""
    filename = "track_ñáéíóú.mp3"
    result = clean_filename(filename, restrict=False)
    assert "track" in result
    assert ".mp3" in result

    result_restricted = clean_filename(filename, restrict=True)
    assert "track" in result_restricted
    # Unicode chars should be removed when restricted
    assert "ñ" not in result_restricted


@pytest.mark.parametrize(
    ("filepath", "restrict", "max_length"),
    [
        ("path/to/file.mp3", False, 200),
        ("very/long/path/" + "a" * 300 + "/file.mp3", False, 100),
        ("path/to/file.mp3", False, 10),
        ("", False, 200),
    ],
)
def test_clean_filepath_respects_max_length(
    filepath: str, restrict: bool, max_length: int
) -> None:
    """Test that clean_filepath respects max_length parameter."""
    result = clean_filepath(filepath, restrict=restrict, max_length=max_length)
    assert len(result) <= max_length


@pytest.mark.parametrize(
    ("filepath", "max_length"),
    [
        ("path/to/very/long/filename/that/exceeds/limits.mp3", 50),
        ("short.mp3", 200),
        ("medium/length/path/file.flac", 100),
    ],
)
def test_clean_filepath_truncation_behavior(filepath: str, max_length: int) -> None:
    """Test filepath truncation behavior."""
    result = clean_filepath(filepath, max_length=max_length)
    assert len(result) <= max_length

    if len(filepath) > max_length:
        # Should be truncated and stripped of trailing whitespace
        assert len(result) <= max_length
        assert not result.endswith(" ")


def test_clean_filepath_restrict_characters() -> None:
    """Test filepath cleaning with character restriction."""
    filepath = "path/to/file\x00\x01.mp3"
    result = clean_filepath(filepath, restrict=True)
    assert all(c in ALLOWED_CHARS for c in result)


@pytest.mark.parametrize(
    ("filepath", "expected_preserved"),
    [
        ("path/to/file.mp3", True),
        ("path\\to\\file.mp3", True),  # Windows paths
        ("path/with spaces/file.mp3", True),
    ],
)
def test_clean_filepath_preserves_structure(
    filepath: str, expected_preserved: bool
) -> None:
    """Test that clean_filepath preserves basic path structure."""
    result = clean_filepath(filepath, restrict=False)
    # Should maintain some recognizable structure
    if expected_preserved and len(filepath) <= 200:
        # Basic components should be recognizable
        assert len(result) > 0


def test_clean_filepath_default_max_length() -> None:
    """Test that clean_filepath uses default max_length of 200."""
    long_path = "path/" + "a" * 300 + "/file.mp3"
    result = clean_filepath(long_path)
    assert len(result) <= 200


@pytest.mark.parametrize(
    ("edge_case_path", "expected_max_length"),
    [
        ("", 200),
        ("///", 200),
        ("path/to/file.mp3", 5),
    ],
)
def test_clean_filepath_edge_cases(
    edge_case_path: str, expected_max_length: int
) -> None:
    """Test edge cases for clean_filepath."""
    result = clean_filepath(edge_case_path, max_length=expected_max_length)
    assert len(result) <= expected_max_length


def test_allowed_chars_contains_printable() -> None:
    """Test that ALLOWED_CHARS contains all printable characters."""
    assert ALLOWED_CHARS == set(printable)


@pytest.mark.parametrize("non_printable_char", ["\x00", "\x01", "\x02", "\x1f"])
def test_allowed_chars_excludes_non_printable(non_printable_char: str) -> None:
    """Test that ALLOWED_CHARS excludes non-printable characters."""
    assert non_printable_char not in ALLOWED_CHARS


@pytest.mark.parametrize("max_length", [200, 150, 100])
def test_real_world_problematic_paths(
    real_world_long_paths: list[str], max_length: int
) -> None:
    """Test filepath utilities with real-world problematic paths."""
    for problematic_path in real_world_long_paths:
        result = clean_filepath(problematic_path, max_length=max_length)

        # Should be within length limits
        assert len(result) <= max_length

        # Should not be empty (unless input was empty)
        if problematic_path:
            assert result

        # Should not end with whitespace
        assert not result.endswith(" ")


def test_filename_and_filepath_consistency() -> None:
    """Test that clean_filename and clean_filepath work consistently."""
    test_name = "problematic<>file|name?.mp3"

    filename_result = clean_filename(test_name)
    filepath_result = clean_filepath(f"path/to/{test_name}")

    # Both should produce valid results
    assert len(filename_result.encode()) <= 255
    assert len(filepath_result) <= 200  # default max_length


def test_clean_filepath_handles_windows_long_paths() -> None:
    """Test that clean_filepath handles Windows-style long paths."""
    windows_path = "C:\\Users\\Username\\Music\\Very Long Artist Name\\Very Long Album Name (Year) [Format]\\Very Long Track Name.flac"
    result = clean_filepath(windows_path, max_length=200)

    assert len(result) <= 200
    assert result  # Should not be empty
    assert not result.endswith(" ")


@pytest.mark.parametrize(
    "unicode_path",
    [
        "path/to/ñáéíóú/file.mp3",
        "路径/到/文件.mp3",
        "путь/к/файлу.mp3",
    ],
)
def test_clean_filepath_unicode_paths(unicode_path: str) -> None:
    """Test clean_filepath with various unicode characters."""
    result = clean_filepath(unicode_path, restrict=False, max_length=200)
    assert len(result) <= 200

    result_restricted = clean_filepath(unicode_path, restrict=True, max_length=200)
    assert len(result_restricted) <= 200
    assert all(c in ALLOWED_CHARS for c in result_restricted)
