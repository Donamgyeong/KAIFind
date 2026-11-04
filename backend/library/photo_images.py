"""Decode and re-encode only pixel data, never retain source metadata."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from service.auth import AuthError


@dataclass(frozen=True)
class SanitizedImage:
    content: bytes
    content_type: str
    width: int
    height: int


def sanitize_image(content: bytes, max_bytes: int, max_pixels: int) -> SanitizedImage:
    if len(content) > max_bytes:
        raise AuthError(413, 'PHOTO_TOO_LARGE')

    try:
        # Identify first, check dimensions before allocation, then fully decode.
        with Image.open(BytesIO(content), formats=('JPEG', 'PNG', 'WEBP')) as image:
            fmt = image.format
            if image.width * image.height > max_pixels:
                raise AuthError(422, 'INVALID_IMAGE')
            if getattr(image, 'n_frames', 1) != 1:
                raise AuthError(422, 'INVALID_IMAGE')

            image.load()
            oriented = ImageOps.exif_transpose(image)
            mode = 'RGB' if fmt == 'JPEG' else 'RGBA'
            converted = oriented.convert(mode)

            # A fresh image prevents EXIF, ICC, comments and PNG text propagation.
            with Image.new(mode, converted.size) as clean:
                clean.paste(converted)
                output = BytesIO()
                clean.save(output, format=fmt)
                result = SanitizedImage(
                    output.getvalue(),
                    {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}[fmt],
                    clean.width,
                    clean.height,
                )

            converted.close()
            oriented.close()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError):
        raise AuthError(422, 'INVALID_IMAGE') from None

    if len(result.content) > max_bytes:
        raise AuthError(413, 'PHOTO_TOO_LARGE')

    return result
