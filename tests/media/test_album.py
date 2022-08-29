from typing import Dict

import pytest
from pytest_mock import MockerFixture

from streamrip.clients import QobuzClient
from streamrip.constants import FOLDER_FORMAT
from streamrip.media import Album, Track


class TestAlbum:
    def test_get_formatted_folder_with_overflow(
        self,
        monty_python_holy_grail_album_resp: Dict[str, object],
        mocker: MockerFixture,
    ):
        mocked_client = mocker.mock_module.MagicMock()
        mocked_client.get.return_value = monty_python_holy_grail_album_resp
        mocked_client.source = "qobuz"

        # resp = client.get("lj1s9oz62wsqb", "album")
        album = Album.from_api(monty_python_holy_grail_album_resp, mocked_client)
        album.load_meta()
        album.container = "FLAC"

        # need to set folder format here because _prepare_download calls it
        # this unit test does not call it
        album.folder_format = FOLDER_FORMAT

        # act
        folder = album._get_formatted_folder("")

        # assert
        assert (
            folder
            == "Monty Python - The Album Of The Soundtrack Of The Trailer Of The Film Of Monty Python And The Holy Grail (1975) [FLAC] ["
        )

    def test_get_formatted_folder_path_without_overflow(
        self, basic_album_qobuz_response: Dict[str, object], mocker: MockerFixture
    ):

        mocked_client = mocker.mock_module.MagicMock()
        mocked_client.get.return_value = basic_album_qobuz_response
        mocked_client.source = "qobuz"

        # resp = client.get("lj1s9oz62wsqb", "album")
        album = Album.from_api(basic_album_qobuz_response, mocked_client)
        album.load_meta()
        album.container = "FLAC"

        album.folder_format = FOLDER_FORMAT

        # act
        folder = album._get_formatted_folder("")

        # assert
        assert folder == "Johnny Appleseed - bar (2022) [FLAC] [16B-44.1kHz]"

    @pytest.mark.parametrize(
        ["format", "expected_output"],
        [(None, r"foo\Johnny Appleseed - bar (2022) [FLAC] [16B-44.1kHz]"),
        ("", r"foo\Johnny Appleseed - bar (2022) [FLAC] [16B-44.1kHz]"),
        (r"{albumartist} - {title}", r"foo\Johnny Appleseed - bar"),
        (r"{year}/{albumartist} - {title}", r"foo\2022/Johnny Appleseed - bar"),
        ("foo", r"foo\foo")],
    )
    def test_get_formatted_folder_path_with_a_different_format(
        self,
        basic_album_qobuz_response: Dict[str, object],
        mocker: MockerFixture,
        format: str,
        expected_output: str,
    ):
        mocked_client = mocker.mock_module.MagicMock()
        mocked_client.get.return_value = basic_album_qobuz_response
        mocked_client.source = "qobuz"

        # resp = client.get("lj1s9oz62wsqb", "album")
        album = Album.from_api(basic_album_qobuz_response, mocked_client)
        album.load_meta()
        album.container = "FLAC"

        album.folder_format = format or FOLDER_FORMAT

        # act
        actual_folder = album._get_formatted_folder("foo")

        # assert
        assert actual_folder == expected_output
