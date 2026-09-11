import io

import pillow_heif
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from companies.serializers import CompanyUpdateSerializer, SanitizedImageField


def _upload(name, fmt, mode='RGB'):
    buf = io.BytesIO()
    # ICNS/ICO only store square icon sizes
    img = Image.new(mode, (64, 64) if fmt in ('ICNS', 'ICO') else (40, 30), 'red')
    if fmt == 'HEIF':
        pillow_heif.from_pillow(img).save(buf, format='HEIF')
    else:
        img.save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue())


# SimpleTestCase: no DB, so this never touches the shared remote test database.
class GalleryImageFormatTests(SimpleTestCase):
    def test_mac_formats_are_accepted_and_stored_browser_viewable(self):
        cases = [
            # iPhone camera / Mac Photos & Preview exports
            ('IMG_0001.HEIC', 'HEIF', 'RGB', 'JPEG'),
            ('photo.heif', 'HEIF', 'RGB', 'JPEG'),
            ('scan.tiff', 'TIFF', 'RGBA', 'PNG'),
            ('scan.tif', 'TIFF', 'RGB', 'JPEG'),
            ('export.jp2', 'JPEG2000', 'RGB', 'JPEG'),
            ('AppIcon.icns', 'ICNS', 'RGBA', 'PNG'),
            ('favicon.ico', 'ICO', 'RGBA', 'PNG'),
            # already browser-viewable: stored as-is
            ('Screenshot.PNG', 'PNG', 'RGBA', 'PNG'),
            ('IMG_0002.JPG', 'JPEG', 'RGB', 'JPEG'),
            ('pic.jpeg', 'JPEG', 'RGB', 'JPEG'),
            ('pic.webp', 'WEBP', 'RGB', 'WEBP'),
            ('pic.avif', 'AVIF', 'RGB', 'AVIF'),
            ('anim.gif', 'GIF', 'P', 'GIF'),
            ('old.bmp', 'BMP', 'RGB', 'BMP'),
        ]
        for name, fmt, mode, stored in cases:
            with self.subTest(name=name):
                result = SanitizedImageField().run_validation(_upload(name, fmt, mode))
                result.seek(0)
                with Image.open(result) as img:
                    self.assertEqual(img.format, stored)
                if stored != fmt:
                    self.assertTrue(result.name.endswith('.jpg' if stored == 'JPEG' else '.png'))

    def test_non_image_still_rejected(self):
        serializer = CompanyUpdateSerializer(
            data={'uploaded_images': [SimpleUploadedFile('fake.heic', b'not an image')]}, partial=True,
        )
        self.assertFalse(serializer.is_valid())
        # ListField child errors are keyed by index: {'uploaded_images': {0: [...]}}
        self.assertIn('Upload a valid image', str(serializer.errors['uploaded_images']))
