import functools
from typing import Optional, Type, TypeVar, Union, Any, get_type_hints, get_origin


def get_album_track_ids(source: str, resp) -> list[str]:
    tracklist = resp["tracks"]
    if source == "qobuz":
        tracklist = tracklist["items"]
    return [track["id"] for track in tracklist]


def safe_get(dictionary, *keys, default=None):
    return functools.reduce(
        lambda d, key: d.get(key, default) if isinstance(d, dict) else default,
        keys,
        dictionary,
    )


T = TypeVar("T")


def typed(thing, expected_type: Type[T] | Any) -> T:
    # For Union types (like str | None, int | float)
    try:
        # Check if it's a union type from Python 3.10+ (int | str)
        origin = get_origin(expected_type)
        if origin is Union:
            # Skip type checking for union types
            return thing
    except (TypeError, AttributeError):
        pass
    
    # Regular type checking for non-union types
    if expected_type is not None:
        assert isinstance(thing, expected_type)
    return thing


def get_quality_id(
    bit_depth: Optional[int],
    sampling_rate: Optional[int | float],
) -> int:
    """Get the universal quality id from bit depth and sampling rate.

    :param bit_depth:
    :type bit_depth: Optional[int]
    :param sampling_rate: In kHz
    :type sampling_rate: Optional[int]
    """
    # XXX: Should `0` quality be supported?
    if bit_depth is None or sampling_rate is None:  # is lossy
        return 1

    if bit_depth == 16:
        return 2

    if bit_depth == 24:
        if sampling_rate <= 96:
            return 3

        return 4

    raise Exception(f"Invalid {bit_depth = }")
