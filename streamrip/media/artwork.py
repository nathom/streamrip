import asyncio
import logging
import os
import shutil

import aiohttp
from PIL import Image

from ..client import BasicDownloadable
from ..config import ArtworkConfig
from ..metadata import Covers

_artwork_tempdirs: set[str] = set()

logger = logging.getLogger("streamrip")


def remove_artwork_tempdirs():
    logger.debug("Removing dirs %s", _artwork_tempdirs)
    for path in _artwork_tempdirs:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass


async def download_artwork(
    session: aiohttp.ClientSession,
    folder: str,
    covers: Covers,
    config: ArtworkConfig,
    for_playlist: bool,
) -> tuple[str | None, str | None]:
    """Download artwork and update passed Covers object with filepaths.

    If paths for the selected sizes already exist in `covers`, nothing will
    be downloaded.

    If `for_playlist` is set, it will not download hires cover art regardless
    of the config setting.

    Embedded artworks are put in a temporary directory under `folder` called
    "__embed" that can be deleted once a playlist or album is done downloading.

    Hi-res (saved) artworks are kept in `folder` as "cover.jpg".

    Args:
    ----
        session (aiohttp.ClientSession):
        folder (str):
        covers (Covers):
        config (ArtworkConfig):
        for_playlist (bool): Set to disable saved hires covers.

    Returns:
    -------
        (path to embedded artwork, path to hires artwork)
    """
    save_artwork, embed = config.save_artwork, config.embed
    if for_playlist:
        save_artwork = False

    if not (save_artwork or embed) or covers.empty():
        # No need to download anything
        return None, None

    downloadables = []

    _, l_url, saved_cover_path = covers.largest()
    if saved_cover_path is None and save_artwork:
        saved_cover_path = os.path.join(folder, "cover.jpg")
        assert l_url is not None
        downloadables.append(
            BasicDownloadable(session, l_url, "jpg").download(
                saved_cover_path,
                lambda _: None,
            ),
        )

    _, embed_url, embed_cover_path = covers.get_size(config.embed_size)
    if embed_cover_path is None and embed:
        assert embed_url is not None
        embed_dir = os.path.join(folder, "__artwork")
        os.makedirs(embed_dir, exist_ok=True)
        _artwork_tempdirs.add(embed_dir)
        embed_cover_path = os.path.join(embed_dir, f"cover{hash(embed_url)}.jpg")
        downloadables.append(
            BasicDownloadable(session, embed_url, "jpg").download(
                embed_cover_path,
                lambda _: None,
            ),
        )

    if len(downloadables) == 0:
        return embed_cover_path, saved_cover_path

    await asyncio.gather(*downloadables)

    # Update `covers` to reflect the current download state
    if save_artwork:
        assert saved_cover_path is not None
        covers.set_largest_path(saved_cover_path)
        if config.saved_max_width > 0:
            downscale_image(saved_cover_path, config.saved_max_width)

    if embed:
        assert embed_cover_path is not None
        covers.set_path(config.embed_size, embed_cover_path)
        if config.embed_max_width > 0:
            downscale_image(embed_cover_path, config.embed_max_width)

    return embed_cover_path, saved_cover_path


def downscale_image(input_image_path: str, max_dimension: int):
    """Downscale an image in place given a maximum allowed dimension.

    Args:
    ----
        input_image_path (str): Path to image
        max_dimension (int): Maximum dimension allowed

    Returns:
    -------


    """
    # Open the image
    image = Image.open(input_image_path)

    # Get the original width and height
    width, height = image.size

    if max_dimension <= max(width, height):
        return

    # Calculate the new dimensions while maintaining the aspect ratio
    if width > height:
        new_width = max_dimension
        new_height = int(height * (max_dimension / width))
    else:
        new_height = max_dimension
        new_width = int(width * (max_dimension / height))

    # Resize the image with the new dimensions
    resized_image = image.resize((new_width, new_height))

    # Save the resized image
    resized_image.save(input_image_path)
