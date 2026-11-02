import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


def process_profile_image(file_stream, max_size=(800, 800), quality=80):
    """Strip EXIF metadata, downsize proportionally, and return a WebP stream."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file_stream) as source:
                image = ImageOps.exif_transpose(source)
                if image.mode in ("RGBA", "P"):
                    image = image.convert("RGB")
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                output_buffer = io.BytesIO()
                image.save(output_buffer, format="WEBP", quality=quality, optimize=True)
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise ValueError("Choose a valid JPG, PNG, or WebP image.") from error
    output_buffer.seek(0)
    return output_buffer
