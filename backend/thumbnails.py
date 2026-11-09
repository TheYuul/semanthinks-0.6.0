"""Thumbnail download with a host allowlist, so nothing that can reach this port can make the backend fetch arbitrary addresses."""
import io, re, threading
from collections import OrderedDict
from typing import Optional
from urllib.parse import urlparse
import httpx

ALLOWED_IMAGE_HOSTS = ("ytimg.com",)


def host_allowed(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_IMAGE_HOSTS)


def _decodable(data: bytes) -> bool:
    try:
        from PIL import Image
        Image.open(io.BytesIO(data)).convert("RGB")
        return True
    except Exception:
        return False


_client = httpx.Client(timeout=5.0, follow_redirects=True, headers={"Accept": "image/jpeg,image/png,*/*;q=0.5", "User-Agent": "Mozilla/5.0"})
_cache = OrderedDict()                                           # url -> bytes or None (a few hundred small JPEGs)
_lock = threading.Lock()


def _fetch(url: str) -> Optional[bytes]:
    try:
        r = _client.get(url)
        r.raise_for_status()
        if not host_allowed(str(r.url)): return None          # a redirect must not leave the allowed hosts
        if _decodable(r.content): return r.content
        print(f"thumbnail not an image: {r.headers.get('content-type')} {len(r.content)} bytes <- {url[:90]}")
    except Exception as e:
        print(f"thumbnail fetch failed ({type(e).__name__}) <- {url[:90]}")
    return None


def download(url: str) -> Optional[bytes]:
    if not host_allowed(url): return None
    m = re.search(r"/vi(?:_webp)?/([\w-]{11})/", urlparse(url).path)
    key = m.group(1) if m else url
    with _lock:
        if key in _cache: return _cache[key]
    # YouTube answers the signed hq720 URLs with AVIF, which Pillow cannot open; the plain JPEG of the same video works.
    data = _fetch(f"https://i.ytimg.com/vi/{key}/hqdefault.jpg") if m else _fetch(url)
    if data is None and m: data = _fetch(url)
    if data is not None:                                        # failures are not cached, so they are retried
        with _lock:
            _cache[key] = data
            if len(_cache) > 400: _cache.popitem(last=False)
    return data
