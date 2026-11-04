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

The bump also rewrites the app's releaseNotes with the bullet points of every
upstream release since the current version, taken from the app's GitHub
releases or from a Markdown changelog with one "## <prefix> X.Y.Z" section per
release.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# App folder -> display name, its images as written in docker-compose.yml, and
# where its release notes come from. All images of an app are released
# together under the same version tag.
APPS = {
    "lee-tofa": ("Tofa", ["ghcr.io/tofatv/tofa"],
                 {"changelog": "https://docs.tofa.tv/whats-new.md", "heading": "Server"}),
    "lee-beszel": ("Beszel", ["henrygd/beszel", "henrygd/beszel-agent-intel"],
                   {"github": "henrygd/beszel"}),
    "lee-recyclarr": ("Recyclarr", ["ghcr.io/recyclarr/recyclarr"],
                      {"github": "recyclarr/recyclarr"}),
}
MAX_NOTES = 10  # bullets per release section; the rest are left to the linked page
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


def fetch(url):
    # Cloudflare-fronted sites refuse urllib's default User-Agent.
    req = urllib.request.Request(url, headers={"User-Agent": "lee-umbrel-apps update check"})
    if url.startswith("https://api.github.com/"):
        req.add_header("Accept", "application/vnd.github+json")
        if os.environ.get("GITHUB_TOKEN"):
            req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    return urllib.request.urlopen(req, timeout=30).read().decode()


def github_releases(repo):
    """Published releases of a GitHub repo, as (version, notes, url)."""
    releases = []
    for release in json.loads(fetch(f"https://api.github.com/repos/{repo}/releases?per_page=50")):
        version = release["tag_name"].removeprefix("v")
        if SEMVER.match(version) and not release["draft"] and not release["prerelease"]:
            releases.append((version, release["body"] or "", release["html_url"]))
    return releases


def changelog_releases(url, heading):
    """Releases in a Markdown changelog, as (version, notes, url). Each release is
    a "## <heading> X.Y.Z" section; the url points at the section on the
    changelog's HTML page."""
    page = url.removesuffix(".md") + ".html"
    pattern = re.compile(rf"^## {re.escape(heading)} (\d+\.\d+\.\d+)\s*$", re.M)
    sections = re.split(r"^(?=## )", fetch(url), flags=re.M)
    releases = []
    for section in sections:
        match = pattern.match(section)
        if match:
            version = match.group(1)
            anchor = re.sub(r"[^a-z0-9]+", "-", f"{heading} {version}".lower())
            releases.append((version, section[match.end():], f"{page}#{anchor}"))
    return releases


def changes(notes):
    """The bullet points of release notes as (section, text) pairs, where section
    is the "### " heading above them, or None. Leaves out code blocks, credits
    for new contributors, PR numbers, author handles and link targets."""
    bullets, section, in_code = [], None, False
    for line in notes.splitlines():
        line = line.strip()
        if line.startswith("```"):
            in_code = not in_code
        elif in_code:
            continue
        elif line.startswith("#"):
            section = line.lstrip("#").strip()
            if section in ("What's Changed", "What’s Changed"):
                section = None
        elif line[:2] in ("- ", "* ") and section != "New Contributors":
            text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line[2:])
            text = re.sub(r"\s*\((?:#\d+(?:,\s*)?)+\)", "", text)
            text = re.sub(r"\s+by @[\w-]+(?:\[bot\])?", "", text)
            text = re.sub(r"\s+in https://github\.com/\S+", "", text)
            bullets.append((section, " ".join(text.split())))
    return bullets


def release_notes(name, source, current, latest):
    """releaseNotes text for an update from current to latest."""
    if "github" in source:
        releases = github_releases(source["github"])
    else:
        releases = changelog_releases(source["changelog"], source["heading"])
    new = sorted((r for r in releases if version_key(current) < version_key(r[0]) <= version_key(latest)),
                 key=lambda r: version_key(r[0]), reverse=True)
    if not new:
        return f"{name} {latest}."
    paragraphs = []
    for version, notes, url in new:
        bullets = changes(notes)
        lines = [f"{name} {version}" + (":" if bullets else ".")]
        sections = list(dict.fromkeys(section for section, _ in bullets))
        for section in sections:
            texts = [text for s, text in bullets if s == section]
            indent = "  " if section is None else "    "
            if section is not None:
                lines.append(f"  {section}:")
            lines += [f"{indent}- {text}" for text in texts[:MAX_NOTES]]
            if len(texts) > MAX_NOTES:
                lines.append(f"{indent}- …and {len(texts) - MAX_NOTES} more")
        paragraphs.append("\n".join(lines))
    paragraphs.append(f"Full release notes can be found at {new[0][2]}")
    return "\n\n".join(paragraphs)


def yaml_block(key, text):
    """A folded YAML block scalar. Blank lines in it become paragraph breaks and
    the more-indented bullet lines keep their own line breaks."""
    lines = [f"  {line}" if line else "" for line in text.replace("\n\n", "\n\n\n").splitlines()]
    return f"{key}: >-\n" + "\n".join(lines) + "\n"


def update(app_dir, name, images, notes_source):
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
    if not APP_VERSION.match(current):
        current = "0.0.0"
    try:
        notes = release_notes(name, notes_source, current, latest)
    except (OSError, ValueError, KeyError) as err:  # notes are nice to have; never block the update
        print(f"{name}: no release notes ({err})", file=sys.stderr)
        notes = f"{name} {latest}."
    notes = yaml_block("releaseNotes", notes)
    # The old notes run until the next top-level key or the end of the file.
    manifest = re.sub(r"^releaseNotes:.*\n(?:(?:[ \t]+.*)?\n)*?(?=\S|\Z)",
                      lambda _: notes, manifest + ("" if manifest.endswith("\n") else "\n"), flags=re.M)
    manifest_path.write_text(manifest)
    return latest


def main():
    for app_dir, (name, images, notes_source) in APPS.items():
        version = update(app_dir, name, images, notes_source)
        if version:
            print(f"{name} {version}")


if __name__ == "__main__":
    main()
