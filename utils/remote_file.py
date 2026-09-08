"""What we accept as a CV / company document, and how we fetch one from a URL.

`document_upload_error` is the size and type rule for direct uploads, shared by the
resume-parse and company-extract endpoints.

`fetch_remote_file` covers the other half: the candidate may paste a link to their CV
instead of uploading it. That URL comes from the browser, so it is an SSRF sink --
without the address check below, a candidate could point us at internal services or the
EC2 instance metadata endpoint and have us fetch them from inside the VPC.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import requests

MAX_BYTES = 10 * 1024 * 1024  # matches the 10MB cap the profile form enforces
TIMEOUT_SECONDS = 20
MAX_REDIRECTS = 3

# No .doc / application/msword. The parser service rejects legacy Word outright --
# "Unsupported file type '.doc'. Allowed types: .pdf ... .docx ..." -- so accepting it
# here only buys the user a long upload that is guaranteed to fail downstream.
DOCUMENT_CONTENT_TYPES = frozenset({
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
})
DOCUMENT_EXTENSIONS = ('.pdf', '.docx')

ALLOWED_CONTENT_TYPES = DOCUMENT_CONTENT_TYPES | {
    'application/octet-stream',  # S3 and Drive serve CVs as this often enough to allow
}


def document_upload_error(filename, size, content_type):
    """Why this uploaded CV / company document is unacceptable, or None.

    The PDF/DOCX + 10MB rule both intake forms advertise, enforced server-side
    because `accept=` on a file input is a picker filter, not a check -- drag-and-drop
    and a switched file-type dropdown both walk straight past it, and nothing stops a
    caller hitting the endpoint directly.

    The extension decides. Browsers disagree on the MIME type for .doc/.docx and some
    send an empty one or `application/octet-stream`, so the type is consulted only when
    the name carries no extension we recognise -- and octet-stream is deliberately not
    proof of anything here, unlike the remote-fetch path where it is all S3 gives us.
    """
    if size > MAX_BYTES:
        return "That file is larger than 10MB."
    if (filename or '').lower().endswith(DOCUMENT_EXTENSIONS):
        return None
    if content_type in DOCUMENT_CONTENT_TYPES:
        return None
    return "Only PDF and DOCX files can be uploaded."


class RemoteFileError(Exception):
    """The URL could not be fetched, or was not something we are willing to fetch."""


def _assert_public_host(url):
    """Reject anything that resolves to a non-public address.

    Checks every address the host resolves to, not just the first: a hostname with both
    a public and a private A record would otherwise slip through.
    """
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise RemoteFileError("Only https URLs are accepted.")
    if not parsed.hostname:
        raise RemoteFileError("URL has no host.")

    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise RemoteFileError("Could not resolve the host in that URL.")

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise RemoteFileError("That URL points to a non-public address.")


def fetch_remote_file(url):
    """Download `url` and return (filename, bytes, content_type).

    Raises RemoteFileError for anything we refuse or cannot fetch. Callers should treat
    that as a 400 -- it is nearly always a bad link from the candidate, not our fault.
    """
    # ponytail: re-resolving between this check and the request leaves a TOCTOU window.
    # Closing it means connecting to the vetted IP with an explicit Host header and
    # custom TLS verification; worth doing if this ever fetches anything sensitive, but
    # the payload here goes straight to a parser and is never echoed back to the caller.
    for _ in range(MAX_REDIRECTS + 1):
        _assert_public_host(url)
        try:
            response = requests.get(
                url, stream=True, timeout=TIMEOUT_SECONDS, allow_redirects=False
            )
        except requests.exceptions.RequestException as e:
            raise RemoteFileError(f"Could not fetch that URL: {e}")

        # Follow redirects by hand so each hop gets the address check above; letting
        # requests follow them internally would skip it.
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get('Location')
            response.close()
            if not location:
                raise RemoteFileError("That URL redirected without a destination.")
            url = requests.compat.urljoin(url, location)
            continue
        break
    else:
        raise RemoteFileError("That URL redirected too many times.")

    with response:
        if response.status_code != 200:
            raise RemoteFileError(f"That URL returned HTTP {response.status_code}.")

        content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip()
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            raise RemoteFileError(f"Unsupported file type: {content_type or 'unknown'}.")

        # Read with a running cap rather than trusting Content-Length, which a hostile
        # or merely wrong server can understate.
        chunks, total = [], 0
        for chunk in response.iter_content(64 * 1024):
            total += len(chunk)
            if total > MAX_BYTES:
                raise RemoteFileError("That file is larger than 10MB.")
            chunks.append(chunk)

    if not total:
        raise RemoteFileError("That URL returned an empty file.")

    filename = (urlparse(url).path.rsplit('/', 1)[-1] or 'resume.pdf')
    return filename, b''.join(chunks), content_type or 'application/octet-stream'


def demo():
    """Self-check for the address guard and the upload rule."""
    ok = (None,)
    cases = [
        # (filename, size, content_type) -> accepted?
        (('cv.pdf', 1000, 'application/pdf'), True),
        (('cv.PDF', 1000, 'application/pdf'), True),           # case-insensitive
        (('cv.doc', 1000, 'application/msword'), False),  # parser rejects legacy Word
        (('cv.docx', 1000, ''), True),                          # browser sent no type
        (('cv.docx', 1000, 'application/octet-stream'), True),  # ... or a useless one
        (('resume', 1000, 'application/pdf'), True),            # no extension, type says PDF
        (('cv.exe', 1000, 'application/x-msdownload'), False),
        (('cv.png', 1000, 'image/png'), False),
        (('cv.pdf.exe', 1000, 'application/pdf'), True),        # type still vouches for it
        (('resume', 1000, 'application/octet-stream'), False),  # nothing vouches for it
        (('', 1000, ''), False),
        ((None, 1000, None), False),
        (('cv.pdf', MAX_BYTES + 1, 'application/pdf'), False),  # size beats type
        (('cv.pdf', MAX_BYTES, 'application/pdf'), True),       # exactly at the cap
    ]
    for args, accepted in cases:
        error = document_upload_error(*args)
        assert (error is None) is accepted, (args, error)
    assert 'larger than 10MB' in document_upload_error('cv.pdf', MAX_BYTES + 1, 'application/pdf')
    assert 'PDF and DOCX' in document_upload_error('cv.exe', 10, 'application/x-msdownload')

    blocked = [
        'https://localhost/cv.pdf',
        'https://127.0.0.1/cv.pdf',
        'https://169.254.169.254/latest/meta-data/',  # EC2 instance metadata
        'https://10.0.0.5/cv.pdf',
        'https://192.168.1.1/cv.pdf',
        'http://example.com/cv.pdf',                  # not https
    ]
    for url in blocked:
        try:
            _assert_public_host(url)
        except RemoteFileError:
            continue
        raise AssertionError(f"should have been rejected: {url}")

    _assert_public_host('https://example.com/cv.pdf')  # public host must pass
    print("remote_file guard OK")


if __name__ == '__main__':
    demo()
