#!/usr/bin/env python3
"""
Course downloader — JStack (https://app.jstack.com.br).  Stage 0 of the course-to-markdown pipeline.

Generated from knowledge/skills/course-downloader/script-template.py by the
`course-downloader` skill. The generic core (manifest/resume, rate-limit, redaction,
DRM guard, tree writer, links.md builder) is the template verbatim; only the three
PLATFORM-SPECIFIC functions + a few JStack helpers are filled in.

Platform facts (recon 2026-06-23, extended 2026-07-17; see
knowledge/skills/course-downloader/platform-recon.md):
  * REST API at https://api.jstack.com.br ; SPA frontend at https://app.jstack.com.br.
  * Auth = the user's own logged-in session: an `accessToken` cookie (Bearer) from the
    exported cookies.txt, plus a constant public X-App-Key, plus Origin/Referer.
  * THREE content types, not one (the SPA's own map: LIVE->lives, PROJECT->projects,
    TRAINING->trainings). The /search page is POST /contents/search (a GET 404s) and just
    groups these. Catalog listings: GET /contents/{lives,projects,trainings}; `lives` is
    CURSOR-PAGINATED via `nextPage` (16/page) — a single un-paged GET silently sees ~16 of 69.
  * Curriculum shape differs PER TYPE — detect, don't assume:
      - trainings/projects: GET /contents/<seg>/<slug> -> content.nodes is a SECTION/MODULE
        skeleton with NO video data; each leaf module must be fetched via
        GET /contents/<seg>/<slug>/modules/<parentSlugs/slug> to reach type=VIDEO nodes.
      - lives: the detail response already carries the WHOLE tree inline (MODULE -> VIDEO
        with data.external populated). The .../modules/ endpoint 404s for lives — they don't
        need it. One request enumerates a whole live.
    enumerate_course() therefore uses inline VIDEO nodes when present and only falls back to
    the per-module fetch when the detail response has none.
  * Video: each VIDEO node carries data.external={id, provider:BUNNY, libraryId, status}.
    The stream is Bunny HLS https://vz-<hash>.b-cdn.net/<id>/playlist.m3u8 where the vz-<hash>
    host is PER LIBRARY (627567 -> vz-ecd6b81a-333 [typescript]; 349046 -> vz-968de784-70c
    [full-stack]; 300830 -> vz-e9bd0866-1a0 [lives]); resolve it per video via
    _pull_zone_for_library() — NEVER hardcode one library's host (that 404s every video of
    any other course). Referer-gated, NO DRM, no token.
  * NOT every live is a Bunny course. A YouTube-hosted live has `nodes: []` and the URL in
    metadata.youtubeURL (also mirrored under metadata.protected). Known case: live #66
    `dominando-os-react-hooks`. Without _youtube_lesson() such a course enumerates to ZERO
    lessons and writes a clean-looking manifest — the same silent-success trap as the
    wrong-pull-zone bug. An empty tree with no youtubeURL is reported, never written as done.

Run from the course-to-markdown project root, using its .venv:

    # List everything this session can see (69 lives + 3 projects + 2 trainings):
    .venv/bin/python downloaders/jstack.py --list --cookies input/cookies.txt

    # One course — any type; the URL's segment picks it, a bare slug is looked up:
    .venv/bin/python downloaders/jstack.py "https://app.jstack.com.br/lives/react-router-v7" \
        --cookies input/cookies.txt --dry-run

    # Every live, sequentially (one course at a time), resumable:
    .venv/bin/python downloaders/jstack.py --all lives --cookies input/cookies.txt --resume

    # Downloads audio-only .m4a by default (Stage 1 only transcribes); add --video for .mp4.
    # Then drop --dry-run to download; --resume to continue an interrupted run.

Hard rules (do not remove):
  * Legitimate access only; use the user's own session. No credential automation.
  * Respect DRM: mark skipped-drm, never decrypt.
  * yt-dlp / ffmpeg via argument arrays, never a shell string.
  * Redact cookies/tokens/signed URLs in all output.
  * Media lands under course-to-markdown/input/ (gitignored). Never commit it.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

# Third-party (declared in course-to-markdown/requirements.txt, installed in its .venv):
#   httpx, yt-dlp
try:
    import httpx
except ImportError:  # keep importable before deps are installed
    httpx = None


# --------------------------------------------------------------------------- #
# Config  (PLATFORM-SPECIFIC)
# --------------------------------------------------------------------------- #
PLATFORM = "jstack"
DEFAULT_RATE_SECONDS = 1.5               # polite floor between network ops
RATE_JITTER = 0.7                        # added random 0..jitter seconds
HTTP_TIMEOUT = 60

API_BASE = "https://api.jstack.com.br"
ORIGIN = "https://app.jstack.com.br"
# Public client key sent by the SPA on every API call (not a secret / not user-bound).
APP_KEY = "iuS99sAdm9seEfMX4gxMm1OjDl4MzEy4M2ODjNudTg5M44OXOXgzbjnU"
# Bunny Stream pull-zone host PER JStack video library. Each course's videos are served from a
# library-specific `vz-<hash>.b-cdn.net`, and the libraryId rides on every VIDEO node
# (data.external.libraryId) — so the host must be picked per video, never hardcoded. Seeded with
# recon-confirmed libraries; an unknown library is auto-discovered from the public Bunny embed
# page and cached (so a new course can't silently build wrong-library URLs -> 404 — the exact
# bug the typescript-only hardcode caused for full-stack). See _pull_zone_for_library().
BUNNY_PULL_ZONES: dict[str, str] = {
    "627567": "vz-ecd6b81a-333",   # formacao-typescript
    "349046": "vz-968de784-70c",   # formacao-full-stack
    "300830": "vz-e9bd0866-1a0",   # lives (all 68 Bunny-hosted lives share one library)
}
BUNNY_EMBED_BASE = "https://iframe.mediadelivery.net/embed"
_PULL_ZONE_RE = re.compile(r"vz-[0-9a-z]+-[0-9a-z]+\.b-cdn\.net")

# The SPA's own content-type map (bundle: `new Map([["LIVE","lives"],["PROJECT","projects"],
# ["TRAINING","trainings"]])`). The API segment is the ONLY thing that varies between types —
# every /contents/<segment>/... path below is otherwise identical.
CONTENT_SEGMENTS: tuple[str, ...] = ("lives", "projects", "trainings")

# Where each type lands under input/. Trainings keep the flat legacy layout (the two
# formacao-* folders already live there); the bulk types get a parent folder so Stage 1 can
# transcribe them as their own batch instead of `main.py input/` sweeping all 69 at once.
INPUT_SUBDIR: dict[str, str] = {
    "lives": "jstack-lives",
    "projects": "jstack-projects",
    "trainings": "",
}


# --------------------------------------------------------------------------- #
# Data model (contract between PLATFORM-SPECIFIC code and the generic core)
# --------------------------------------------------------------------------- #
@dataclass
class Asset:
    url: str
    headers: dict = field(default_factory=dict)   # may carry auth — REDACTED in logs
    use_ytdlp: bool = False                        # True for HLS/DASH/Vimeo/Wistia/YouTube
    suggested_name: str | None = None              # for materials (keep the real extension)


@dataclass
class Lesson:
    path: list[str]                # final folder chain under the course root, in order
    order: int                     # 1-based position within its parent folder
    title: str
    video: Asset | None = None
    description: str = ""           # plain text / markdown
    materials: list[Asset] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    drm: bool = False              # True when DRM is detected -> skipped, never decrypted

    def lesson_id(self) -> str:
        return "/".join(self.path + [self.video_stem()])

    def video_stem(self) -> str:
        return f"{self.order:02d}-{slugify(self.title)}"


# --------------------------------------------------------------------------- #
# PLATFORM-SPECIFIC — JStack
# --------------------------------------------------------------------------- #
def authenticate(args) -> "httpx.Client":
    """httpx.Client carrying the user's OWN JStack session.

    Reads the exported Netscape cookies.txt: the HttpOnly `accessToken` cookie becomes
    the Bearer token, and the whole jar is sent alongside it (matches the browser).
    No login is automated. See platform-recon.md §2.
    """
    if not args.cookies:
        sys.exit("JStack needs --cookies <cookies.txt> exported from your logged-in browser "
                 "(app.jstack.com.br). See platform-recon.md §2.")
    cookies = _parse_netscape_cookies(args.cookies)
    token = cookies.get("accessToken")
    if not token:
        sys.exit("No `accessToken` cookie in cookies.txt — re-export while logged in to "
                 "app.jstack.com.br (it is HttpOnly, so use a full cookies.txt export).")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-App-Key": APP_KEY,
        "Origin": ORIGIN,
        "Referer": ORIGIN + "/",
        "Accept": "application/json",
    }
    return httpx.Client(base_url=API_BASE, headers=headers, cookies=cookies,
                        timeout=HTTP_TIMEOUT, follow_redirects=True)


def enumerate_course(client, segment: str, slug: str) -> "tuple[str, list[Lesson]]":
    """Return (course_title, lessons) in order, for any content type.

    JStack returns each lesson's full payload (video id + description + materials/links)
    alongside the video node, so all assets are built here in one pass and
    resolve_lesson_assets() below is a no-op. See platform-recon.md §3-6.

    The tree arrives one of three ways, so DETECT rather than assume (see module docstring):
      1. inline  — lives: the detail response already holds MODULE -> VIDEO with data.external.
      2. youtube — a live with no nodes at all, video URL in metadata.youtubeURL.
      3. fetched — trainings/projects: detail is a SECTION/MODULE skeleton; each leaf module
                   must be fetched to reach its VIDEO nodes.
    """
    detail = _api_get(client, f"/contents/{segment}/{slug}")
    content = detail["content"]
    course_title = content.get("name") or slug
    nodes = content.get("nodes") or []

    lessons: list[Lesson] = []
    meta = _course_meta_lesson(content)
    if meta:
        lessons.append(meta)

    # 1. Inline tree (lives) — every VIDEO is already here; no extra request needed.
    inline = [(v, chain) for v, chain in _walk_videos(nodes, [])
              if ((v.get("data") or {}).get("external") or {}).get("id")]
    if inline:
        lessons += [_lesson_from_video(v, chain) for v, chain in inline]
        return course_title, lessons

    # 2. No tree at all -> a YouTube-hosted live, or genuinely empty (reported, never silent).
    if not nodes:
        yt = _youtube_lesson(content)
        if yt:
            lessons.append(yt)
        else:
            log(f"  ! {segment}/{slug}: no nodes and no metadata.youtubeURL — nothing to "
                f"download (unknown content shape; not marking done)")
        return course_title, lessons

    # 3. Skeleton only (trainings/projects) -> fetch each leaf module.
    for leaf_path in _leaf_module_paths(nodes):
        try:
            resp = _api_get(client, f"/contents/{segment}/{slug}/modules/{leaf_path}")
        except Exception as e:  # noqa: BLE001 — one bad module shouldn't kill the course
            log(f"  ! module fetch failed: {leaf_path}: {redact(e)}")
            continue
        root = resp.get("contents") or resp.get("content") or {}
        for vnode, mod_chain in _walk_videos([root], []):
            lessons.append(_lesson_from_video(vnode, mod_chain))
    return course_title, lessons


def resolve_lesson_assets(client, lesson: Lesson) -> None:
    """No-op for JStack — enumerate_course() already populated video/description/links
    from the bulk module payload (avoids one extra request per lesson)."""
    return None


# ---- JStack helpers ------------------------------------------------------- #
def _parse_netscape_cookies(path: str) -> dict:
    """Minimal Netscape cookies.txt parser. Honors the `#HttpOnly_` domain prefix
    (where the accessToken lives) and ignores ordinary comment/blank lines."""
    cookies: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookies[parts[5]] = parts[6]
    return cookies


def list_catalog(client, segments: "tuple[str, ...]" = CONTENT_SEGMENTS) -> "dict[str, list[dict]]":
    """Every content this session can see, per type: {segment: [entry, ...]}.

    `lives` is cursor-paginated (`nextPage`, a base64 DynamoDB key) — follow it to the end or
    you silently get only the first 16 of 69. The other two return everything in one page.
    """
    catalog: dict[str, list[dict]] = {}
    for seg in segments:
        items: list[dict] = []
        page, guard = None, 0
        while guard < 50:                     # cursor loop, bounded so a bad cursor can't spin
            guard += 1
            resp = client.get(f"/contents/{seg}", params={"page": page} if page else None)
            resp.raise_for_status()
            polite_sleep(DEFAULT_RATE_SECONDS)
            data = resp.json()
            items += data.get("contents") or []
            page = data.get("nextPage")
            if not page:
                break
        catalog[seg] = items
    return catalog


def _content_ref_from_url(course_url: str, client) -> "tuple[str, str]":
    """Resolve a user-supplied course reference to (segment, slug).

    Accepts a full URL of any type (.../lives/<slug>, .../contents/projects/<slug>, ...) or a
    bare slug, which is looked up across the catalog so `--list` output can be pasted straight
    back in. Guessing the segment is not an option: the wrong one 404s the whole course.
    """
    u = (course_url or "").strip()
    m = re.search(rf"/({'|'.join(CONTENT_SEGMENTS)})/([^/?#]+)", u)
    if m:
        return m.group(1), m.group(2)

    slug = u if (u and "/" not in u and "://" not in u) else next(
        (s for s in reversed([p for p in urlparse(u).path.split("/") if p])), "")
    if slug:
        catalog = list_catalog(client)
        hits = [(seg, i) for seg, items in catalog.items()
                for i in items if i.get("slug") == slug]
        if len(hits) == 1:
            return hits[0][0], slug
        if len(hits) > 1:
            sys.exit(f"Ambiguous slug {slug!r} — exists as: "
                     + ", ".join(f"{seg}/{slug}" for seg, _ in hits)
                     + ". Pass a full URL to disambiguate.")
    try:
        avail = list_catalog(client)
        hint = "\n".join(f"  {seg}: " + ", ".join(i.get("slug", "") for i in items)
                         for seg, items in avail.items())
    except Exception:  # noqa: BLE001
        hint = ""
    sys.exit(f"Could not resolve {redact(course_url)!r} to a course; pass a "
             f".../<{'|'.join(CONTENT_SEGMENTS)}>/<slug> URL or a bare slug.\n{hint}")


def _api_get(client, path: str, rate: float = DEFAULT_RATE_SECONDS) -> dict:
    r = client.get(path)
    r.raise_for_status()
    polite_sleep(rate)
    return r.json()


def _leaf_module_paths(nodes: list, parents: list[str] | None = None) -> list[str]:
    """Slug-paths (parentSlugs/own-slug) of every leaf MODULE (a module with no child
    nodes) — exactly the paths the .../modules/ endpoint expects."""
    parents = parents or []
    out: list[str] = []
    for n in nodes:
        slug = n.get("slug")
        if not slug:
            continue
        chain = parents + [slug]
        kids = n.get("nodes") or []
        if kids:
            out.extend(_leaf_module_paths(kids, chain))
        else:
            out.append("/".join(chain))
    return out


def _walk_videos(nodes: list, mod_chain: list[tuple[int, str]]):
    """Yield (video_node, module_chain) for every type=VIDEO node, accumulating the
    (order, name) of each MODULE ancestor so the folder tree can be rebuilt."""
    for n in nodes:
        ntype = n.get("type")
        if ntype == "VIDEO" or ((n.get("data") or {}).get("external") and not (n.get("nodes"))):
            yield n, mod_chain
        else:
            name = n.get("name") or n.get("slug") or "modulo"
            order = n.get("order") or 0
            yield from _walk_videos(n.get("nodes") or [], mod_chain + [(order, name)])


def _pull_zone_for_library(library_id: str, sample_guid: str) -> str:
    """Resolve a JStack Bunny libraryId -> its `vz-<hash>` CDN host.

    Known libraries come from BUNNY_PULL_ZONES; an unknown one is discovered ONCE by scraping the
    public Bunny Stream embed page (which references the playlist host), then cached for the rest
    of the run. Raises if it can't be resolved — we never silently fall back to another library's
    host, because that built wrong URLs -> 404 for an entire course (full-stack vs typescript)."""
    host = BUNNY_PULL_ZONES.get(library_id)
    if host:
        return host
    embed = f"{BUNNY_EMBED_BASE}/{library_id}/{sample_guid}"
    try:
        r = httpx.get(embed, headers={"Referer": ORIGIN + "/", "User-Agent": "Mozilla/5.0"},
                      timeout=HTTP_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        m = _PULL_ZONE_RE.search(r.text)
        if m:
            host = m.group(0).split(".", 1)[0]          # vz-<hash>
            BUNNY_PULL_ZONES[library_id] = host          # memoize for the rest of the run
            log(f"  + discovered pull zone for library {library_id}: {host}")
            return host
    except Exception as e:  # noqa: BLE001
        log(f"  ! pull-zone discovery failed for library {library_id}: {redact(e)}")
    raise RuntimeError(
        f"no Bunny pull zone for libraryId {library_id} — add it to BUNNY_PULL_ZONES "
        f"(scrape {BUNNY_EMBED_BASE}/{library_id}/<guid> for the vz-* host)"
    )


def _lesson_from_video(vnode: dict, mod_chain: list[tuple[int, str]]) -> Lesson:
    path = [f"{order + 1:02d}-{slugify(name)}" for order, name in mod_chain]
    data = vnode.get("data") or {}
    ext = data.get("external") or {}
    video: Asset | None = None
    provider = (ext.get("provider") or "").upper()
    guid = ext.get("id")
    if provider == "BUNNY" and guid:
        try:
            pull_zone = _pull_zone_for_library(str(ext.get("libraryId") or ""), guid)
            video = Asset(
                url=f"https://{pull_zone}.b-cdn.net/{guid}/playlist.m3u8",
                headers={"Referer": ORIGIN + "/", "Origin": ORIGIN},
                use_ytdlp=True,
            )
        except Exception as e:  # noqa: BLE001 — record + continue; reported as "no video"
            log(f"  ! {redact(e)} on {vnode.get('slug')} — left unresolved")
    elif guid or provider:
        log(f"  ? unhandled video provider {provider!r} on {vnode.get('slug')} — left unresolved")
    return Lesson(
        path=path,
        order=(vnode.get("order") or 0) + 1,
        title=vnode.get("name") or vnode.get("slug") or "aula",
        video=video,
        description=(vnode.get("description") or "").strip(),
        materials=_extract_materials(vnode),
        links=_extract_links(vnode),
    )


def _extract_links(node: dict) -> list[str]:
    out: list[str] = []
    for l in node.get("links") or []:
        if isinstance(l, str):
            out.append(l)
        elif isinstance(l, dict):
            u = l.get("url") or l.get("href") or l.get("link")
            if u:
                out.append(u)
    return out


def _extract_materials(node: dict) -> list[Asset]:
    """Best-effort: JStack's material schema is unverified (none present in the test
    course), so resolve common shapes and log anything unrecognized rather than guess."""
    out: list[Asset] = []
    for m in node.get("materials") or []:
        if not isinstance(m, dict):
            continue
        url = m.get("url") or m.get("downloadURL") or m.get("href")
        key = m.get("storageKey") or m.get("key")
        if not url and key:
            url = f"https://cdn.jstack.com.br/{key}"
        if not url:
            log(f"  ? material without a resolvable URL on {node.get('slug')}: "
                f"{json.dumps(m, ensure_ascii=False)[:200]}")
            continue
        name = m.get("name") or m.get("title") or Path(urlparse(url).path).name or "material"
        out.append(Asset(url=url, headers={"Referer": ORIGIN + "/"}, suggested_name=name))
    return out


def _youtube_lesson(content: dict) -> "Lesson | None":
    """A live whose recording lives on YouTube instead of Bunny (nodes: []).

    The URL sits at metadata.youtubeURL, mirrored under metadata.protected.youtubeURL. yt-dlp
    handles youtube.com/live/<id> natively, so this is just a different Asset — no Referer
    gate, no pull zone. Known case: live #66 `dominando-os-react-hooks`.
    """
    meta = content.get("metadata") or {}
    url = meta.get("youtubeURL") or (meta.get("protected") or {}).get("youtubeURL")
    if not url:
        return None
    return Lesson(
        path=[],
        # order=1, not 0: the course meta lesson is already 00-<slug>, and an identical stem
        # would collide on lesson_id() -> one shared manifest key for two lessons, letting
        # --resume mark the blurb "done" and skip the actual video.
        order=1,
        title=content.get("name") or content.get("slug") or "aula",
        video=Asset(url=url, use_ytdlp=True),
        description=(content.get("description") or "").strip(),
        links=[url],
    )


def _course_meta_lesson(content: dict) -> "Lesson | None":
    """A videoless root-level 'lesson' that captures the course blurb, author(s) and code
    repo into 00-<course>.description.md + links.md (Stage 1 ignores non-media files)."""
    parts: list[str] = []
    links: list[str] = []
    if content.get("description"):
        parts.append(content["description"].strip())
    names = ", ".join(a.get("name", "") for a in (content.get("authors") or []) if a.get("name"))
    if names:
        parts.append(f"**Autor(es):** {names}")
    if content.get("repoURL"):
        parts.append(f"**Repositório:** {content['repoURL']}")
        links.append(content["repoURL"])
    if not parts and not links:
        return None
    return Lesson(path=[], order=0, title=content.get("name") or "Curso",
                  description="\n\n".join(parts), links=links)


# --------------------------------------------------------------------------- #
# Generic core — reused verbatim from script-template.py
# --------------------------------------------------------------------------- #
def slugify(text: str) -> str:
    """Lowercase kebab-case, preserving accented letters (matches input/ convention).

    NFC-normalize first: some APIs return decomposed (NFD) text where accents are
    separate combining marks that \\w drops — collapsing 'Introdução' to 'introducao'.
    Normalizing to precomposed form keeps the accents the \\w class below preserves.
    """
    text = unicodedata.normalize("NFC", (text or "").strip().lower())
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^\w\-]", "", text, flags=re.UNICODE)  # \w keeps á, ç, ã ...
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "untitled"


_SECRET_RE = re.compile(
    r"(cookie|authorization|token|sig|signature|expires|key|password)=[^&\s;]+",
    re.IGNORECASE,
)


def redact(text) -> str:
    """Mask secrets before logging or surfacing an error."""
    text = _SECRET_RE.sub(lambda m: m.group(0).split("=")[0] + "=<redacted>", str(text))
    return re.sub(r"([?&])(X-Amz-[^&\s]+|token|sig)=[^&\s]+", r"\1\2=<redacted>", text)


def log(msg: str) -> None:
    print(redact(msg), flush=True)


def polite_sleep(rate: float) -> None:
    time.sleep(rate + random.uniform(0, RATE_JITTER))


# ---- manifest (resumability) --------------------------------------------- #
def load_manifest(course_dir: Path) -> dict:
    f = course_dir / "manifest.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"platform": PLATFORM, "lessons": {}}


def save_manifest(course_dir: Path, manifest: dict) -> None:
    (course_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---- downloads (shell-free) ---------------------------------------------- #
def download_http(client, asset: Asset, dest: Path, rate: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with client.stream("GET", asset.url, headers=asset.headers, timeout=HTTP_TIMEOUT) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in r.iter_bytes(chunk_size=1 << 16):
                fh.write(chunk)
    tmp.replace(dest)  # promote only after a complete download
    polite_sleep(rate)


def download_ytdlp(asset: Asset, dest: Path, cookies: "str | None",
                   max_height: "int | None" = None,
                   audio_only: bool = False, audio_format: str = "m4a") -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # `-m yt_dlp` (not the bare console script) so the .venv's yt-dlp is used
    # regardless of PATH — the project runs everything through .venv/bin/python.
    # --force-ipv4: some hosts (e.g. WSL2) have a dead IPv6 path where TLS connects but reads
    # stall; prefer v4. Generous socket-timeout + retries ride out flaky DNS / slow CDN edges
    # over a long course (a 64k-fragment HLS pull shouldn't die on one slow segment).
    cmd = [sys.executable, "-m", "yt_dlp", "--no-progress", "--no-playlist",
           "--force-ipv4", "--socket-timeout", "60",
           "--retries", "10", "--fragment-retries", "10", "--retry-sleep", "2",
           "-o", str(dest)]
    if audio_only:
        # Stage 1 only transcribes audio, so keep just the audio track. Where the host has
        # no separate audio rendition (e.g. JStack HLS) yt-dlp grabs the smallest source
        # then extracts; an AAC source copies losslessly into m4a. `-S +size` => smallest.
        cmd += ["-x", "--audio-format", audio_format, "-S", "+size,+abr,+br,+res"]
    elif max_height:  # optional override: best video up to this height
        cmd += ["--merge-output-format", "mp4",
                "-f", f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b"]
    else:  # DEFAULT video: smallest rendition — this pipeline transcribes, it never watches
        cmd += ["--merge-output-format", "mp4", "-S", "+res,+size,+br"]
    if cookies:
        cmd += ["--cookies", cookies]
    for k, v in asset.headers.items():
        cmd += ["--add-header", f"{k}:{v}"]
    cmd += [asset.url]
    log(f"  yt-dlp -> {dest.name}")
    subprocess.run(cmd, check=True)  # argument array, no shell


# ---- writers ------------------------------------------------------------- #
def write_description(lesson: Lesson, lesson_dir: Path) -> None:
    if not lesson.description.strip():
        return
    lesson_dir.mkdir(parents=True, exist_ok=True)
    (lesson_dir / f"{lesson.video_stem()}.description.md").write_text(
        f"# {lesson.title}\n\n{lesson.description.strip()}\n", encoding="utf-8"
    )


def build_links_md(course_title: str, lessons: "list[Lesson]", course_dir: Path) -> None:
    """Hierarchical links.md mirroring the course tree (matches existing format)."""
    lines = [f"# {course_title} - Links", ""]
    last_path: list[str] = []
    for lesson in lessons:
        if not lesson.links:
            continue
        for depth, part in enumerate(lesson.path):
            if depth >= len(last_path) or last_path[depth] != part:
                lines += [f"{'#' * (depth + 2)} {part}", ""]
        last_path = list(lesson.path)
        lines += [f"{'#' * (len(lesson.path) + 2)} {lesson.title}", ""]
        lines += [f"- {url}" for url in lesson.links]
        lines.append("")
    (course_dir / "links.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _course_dir_for(args, segment: str, course_slug: str) -> Path:
    """input/<subdir>/<slug> — trainings stay flat (legacy), bulk types get a parent folder."""
    if args.out:
        return Path(args.out)
    root = Path(__file__).resolve().parent.parent / "input"
    sub = INPUT_SUBDIR.get(segment, "")
    return (root / sub / course_slug) if sub else (root / course_slug)


def run_one(args, client, segment: str, slug: str) -> int:
    """Download a single course. Returns the number of FAILED lessons (0 = clean)."""
    course_title, lessons = enumerate_course(client, segment, slug)
    course_slug = args.course_slug or slug or slugify(course_title)
    course_dir = _course_dir_for(args, segment, course_slug)
    course_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(course_dir)
    log(f"[{PLATFORM}] {course_title} - {len(lessons)} lessons -> {course_dir}")

    # resolve everything first so links.md / dry-run reflect the whole course
    for lesson in lessons:
        try:
            resolve_lesson_assets(client, lesson)
        except Exception as e:  # noqa: BLE001 — keep enumerating; record below
            log(f"  ! resolve failed: {lesson.lesson_id()}: {redact(e)}")

    build_links_md(course_title, lessons, course_dir)

    if args.dry_run:
        drm = sum(1 for x in lessons if x.drm)
        novid = sum(1 for x in lessons if not x.drm and not x.video)
        log(f"[dry-run] {len(lessons)} lessons | {drm} DRM (skip) | {novid} without a resolved video")
        for x in lessons:
            flag = "DRM" if x.drm else ("--" if not x.video else "ok")
            log(f"  [{flag}] {x.lesson_id()}")
        return 0

    for lesson in lessons:
        lid = lesson.lesson_id()
        if args.resume and manifest["lessons"].get(lid, {}).get("status") == "done":
            continue
        if lesson.drm:
            manifest["lessons"][lid] = {"status": "skipped-drm", "title": lesson.title}
            save_manifest(course_dir, manifest)
            log(f"  [skipped-drm] {lid}")
            continue

        lesson_dir = course_dir.joinpath(*lesson.path)
        try:
            if lesson.video:
                media_ext = args.audio_format if args.audio_only else "mp4"
                dest = lesson_dir / f"{lesson.video_stem()}.{media_ext}"
                if not (args.resume and dest.exists()):
                    log(f"  v {lid}")
                    if lesson.video.use_ytdlp or args.audio_only:
                        download_ytdlp(lesson.video, dest, args.cookies, args.max_height,
                                       args.audio_only, args.audio_format)
                    else:
                        download_http(client, lesson.video, dest, args.rate)
            write_description(lesson, lesson_dir)
            for m in lesson.materials:
                name = m.suggested_name or slugify(Path(m.url).name) or "material"
                download_http(client, m, lesson_dir / "materials" / name, args.rate)
            manifest["lessons"][lid] = {"status": "done", "title": lesson.title}
        except subprocess.CalledProcessError as e:
            manifest["lessons"][lid] = {"status": "failed", "title": lesson.title}
            log(f"  ! download failed: {lid}: yt-dlp exit {e.returncode}")
        except Exception as e:  # noqa: BLE001
            manifest["lessons"][lid] = {"status": "failed", "title": lesson.title}
            log(f"  ! failed: {lid}: {redact(e)}")
        finally:
            save_manifest(course_dir, manifest)

    states = manifest["lessons"].values()
    done = sum(1 for s in states if s["status"] == "done")
    drm = sum(1 for s in states if s["status"] == "skipped-drm")
    failed = sum(1 for s in states if s["status"] == "failed")
    log(f"[done] {done} downloaded | {drm} DRM-skipped | {failed} failed -> {course_dir}")
    return failed


def print_catalog(catalog: "dict[str, list[dict]]") -> None:
    for seg, items in catalog.items():
        log(f"\n=== {seg} ({len(items)}) ===")
        for i in items:
            num = (i.get("metadata") or {}).get("number")
            cat = (i.get("category") or {}).get("name", "")
            lock = "" if (i.get("isAllowed") and i.get("isUnlocked")) else "  [LOCKED]"
            tag = f"#{num:<3}" if num is not None else "    "
            log(f"  {tag} {i.get('slug','')!s:<70s} {cat}{lock}")
    log(f"\ntotal: {sum(len(v) for v in catalog.values())}")


def run(args) -> int:
    if httpx is None:
        sys.exit("Install deps into the course-to-markdown .venv: pip install httpx yt-dlp")
    if args.max_height:  # asking for a resolution implies you want the video, not audio-only
        args.audio_only = False

    client = authenticate(args)

    if args.list_only:
        print_catalog(list_catalog(client))
        return 0

    # ---- single course ---------------------------------------------------- #
    if not args.all:
        segment, slug = _content_ref_from_url(args.course_url, client)
        return 1 if run_one(args, client, segment, slug) else 0

    # ---- batch: one course at a time, sequentially ------------------------ #
    segments = CONTENT_SEGMENTS if args.all == "all" else (args.all,)
    catalog = list_catalog(client, segments)
    queue = [(seg, i) for seg in segments for i in catalog[seg]
             if i.get("isAllowed") and i.get("isUnlocked")]
    skipped = sum(len(catalog[s]) for s in segments) - len(queue)
    if args.limit:
        queue = queue[:args.limit]
    log(f"[{PLATFORM}] batch: {len(queue)} course(s)"
        + (f" ({skipped} locked, skipped)" if skipped else ""))

    # --course-slug names ONE folder; it cannot name N. Guard rather than overwrite in a loop.
    if args.course_slug or args.out:
        sys.exit("--course-slug/--out name a single folder and cannot be combined with --all; "
                 "the batch derives input/<subdir>/<slug> per course.")

    results: list[tuple[str, str, str]] = []
    for n, (seg, item) in enumerate(queue, 1):
        slug = item.get("slug") or ""
        log(f"\n───── [{n}/{len(queue)}] {seg}/{slug} ─────")
        try:
            failed = run_one(args, client, seg, slug)
            results.append((seg, slug, "clean" if not failed else f"{failed} failed"))
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 — one bad course must not kill the batch
            log(f"  ! course failed: {seg}/{slug}: {redact(e)}")
            results.append((seg, slug, "ERROR"))

    log(f"\n═════ batch summary ═════")
    bad = [r for r in results if r[2] != "clean"]
    for seg, slug, status in bad:
        log(f"  ! {seg}/{slug}: {status}")
    log(f"{len(results) - len(bad)}/{len(results)} clean"
        + (f" | {len(bad)} need attention (re-run with --resume)" if bad else ""))
    return 1 if bad else 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=f"Download a course from {PLATFORM} (Stage 0).")
    p.add_argument("course_url", nargs="?",
                   help="Course home URL (.../<lives|projects|trainings>/<slug>) or a bare "
                        "slug. Omit when using --list or --all.")
    p.add_argument("--list", dest="list_only", action="store_true",
                   help="List every course this session can see (all types) and exit.")
    p.add_argument("--all", choices=(*CONTENT_SEGMENTS, "all"), default=None,
                   help="Batch-download a whole content type (or 'all'), one course at a "
                        "time. Locked courses are skipped; a failing course is reported and "
                        "the batch continues. Pair with --resume to continue a run.")
    p.add_argument("--limit", type=int, default=None,
                   help="With --all: stop after N courses (smoke-test a batch).")
    p.add_argument("--out", help="Output dir (default: ../input/<subdir>/<course-slug>).")
    p.add_argument("--course-slug", dest="course_slug", help="Folder name under input/.")
    p.add_argument("--cookies", help="Path to exported cookies.txt (Netscape format).")
    p.add_argument("--video", dest="audio_only", action="store_false",
                   help="Download video (.mp4) instead of the DEFAULT audio-only (.m4a). The "
                        "pipeline only transcribes audio, so video is for human reference only.")
    p.set_defaults(audio_only=True)  # audio-only is the default — Stage 1 never watches video
    p.add_argument("--audio-format", dest="audio_format", default="m4a",
                   help="Audio container for the default audio-only mode (m4a/opus/mp3; "
                        "default m4a). Must be one of course-to-markdown's AUDIO_EXTS.")
    p.add_argument("--max-height", dest="max_height", type=int, default=None,
                   help="Cap video height (e.g. 720); implies --video. Otherwise --video "
                        "fetches the smallest rendition.")
    p.add_argument("--rate", type=float, default=DEFAULT_RATE_SECONDS, help="Seconds between network ops.")
    p.add_argument("--dry-run", action="store_true", help="Enumerate + resolve only; download nothing.")
    p.add_argument("--resume", action="store_true", help="Skip lessons already done in manifest.json.")
    args = p.parse_args(argv)
    if not (args.course_url or args.list_only or args.all):
        p.error("pass a course URL/slug, or --list, or --all <type>.")
    if args.course_url and args.all:
        p.error("--all downloads a whole type; drop the course URL (or drop --all).")
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
