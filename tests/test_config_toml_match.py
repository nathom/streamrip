import pytest
import tomlkit
from tomlkit.toml_document import TOMLDocument

from streamrip.config import ConfigData


@pytest.fixture()
def toml():
    with open("streamrip/config.toml") as f:
        t = tomlkit.parse(f.read())  # type: ignore
    return t


@pytest.fixture()
def config():
    return ConfigData.defaults()


def test_toml_subset_of_py(toml, config):
    """Test that all keys in the TOML file are in the config classes."""
    for k, v in toml.items():
        if k in config.__slots__:
            if isinstance(v, TOMLDocument):
                test_toml_subset_of_py(v, getattr(config, k))
        else:
            raise Exception(f"{k} not in {config.__slots__}")


exclude = {"toml", "_modified"}


def test_py_subset_of_toml(toml, config):
    """Test that all keys in the python classes are in the TOML file."""
    for item in config.__slots__:
        if item in exclude:
            continue
        if item in toml:
            if "Config" in item.__class__.__name__:
                test_py_subset_of_toml(toml[item], getattr(config, item))
        else:
            raise Exception(f"Config field {item} not in {list(toml.keys())}")
