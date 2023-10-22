import asyncio
import os

import aiohttp
from PIL import Image

from .config import ArtworkConfig
from .downloadable import BasicDownloadable
from .metadata import Covers


async def download_artwork(
    session: aiohttp.ClientSession, folder: str, covers: Covers, config: ArtworkConfig
) -> tuple[str | None, str | None]:
    """Download artwork, which may include a seperate file to keep.
    Also updates the passed Covers object with downloaded filepaths.

    Because it is a single, we will assume that none of the covers have already been
    downloaded, so existing paths in `covers` will be discarded and overwritten.

    Args:
        covers (Covers): The set of available covers.

    Returns:
        The path of the cover to embed, or None if there either is no artwork available or
        if artwork embedding is turned off.
    """
    if (not config.save_artwork and not config.embed) or covers.empty():
        # No need to download anything
        return None, None

    downloadables = []

    saved_cover_path = None
    if config.save_artwork:
        _, l_url, _ = covers.largest()
        assert l_url is not None  # won't be true unless covers is empty
        saved_cover_path = os.path.join(folder, "cover.jpg")
        downloadables.append(
            BasicDownloadable(session, l_url, "jpg").download(
                saved_cover_path, lambda _: None
            )
        )

    embed_cover_path = None
    if config.embed:
        _, embed_url, _ = covers.get_size(config.embed_size)
        assert embed_url is not None
        embed_cover_path = os.path.join(folder, "embed_cover.jpg")
        downloadables.append(
            BasicDownloadable(session, embed_url, "jpg").download(
                embed_cover_path, lambda _: None
            )
        )

    await asyncio.gather(*downloadables)

    # Update `covers` to reflect the current download state
    if config.save_artwork:
        assert saved_cover_path is not None
        covers.set_largest_path(saved_cover_path)
        if config.saved_max_width > 0:
            downscale_image(saved_cover_path, config.saved_max_width)

    if config.embed:
        assert embed_cover_path is not None
        covers.set_path(config.embed_size, embed_cover_path)
        if config.embed_max_width > 0:
            downscale_image(embed_cover_path, config.embed_max_width)

    return embed_cover_path, saved_cover_path


def downscale_image(input_image_path: str, max_dimension: int):
    """Downscale an image in place given a maximum allowed dimension.

    Args:
        input_image_path (str): Path to image
        max_dimension (int): Maximum dimension allowed

    Returns:


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
