"""Shared ML-service calls that both jobs and projects need.

Lives here rather than being copied into JobMLMixin and ProjectMLMixin: the two
already drifted apart once (the projects list filter fell behind the jobs one), and
a delete that behaves differently per entity is exactly the kind of divergence that
is invisible until the vector store is wrong.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ML_DELETE_TIMEOUT = 30


def delete_from_ml_index(path):
    """DELETE {FLIT_AI_URL}{path}. Returns (ok: bool, error: str | None).

    404 counts as success -- "not in the index" is the state we are asking for, and a
    posting closed before this call existed was never indexed under a live id anyway.
    Never raises: callers close the row first, and a failed notify must not roll that
    back or stop the sweep.
    """
    url = f"{settings.FLIT_AI_URL}{path}"
    try:
        response = requests.delete(url, timeout=ML_DELETE_TIMEOUT)
    except requests.exceptions.RequestException as e:
        return False, f"ML delete request failed: {e}"

    if response.status_code in (200, 202, 204, 404):
        return True, None
    return False, f"ML delete error: {response.status_code}"
