from PIL import Image


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
