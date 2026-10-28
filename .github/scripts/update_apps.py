"""Bump each app in this store to the newest release of its upstream images.

For every app in APPS, looks up the highest X.Y.Z tag of its first image. If
that is newer than the version in the app's umbrel-app.yml and every image of
the app has the tag, pins each compose image to that tag and its digest and
raises the app version, which makes umbrelOS offer an update. Prints one
"<Name> <version>" line per bumped app, or nothing when all are up to date.

An app version may carry a package revision (X.Y.Z-N) for changes to the
package that don't change the upstream release; umbrelOS offers an update
whenever the version text changes. Only the X.Y.Z part is compared with
upstream releases.
"""

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# App folder -> display name and its images, as written in docker-compose.yml.
# All images of an app are released together under the same version tag.
APPS = {
    "lee-tofa": ("Tofa", ["ghcr.io/tofatv/tofa"]),
    "lee-beszel": ("Beszel", ["henrygd/beszel", "henrygd/beszel-agent-intel"]),
}
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
APP_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-\d+)?$")
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


class Registry:
    """Anonymous pull access to one image repository."""

    def __init__(self, image):
        host, _, repo = image.partition("/")
        if host == "ghcr.io":
            self.api = "https://ghcr.io/v2"
            token_url = f"https://ghcr.io/token?scope=repository:{repo}:pull"
        else:  # Docker Hub
            repo = image
            self.api = "https://registry-1.docker.io/v2"
            token_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
        self.repo = repo
        self.token = json.load(get(token_url))["token"]

    def tags(self):
        return json.load(get(f"{self.api}/{self.repo}/tags/list?n=1000", self.token))["tags"]

    def digest(self, tag):
        """The tag's manifest digest, or None if the tag doesn't exist."""
        try:
            resp = get(f"{self.api}/{self.repo}/manifests/{tag}", self.token, "HEAD")
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            raise
        return resp.headers["Docker-Content-Digest"]


def version_key(version):
    return tuple(int(part) for part in APP_VERSION.match(version).groups())


def update(app_dir, name, images):
    manifest_path = ROOT / app_dir / "umbrel-app.yml"
    compose_path = ROOT / app_dir / "docker-compose.yml"
    registries = [Registry(image) for image in images]
    latest = max((t for t in registries[0].tags() if SEMVER.match(t)), key=version_key)

    manifest = manifest_path.read_text()
    current = re.search(r'^version: "([^"]+)"$', manifest, re.M).group(1)
    if APP_VERSION.match(current) and version_key(latest) <= version_key(current):
        return None

    digests = [registry.digest(latest) for registry in registries]
    if None in digests:
        return None  # not every image is published yet; try again next run

    compose = compose_path.read_text()
    for image, digest in zip(images, digests):
        compose = re.sub(rf"image: {re.escape(image)}:\S+", f"image: {image}:{latest}@{digest}", compose)
    compose_path.write_text(compose)

    manifest = re.sub(r'^version: "[^"]+"$', f'version: "{latest}"', manifest, flags=re.M)
    manifest = re.sub(r"^releaseNotes: .*$", f"releaseNotes: {name} {latest}.", manifest, flags=re.M)
    manifest_path.write_text(manifest)
    return latest


def main():
    for app_dir, (name, images) in APPS.items():
        version = update(app_dir, name, images)
        if version:
            print(f"{name} {version}")


if __name__ == "__main__":
    main()
