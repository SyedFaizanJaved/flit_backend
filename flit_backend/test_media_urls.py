"""Signing is computed locally by boto3: no network, no database."""
from urllib.parse import urlparse, parse_qs

from django.core.files.storage import default_storage
from django.test import SimpleTestCase

from flit_backend.media_urls import media_url

KEY = "candidates/resumes/cv.pdf"


def parts(url):
    p = urlparse(url)
    return p.path, parse_qs(p.query)


class MediaUrlTests(SimpleTestCase):
    def test_file_urls_are_signed_and_expire(self):
        path, qs = parts(default_storage.url(KEY))
        self.assertEqual(path, f"/{KEY}")
        self.assertIn("X-Amz-Signature", qs)
        self.assertEqual(qs["X-Amz-Expires"], [str(default_storage.querystring_expire)])

    def test_bare_key_is_signed(self):
        path, qs = parts(media_url(KEY))
        self.assertEqual(path, f"/{KEY}")
        self.assertIn("X-Amz-Signature", qs)

    def test_stale_bucket_url_is_resigned_not_reused(self):
        host = urlparse(default_storage.url(KEY)).netloc
        stale = f"https://{host}/{KEY}?X-Amz-Signature=dead&X-Amz-Expires=1"
        path, qs = parts(media_url(stale))
        self.assertEqual(path, f"/{KEY}")
        self.assertNotEqual(qs["X-Amz-Signature"], ["dead"])

    def test_foreign_and_empty_values_pass_through(self):
        self.assertEqual(media_url("https://example.com/a.png"), "https://example.com/a.png")
        self.assertIsNone(media_url(None))
        self.assertEqual(media_url(""), "")
