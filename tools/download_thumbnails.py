"""
download_thumbnails.py - downloads the YouTube thumbnails that dataset_clean.csv / training.csv refer to.

    python tools/download_thumbnails.py data/clean/training.csv --out thumbnails [--workers 16] [--limit N]

Reads `image_path` (file name) and, from the cleaned dataset, `image_url`. Only https://i.ytimg.com/ URLs are fetched (the extension and
the backend use the same allowlist). Already downloaded files are skipped, so the script can be re-run. Failures are listed in
<out>/failed.txt; rows whose thumbnail is missing are treated as text-only by extract_features.py, which is fine.
"""
import argparse, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd

ALLOWED_PREFIX = "https://i.ytimg.com/"


def readable(data: bytes) -> bool:
    """JPEG, PNG or WebP. YouTube sometimes answers with AVIF, which Pillow cannot open."""
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "semanthinks-dataset-builder", "Accept": "image/jpeg,image/png,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch(url, dest, timeout=15):
    try:
        data = _get(url, timeout)
        if not readable(data):                                   # same video, plain JPEG thumbnail
            m = re.search(r"/vi(?:_webp)?/([\w-]{11})/", url)
            if m: data = _get(f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg", timeout)
        if len(data) < 500: return "too small"
        if not readable(data): return "not a readable image format"
        dest.write_bytes(data); return None
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:80]}"


def jobs(df, out, allowed=ALLOWED_PREFIX):
    seen = set(); todo = []
    for _, r in df.iterrows():
        path, url = (r.get("image_path") or "").strip(), (r.get("image_url") or "").strip()
        if not path or not url or path in seen: continue
        seen.add(path)
        if not url.startswith(allowed): continue
        if (out / path).exists() and readable((out / path).read_bytes()[:16]): continue   # re-fetch files that are not readable
        todo.append((url, out / path))
    return todo


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("csv"); ap.add_argument("--out", default="thumbnails"); ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--clean", default="data/clean/dataset_clean.csv", help="source of image_url when the CSV has none")
    a = ap.parse_args()
    df = pd.read_csv(a.csv, dtype=str, keep_default_na=False)
    if "image_url" not in df.columns:
        urls = pd.read_csv(a.clean, dtype=str, keep_default_na=False).set_index("id")["image_url"]
        df["image_url"] = [urls.get(str(i).split("#")[0].split("~")[0], "") for i in df["id"]]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    todo = jobs(df, out)
    if a.limit: todo = todo[:a.limit]
    print(f"{len(todo)} thumbnails to download into {out}/")
    failed = []
    with ThreadPoolExecutor(a.workers) as ex:
        for n, ((url, dest), err) in enumerate(zip(todo, ex.map(lambda j: fetch(*j), todo)), 1):
            if err: failed.append(f"{dest.name}\t{err}")
            if n % 500 == 0: print(f"{n}/{len(todo)} ({len(failed)} failed)")
    (out / "failed.txt").write_text("\n".join(failed))
    print(f"done: {len(todo) - len(failed)} downloaded, {len(failed)} failed (see {out}/failed.txt)")


if __name__ == "__main__":
    main()
