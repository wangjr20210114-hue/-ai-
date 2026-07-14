"""Download and import China extracts one region at a time, then delete each PBF."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen


BASE_URL = "https://download.geofabrik.de/asia/china"

# Hebei includes Beijing and Tianjin; Guangdong includes Hong Kong and Macau.
# Omitting the overlapping standalone extracts saves bandwidth and avoids duplicate work.
DEFAULT_REGIONS = (
    "anhui", "chongqing", "fujian", "gansu", "guangdong", "guangxi", "guizhou",
    "hainan", "hebei", "heilongjiang", "henan", "hubei", "hunan", "inner-mongolia",
    "jiangsu", "jiangxi", "jilin", "liaoning", "ningxia", "qinghai", "shaanxi",
    "shandong", "shanghai", "shanxi", "sichuan", "tibet", "xinjiang", "yunnan",
    "zhejiang",
)

EXTRA_REGIONS = ("beijing", "tianjin", "hong-kong", "macau")
ALLOWED_REGIONS = frozenset(DEFAULT_REGIONS + EXTRA_REGIONS)


def download(url: str, destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "yuanbao-place-importer/1.0"})
    with urlopen(request, timeout=120) as response, partial.open("wb") as target:
        total = int(response.headers.get("Content-Length") or 0)
        copied = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            target.write(chunk)
            copied += len(chunk)
            if copied and copied % (50 * 1024 * 1024) < len(chunk):
                print(f"downloaded={copied // (1024 * 1024)}MB total={total // (1024 * 1024)}MB", flush=True)
    partial.replace(destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regions", nargs="*", default=list(DEFAULT_REGIONS))
    parser.add_argument("--work-dir", default="/work")
    parser.add_argument("--batch-size", type=int, default=3000)
    parser.add_argument("--keep-downloads", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="skip regions recorded as completed in the persistent work directory")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=int, default=15)
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    invalid = sorted(set(args.regions) - ALLOWED_REGIONS)
    if invalid:
        raise SystemExit(f"unsupported regions: {', '.join(invalid)}")
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    progress_path = work_dir / "china-import-completed.txt"
    completed = {
        line.strip() for line in progress_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    } if args.resume and progress_path.exists() else set()
    failures: list[str] = []
    for index, region in enumerate(args.regions, start=1):
        if region in completed:
            print(f"region={region} step={index}/{len(args.regions)} skipped=completed", flush=True)
            continue
        path = work_dir / f"{region}-latest.osm.pbf"
        url = f"{BASE_URL}/{region}-latest.osm.pbf"
        print(f"region={region} step={index}/{len(args.regions)}", flush=True)
        succeeded = False
        for attempt in range(1, max(1, args.retries) + 1):
            try:
                if not path.exists():
                    download(url, path)
                subprocess.run(
                    [sys.executable, "/importer/import_osm.py", str(path), "--region", region,
                     "--country-code", "cn", "--batch-size", str(max(100, args.batch_size))],
                    check=True,
                )
                succeeded = True
                break
            except Exception as exc:
                print(f"region={region} attempt={attempt}/{max(1, args.retries)} failed={exc}",
                      file=sys.stderr, flush=True)
                if attempt < max(1, args.retries):
                    time.sleep(max(0, min(args.retry_delay, 60)))
        if succeeded:
            if not args.keep_downloads:
                path.unlink(missing_ok=True)
                print(f"deleted={path.name}", flush=True)
            if args.resume:
                completed.add(region)
                progress_path.write_text("\n".join(sorted(completed)) + "\n", encoding="utf-8")
        else:
            failures.append(region)
            if args.stop_on_error:
                break

    print(f"complete regions={len(args.regions) - len(failures)} failed={len(failures)}", flush=True)
    if failures:
        raise SystemExit(f"failed regions: {', '.join(failures)}")


if __name__ == "__main__":
    main()
