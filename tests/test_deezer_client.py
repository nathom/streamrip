import deezer
import pytest

from streamrip.client.deezer import DeezerClient
from streamrip.config import Config
from streamrip.exceptions import MissingCredentialsError, NonStreamableError
from tests.util import arun


def test_client_raises_missing_credentials():
    c = Config.defaults()
    with pytest.raises(MissingCredentialsError):
        arun(DeezerClient(c).login())


def test_get_downloadable_wrong_license(mocker):
    config = Config.defaults()
    free_client = DeezerClient(config)
    quality = 2

    def raise_wrong_license():
        raise deezer.WrongLicense("")

    mocker.patch.object(
        free_client.client.gw,
        "get_track",
        lambda _: {
            "FILESIZE_FLAC": "1234",
            "TRACK_TOKEN": "foobar",
        },
    )
    mocker.patch.object(
        free_client.client,
        "get_track_url",
        lambda *args, **kwargs: raise_wrong_license(),
    )

    with pytest.raises(
        NonStreamableError,
        match=rf"The requested quality \({quality}\) is not available with your subscription. Deezer HiFi is required for quality 2. Deezer Premium is required for quality 1. Otherwise, the maximum quality allowed is 0.",
    ):
        arun(free_client.get_downloadable("foobar", quality))
