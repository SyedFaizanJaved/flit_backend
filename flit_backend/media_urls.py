"""Fresh pre-signed URLs for media kept in the private S3 bucket.

FileField.url already signs. This covers the values that are not a FileField: a bare
storage key from the ML service, or a full bucket URL that was saved or echoed back
(possibly carrying an old, expired signature).
"""
from urllib.parse import urlparse, unquote

from django.core.files.storage import default_storage


def media_url(value):
    """Return a freshly signed URL for `value`; non-bucket URLs pass through untouched."""
    if not value:
        return value
    value = str(value)
    if value.startswith(('http://', 'https://')):
        parsed = urlparse(value)
        bucket = getattr(default_storage, 'bucket_name', None)
        # Virtual-hosted style only (<bucket>.s3...amazonaws.com) — the style this project uses.
        if not bucket or not parsed.netloc.startswith(f'{bucket}.s3'):
            return value
        key = unquote(parsed.path)  # query string (old signature) is dropped here
    else:
        key = value
    key = key.lstrip('/')
    # default_storage.url() prepends its LOCATION ("media/"); don't double it.
    location = (getattr(default_storage, 'location', '') or '').strip('/')
    if location and key.startswith(f'{location}/'):
        key = key[len(location) + 1:]
    return default_storage.url(key)
