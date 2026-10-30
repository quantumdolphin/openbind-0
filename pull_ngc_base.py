#!/usr/bin/env python3
"""Resumable parallel pull of the pinned NVIDIA ARM64 PyTorch base image."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import threading
import time

import requests

ROOT = Path(__file__).resolve().parent / "ngc-transfer"
BLOBS = ROOT / "blobs" / "sha256"
REPO = "nvidia/pytorch"
TAG = "25.11-py3"
MANIFEST_SHA = "4a85d8cf6fb3a943280960b8948cf4e9b6eca77b4414c68c9b2c7bb863f79b70"
CHUNK_SIZE = 64 * 1024 * 1024
WORKERS = 48
_token = ""
_token_expires = 0.0
_token_lock = threading.Lock()


def token() -> str:
    global _token, _token_expires
    with _token_lock:
        if time.time() < _token_expires:
            return _token
        response = requests.get(
            "https://nvcr.io/proxy_auth",
            params={"service": "registry", "scope": f"repository:{REPO}:pull"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        _token = data["token"]
        _token_expires = time.time() + min(int(data.get("expires_in", 300)), 300) - 30
        return _token


def registry_get(kind: str, digest: str) -> bytes:
    response = requests.get(
        f"https://nvcr.io/v2/{REPO}/{kind}/{digest}",
        headers={"Authorization": f"Bearer {token()}", "Accept": "application/vnd.docker.distribution.manifest.v2+json"},
        timeout=(30, 120),
    )
    response.raise_for_status()
    body = response.content
    if hashlib.sha256(body).hexdigest() != digest.split(":", 1)[1]:
        raise RuntimeError(f"Digest mismatch for {kind} {digest}")
    return body


def fetch_chunk(digest: str, offset: int, end: int, total: int) -> Path:
    name = digest.split(":", 1)[1]
    destination = ROOT / "chunks" / f"{name}.{offset:012d}"
    expected = end - offset + 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(40):
        complete = destination.stat().st_size if destination.exists() else 0
        if complete == expected:
            return destination
        if complete > expected:
            raise RuntimeError(f"Chunk too large: {destination}")
        try:
            with requests.get(
                f"https://nvcr.io/v2/{REPO}/blobs/{digest}",
                headers={"Authorization": f"Bearer {token()}", "Range": f"bytes={offset + complete}-{end}"},
                stream=True,
                timeout=(30, 90),
            ) as response:
                if response.status_code == 401:
                    global _token_expires
                    _token_expires = 0
                    continue
                response.raise_for_status()
                expected_range = f"bytes {offset + complete}-{end}/{total}"
                if response.status_code != 206 or response.headers.get("Content-Range") != expected_range:
                    raise RuntimeError(f"Unexpected range response: {response.status_code} {response.headers.get('Content-Range')}")
                with destination.open("ab") as output:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if block:
                            output.write(block)
        except (requests.RequestException, OSError) as error:
            print(f"Retry {attempt + 1} for {name[:12]} at {offset}: {error}", flush=True)
            time.sleep(min(attempt + 1, 10))
    raise RuntimeError(f"Could not finish chunk {destination}")


def assemble_blob(descriptor: dict) -> Path:
    digest = descriptor["digest"]
    name = digest.split(":", 1)[1]
    total = descriptor["size"]
    final = BLOBS / name
    if final.exists() and final.stat().st_size == total:
        with final.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == name:
                return final
    assembling = BLOBS / f"{name}.assembling"
    value = hashlib.sha256()
    with assembling.open("wb") as output:
        for offset in range(0, total, CHUNK_SIZE):
            chunk = ROOT / "chunks" / f"{name}.{offset:012d}"
            with chunk.open("rb") as source:
                for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    value.update(block)
                    output.write(block)
    if assembling.stat().st_size != total or value.hexdigest() != name:
        raise RuntimeError(f"Layer digest mismatch: {digest}")
    assembling.replace(final)
    for offset in range(0, total, CHUNK_SIZE):
        (ROOT / "chunks" / f"{name}.{offset:012d}").unlink()
    return final


def load_image(manifest: dict) -> None:
    config = manifest["config"]
    layers = manifest["layers"]
    oci_manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": config["digest"], "size": config["size"]},
        "layers": [
            {"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": item["digest"], "size": item["size"]}
            for item in layers
        ],
    }
    encoded = json.dumps(oci_manifest, separators=(",", ":")).encode()
    oci_digest = hashlib.sha256(encoded).hexdigest()
    (BLOBS / oci_digest).write_bytes(encoded)
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [{
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": "sha256:" + oci_digest,
            "size": len(encoded),
            "platform": {"architecture": "arm64", "os": "linux"},
            "annotations": {
                "io.containerd.image.name": f"nvcr.io/{REPO}:{TAG}",
                "org.opencontainers.image.ref.name": TAG,
            },
        }],
    }
    docker_manifest = [{
        "Config": "blobs/sha256/" + config["digest"].split(":", 1)[1],
        "RepoTags": [f"nvcr.io/{REPO}:{TAG}"],
        "Layers": ["blobs/sha256/" + item["digest"].split(":", 1)[1] for item in layers],
        "LayerSources": {item["digest"]: item for item in oci_manifest["layers"]},
    }]
    (ROOT / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    (ROOT / "manifest.json").write_text(json.dumps(docker_manifest, separators=(",", ":")))
    (ROOT / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}')
    print("All NVIDIA layer digests verified. Loading image into Docker...", flush=True)
    with tempfile.TemporaryFile(mode="w+b") as log:
        process = subprocess.Popen(["docker", "load"], stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
        try:
            with tarfile.open(fileobj=process.stdin, mode="w|") as archive:
                for name in ("oci-layout", "index.json", "manifest.json"):
                    archive.add(ROOT / name, arcname=name)
                archive.add(BLOBS, arcname="blobs/sha256")
        finally:
            process.stdin.close()
        if process.wait() != 0:
            log.seek(0)
            raise RuntimeError("docker load failed: " + log.read().decode(errors="replace")[-1000:])
        log.seek(0)
        print(log.read().decode(errors="replace")[-500:], flush=True)
    loaded_id = subprocess.check_output(
        ["docker", "image", "inspect", f"nvcr.io/{REPO}:{TAG}", "--format", "{{.Id}}"],
        text=True,
    ).strip()
    if loaded_id != config["digest"]:
        raise RuntimeError(f"Loaded image ID {loaded_id} does not match pinned config {config['digest']}")
    print(f"Verified Docker image ID: {loaded_id}", flush=True)


def main() -> None:
    BLOBS.mkdir(parents=True, exist_ok=True)
    manifest_bytes = registry_get("manifests", "sha256:" + MANIFEST_SHA)
    manifest = json.loads(manifest_bytes)
    (BLOBS / MANIFEST_SHA).write_bytes(manifest_bytes)
    config = manifest["config"]
    (BLOBS / config["digest"].split(":", 1)[1]).write_bytes(registry_get("blobs", config["digest"]))
    descriptors = list({item["digest"]: item for item in manifest["layers"]}.values())
    print(f"Pinned image: {len(descriptors)} unique layers, {sum(x['size'] for x in descriptors) / 1e9:.2f} GB compressed", flush=True)
    tasks = []
    for item in descriptors:
        final = BLOBS / item["digest"].split(":", 1)[1]
        if final.exists() and final.stat().st_size == item["size"]:
            with final.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == item["digest"].split(":", 1)[1]:
                    continue
        for offset in range(0, item["size"], CHUNK_SIZE):
            tasks.append((item["digest"], offset, min(item["size"] - 1, offset + CHUNK_SIZE - 1), item["size"]))
    print(f"Downloading {len(tasks)} resumable ranges with {WORKERS} connections", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch_chunk, *task) for task in tasks]
        for count, future in enumerate(as_completed(futures), 1):
            future.result()
            if count % 10 == 0 or count == len(futures):
                print(f"Ranges complete: {count}/{len(futures)}", flush=True)
    for count, item in enumerate(descriptors, 1):
        assemble_blob(item)
        if count % 10 == 0 or count == len(descriptors):
            print(f"Verified layers: {count}/{len(descriptors)}", flush=True)
    load_image(manifest)


if __name__ == "__main__":
    main()
