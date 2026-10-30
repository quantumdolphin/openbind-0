#!/usr/bin/env python3
"""Download and verify the OpenFold project's OpenBind-0 checkpoint."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from pathlib import Path
import subprocess

URL = "https://openfold3-data.s3.amazonaws.com/openfold3-parameters/of3-ob-2025-06-30-174k.pt"
NAME = "of3-ob-2025-06-30-174k.pt"
SIZE = 2_287_872_989
SHA256 = "bd43301c011d5f87580d3e8b548658869433e4488399feb03035ba248f8e29e4"
PARTS = 16
ROOT = Path(__file__).resolve().parent / "weights"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fetch(index: int, start: int, end: int) -> Path:
    target = ROOT / f"{NAME}.range-{index:02d}"
    expected = end - start + 1
    for attempt in range(30):
        completed = target.stat().st_size if target.exists() else 0
        if completed == expected:
            break
        if completed > expected:
            raise RuntimeError(f"Range {index} is too large: {completed}")
        temporary = ROOT / f"{NAME}.range-{index:02d}.transfer"
        response = subprocess.run(
            [
                "curl", "--fail", "--location", "--silent", "--show-error",
                "--connect-timeout", "30", "--max-time", "300",
                "--range", f"{start + completed}-{end}",
                "--output", str(temporary), "--write-out", "%{http_code}", URL,
            ],
            capture_output=True,
            text=True,
        )
        if response.stdout != "206":
            raise RuntimeError(
                f"Range {index} returned HTTP {response.stdout!r}: {response.stderr.strip()}"
            )
        if temporary.exists():
            with target.open("ab") as output, temporary.open("rb") as source:
                for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    output.write(block)
            temporary.unlink()
        if response.returncode != 0:
            print(f"range {index + 1}/{PARTS} retry {attempt + 1}: {response.stderr.strip()}", flush=True)
    if target.stat().st_size != expected:
        raise RuntimeError(f"Range {index} has unexpected size: {target.stat().st_size}")
    print(f"range {index + 1}/{PARTS} complete", flush=True)
    return target


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    final = ROOT / NAME
    if final.exists() and final.stat().st_size == SIZE and digest(final) == SHA256:
        print(f"Already verified: {final}")
        return
    chunk = (SIZE + PARTS - 1) // PARTS
    with ThreadPoolExecutor(max_workers=PARTS) as pool:
        futures = [
            pool.submit(fetch, index, index * chunk, min(SIZE - 1, (index + 1) * chunk - 1))
            for index in range(PARTS)
        ]
        for future in as_completed(futures):
            future.result()
    assembled = ROOT / f"{NAME}.assembling"
    with assembled.open("wb") as output:
        for index in range(PARTS):
            with (ROOT / f"{NAME}.range-{index:02d}").open("rb") as source:
                for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    output.write(block)
    if assembled.stat().st_size != SIZE or digest(assembled) != SHA256:
        raise RuntimeError("OpenBind checkpoint failed size or SHA-256 verification")
    assembled.replace(final)
    for index in range(PARTS):
        (ROOT / f"{NAME}.range-{index:02d}").unlink()
    print(f"Verified SHA-256 {SHA256}: {final}", flush=True)


if __name__ == "__main__":
    main()
