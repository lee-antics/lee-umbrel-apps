"""Bump lee-tofa to the newest Tofa release published on ghcr.io.

Looks at ghcr.io/tofatv/tofa for the highest X.Y.Z tag. If it is newer than
the version in lee-tofa/umbrel-app.yml, pins the compose image to that tag
and digest and raises the app version, which makes umbrelOS offer an update.
Prints the new version, or nothing when already up to date.
"""

import json
import re
import urllib.request
from pathlib import Path

REPO = "tofatv/tofa"
APP_DIR = Path(__file__).resolve().parents[2] / "lee-tofa"
MANIFEST = APP_DIR / "umbrel-app.yml"
COMPOSE = APP_DIR / "docker-compose.yml"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])


def get(url, token=None, method="GET"):
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", ACCEPT)
    return urllib.request.urlopen(req, timeout=30)


def version_key(tag):
    return tuple(int(part) for part in SEMVER.match(tag).groups())


def main():
    token = json.load(get(f"https://ghcr.io/token?scope=repository:{REPO}:pull"))["token"]
    tags = json.load(get(f"https://ghcr.io/v2/{REPO}/tags/list?n=1000", token))["tags"]
    latest = max((t for t in tags if SEMVER.match(t)), key=version_key)

    manifest = MANIFEST.read_text()
    current = re.search(r'^version: "([^"]+)"$', manifest, re.M).group(1)
    if SEMVER.match(current) and version_key(latest) <= version_key(current):
        return

    digest = get(f"https://ghcr.io/v2/{REPO}/manifests/{latest}", token, "HEAD").headers["Docker-Content-Digest"]

    compose = COMPOSE.read_text()
    compose = re.sub(r"image: ghcr\.io/tofatv/tofa:\S+", f"image: ghcr.io/{REPO}:{latest}@{digest}", compose)
    COMPOSE.write_text(compose)

    manifest = re.sub(r'^version: "[^"]+"$', f'version: "{latest}"', manifest, flags=re.M)
    manifest = re.sub(r"^releaseNotes: .*$", f"releaseNotes: Tofa {latest}.", manifest, flags=re.M)
    MANIFEST.write_text(manifest)

    print(latest)


if __name__ == "__main__":
    main()
