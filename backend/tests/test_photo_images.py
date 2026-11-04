from io import BytesIO
import logging

import pytest
from PIL import Image, PngImagePlugin
from uvicorn.logging import AccessFormatter

from library.photo_http import PhotoAccessLogFilter
from library.photo_images import sanitize_image
from main import app
from service.auth import AuthError
from service.photos import PhotoSettings


def image_bytes(fmt='PNG', size=(16, 12), metadata=False):
    image = Image.new('RGB', size, 'red')
    output = BytesIO()
    kwargs = {}
    if metadata:
        exif = Image.Exif()
        exif[0x0112] = 6  # Rotate 90 degrees; output dimensions must follow.
        exif[0x010E] = 'private description'
        exif[0x8825] = {1: 'N', 2: (37.0, 30.0, 0.0), 3: 'E', 4: (127.0, 0.0, 0.0)}
        kwargs['exif'] = exif
        if fmt == 'PNG':
            png = PngImagePlugin.PngInfo()
            png.add_text('location', 'private location')
            kwargs['pnginfo'] = png
    image.save(output, fmt, **kwargs)
    return output.getvalue()


@pytest.mark.parametrize('fmt,mime', [('JPEG', 'image/jpeg'), ('PNG', 'image/png'), ('WEBP', 'image/webp')])
def test_sanitized_pixels_and_orientation_without_metadata(fmt, mime):
    raw = image_bytes(fmt, metadata=True)
    result = sanitize_image(raw, 10 * 1024 * 1024, 24000000)
    assert result.content_type == mime
    assert (result.width, result.height) == (12, 16)
    with Image.open(BytesIO(result.content)) as clean:
        clean.load()
        assert not clean.getexif()
        assert not any(key in clean.info for key in ('exif', 'icc_profile', 'location', 'comment'))
        assert clean.size == (12, 16)


@pytest.mark.parametrize('raw', [b'', b'<html>not an image</html>', b'\xff\xd8\xffbroken'])
def test_invalid_images(raw):
    with pytest.raises(AuthError) as error:
        sanitize_image(raw, 1024, 1000)
    assert (error.value.status, error.value.code) == (422, 'INVALID_IMAGE')


def test_input_size_boundaries_and_pixel_limit():
    raw = image_bytes('JPEG')
    assert sanitize_image(raw, len(raw), 192).width == 16
    for max_bytes, max_pixels, status in ((len(raw)-1, 192, 413), (len(raw), 191, 422)):
        with pytest.raises(AuthError) as error:
            sanitize_image(raw, max_bytes, max_pixels)
        assert error.value.status == status


def test_animated_image_is_rejected():
    out = BytesIO()
    with Image.new('RGB', (8, 8), 'red') as first, Image.new('RGB', (8, 8), 'blue') as second:
        first.save(out, 'WEBP', save_all=True, append_images=[second], duration=100, loop=0)
    with pytest.raises(AuthError) as error:
        sanitize_image(out.getvalue(), 1024 * 1024, 1000)
    assert error.value.code == 'INVALID_IMAGE'


def test_access_tokens_redacted_without_breaking_uvicorn_formatter():
    token = 'secret-access-token'
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 1,
        '%s - "%s %s HTTP/%s" %d', ('127.0.0.1', 'GET', f'/api/v1/photo-access/{token}', '1.1', 200), None)
    PhotoAccessLogFilter().filter(record)
    rendered = AccessFormatter('%(message)s').format(record)
    assert token not in rendered
    assert '[redacted]' in rendered


def test_openapi_photo_contracts_and_safe_origin():
    paths = app.openapi()['paths']
    assert 'multipart/form-data' in paths['/api/v1/photos']['post']['requestBody']['content']
    assert 'requestBody' not in paths['/api/v1/photos/{photoId}/access-url']['post']
    assert set(paths['/api/v1/photo-access/{accessToken}']['get']['responses']['200']['content']) == {
        'image/jpeg', 'image/png', 'image/webp'}
    with pytest.raises(ValueError):
        PhotoSettings(public_base_url='http://untrusted.test')
