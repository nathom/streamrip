import re

import pytest

from streamrip import __version__ as init_version
from streamrip.config import CURRENT_CONFIG_VERSION

toml_version_re = re.compile(r'version\s*\=\s*"([\d\.]+)"')


@pytest.fixture
def pyproject_version() -> str:
    with open("pyproject.toml") as f:
        m = toml_version_re.search(f.read())
    assert m is not None
    return m.group(1)


@pytest.fixture
def config_version() -> str | None:
    with open("streamrip/config.toml") as f:
        m = toml_version_re.search(f.read())
    assert m is not None
    return m.group(1)


def test_config_versions_match(config_version):
    assert config_version == CURRENT_CONFIG_VERSION


def test_streamrip_versions_match(pyproject_version):
    assert pyproject_version == init_version
