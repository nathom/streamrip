
from streamrip.filepath_utils import clean_filename, clean_filepath, truncate_str


class TestCleanFilename:
    def test_slash_replaced_by_dash(self):
        assert clean_filename("foo/bar") == "foo-bar"

    def test_multiple_slashes(self):
        assert clean_filename("a/b/c") == "a-b-c"

    def test_no_slash_unchanged(self):
        result = clean_filename("normal")
        assert result == "normal"

    def test_leading_slash(self):
        assert clean_filename("/etc/passwd") == "-etc-passwd"

    def test_empty_string(self):
        result = clean_filename("")
        assert result == ""

    def test_restrict_keeps_printable(self):
        result = clean_filename("hello\x00world", restrict=True)
        assert "\x00" not in result
        assert "hello" in result
        assert "world" in result

    def test_slash_then_restrict(self):
        result = clean_filename("ac/dc", restrict=True)
        assert "/" not in result
        assert "-" in result


class TestCleanFilepath:
    def test_preserves_separator(self):
        result = clean_filepath("artist/album")
        assert "/" in result

    def test_plain_name(self):
        result = clean_filepath("Pink Floyd - The Wall [FLAC]")
        assert "Pink Floyd" in result

    def test_restrict_strips_non_printable(self):
        result = clean_filepath("hello\x00world", restrict=True)
        assert "\x00" not in result


class TestTruncateStr:
    def test_short_string_unchanged(self):
        s = "hello"
        assert truncate_str(s) == s

    def test_exactly_255_bytes_unchanged(self):
        s = "a" * 255
        assert truncate_str(s) == s

    def test_256_ascii_truncated(self):
        s = "a" * 256
        result = truncate_str(s)
        assert len(result.encode("utf-8")) == 255

    def test_multibyte_boundary_valid_utf8(self):
        # 3-byte CJK char: 3 x 85 = 255 bytes exactly — should pass through unchanged
        s = "中" * 85
        assert len(s.encode("utf-8")) == 255
        assert truncate_str(s) == s

    def test_multibyte_boundary_truncates_cleanly(self):
        # 3-byte char x 86 = 258 bytes — truncate must drop the last partial char
        s = "中" * 86
        result = truncate_str(s)
        encoded = result.encode("utf-8")
        assert len(encoded) <= 255
        # round-trip must work (no UnicodeDecodeError means valid UTF-8)
        encoded.decode("utf-8")
