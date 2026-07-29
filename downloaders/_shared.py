"""Shared, platform-neutral core for authenticated course downloaders.

The adapters supply curriculum discovery and asset resolution. This module owns
the safety-sensitive behavior shared by them: cookie parsing, redacted logging,
DRM detection, resumable manifests, filesystem layout, and shell-free yt-dlp
invocation.
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    import httpx
except ImportError:  # Keep modules importable long enough to show a useful setup error.
    httpx = None


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = 60
RATE_JITTER = 0.7
DEFAULT_RATE_SECONDS = 1.5
AUDIO_FORMATS = {"m4a", "mp3", "opus", "wav"}


class DRMProtectedError(RuntimeError):
    """Media extractor confirmed that the resolved asset is DRM-protected."""


@dataclass(frozen=True)
class NetscapeCookie:
    domain: str
    include_subdomains: bool
    path: str
    secure: bool
    expires: int | None
    name: str
    value: str


@dataclass
class Asset:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    use_ytdlp: bool = False
    suggested_name: str | None = None


@dataclass
class Lesson:
    path: list[str]
    order: int
    title: str
    video: Asset | None = None
    description: str = ""
    materials: list[Asset] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    drm: bool = False

    def video_stem(self) -> str:
        return f"{self.order:02d}-{slugify(self.title)}"

    def lesson_id(self) -> str:
        return "/".join([*self.path, self.video_stem()])


def require_httpx() -> None:
    if httpx is None:
        raise SystemExit(
            "Install project dependencies first: .venv/bin/pip install -r requirements.txt"
        )


def parse_netscape_cookies(path: str | Path) -> list[NetscapeCookie]:
    """Parse a Netscape cookies.txt without ever logging cookie values."""
    cookie_path = Path(path)
    if not cookie_path.is_file():
        raise SystemExit(f"Cookie export not found: {cookie_path}")

    parsed: list[NetscapeCookie] = []
    for raw in cookie_path.read_text(encoding="utf-8").splitlines():
        is_http_only = raw.startswith("#HttpOnly_")
        if not raw or (raw.startswith("#") and not is_http_only):
            continue
        line = raw.removeprefix("#HttpOnly_")
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        domain, subdomains, cookie_pathname, secure, expires, name = fields[:6]
        value = "\t".join(fields[6:])
        try:
            expiry = int(expires) if expires and expires != "0" else None
        except ValueError:
            expiry = None
        parsed.append(
            NetscapeCookie(
                domain=domain,
                include_subdomains=subdomains.upper() == "TRUE",
                path=cookie_pathname or "/",
                secure=secure.upper() == "TRUE",
                expires=expiry,
                name=name,
                value=value,
            )
        )
    if not parsed:
        raise SystemExit(f"No Netscape-format cookies found in {cookie_path}")
    return parsed


def cookie_value(cookies: list[NetscapeCookie], name: str) -> str | None:
    for cookie in cookies:
        if cookie.name == name:
            return cookie.value
    return None


def httpx_cookie_jar(cookies: list[NetscapeCookie]):
    require_httpx()
    jar = httpx.Cookies()
    for cookie in cookies:
        jar.set(
            cookie.name,
            cookie.value,
            domain=cookie.domain,
            path=cookie.path,
        )
    return jar


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFC", (text or "").strip().lower())
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^\w\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "untitled"


_SECRET_RE = re.compile(
    r"(cookie|authorization|token|sig|signature|expires|key|password)=[^&\s;]+",
    re.IGNORECASE,
)
_HEADER_SECRET_RE = re.compile(
    r"(?i)\b(authorization|cookie|set-cookie)\s*:\s*[^\r\n]+"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_URL_QUERY_RE = re.compile(r"(https?://[^\s?#]+)\?[^\s#]+", re.IGNORECASE)


def redact(value: object) -> str:
    text = _URL_QUERY_RE.sub(r"\1?<redacted>", str(value))
    text = _HEADER_SECRET_RE.sub(
        lambda match: match.group(1) + ": <redacted>",
        text,
    )
    text = _BEARER_RE.sub("Bearer <redacted>", text)
    text = _SECRET_RE.sub(
        lambda match: match.group(0).split("=", 1)[0] + "=<redacted>",
        text,
    )
    return re.sub(
        r"([?&])(X-Amz-[^&\s]+|token|sig|signature)=[^&\s]+",
        r"\1\2=<redacted>",
        text,
        flags=re.IGNORECASE,
    )


def safe_url(value: str) -> str:
    """Return a URL suitable for diagnostics: no query, fragment, or user info."""
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return urlunsplit((parsed.scheme, host + port, parsed.path, "", ""))


def log(message: object) -> None:
    print(redact(message), flush=True)


def polite_sleep(rate: float) -> None:
    if rate > 0:
        time.sleep(rate + random.uniform(0, RATE_JITTER))


def load_manifest(course_dir: Path, platform: str, title: str) -> dict:
    path = course_dir / "manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest.setdefault("platform", platform)
        manifest.setdefault("course_title", title)
        manifest.setdefault("lessons", {})
        return manifest
    return {
        "schema_version": 1,
        "platform": platform,
        "course_title": title,
        "lessons": {},
    }


def save_manifest(course_dir: Path, manifest: dict) -> None:
    course_dir.mkdir(parents=True, exist_ok=True)
    path = course_dir / "manifest.json"
    temporary = path.with_suffix(".json.part")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _download_http(client, asset: Asset, destination: Path, rate: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with client.stream(
        "GET",
        asset.url,
        headers=asset.headers,
        timeout=HTTP_TIMEOUT,
    ) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for chunk in response.iter_bytes(chunk_size=1 << 16):
                handle.write(chunk)
    temporary.replace(destination)
    polite_sleep(rate)


def _download_ytdlp(
    asset: Asset,
    destination: Path,
    cookies_path: str | None,
    *,
    audio_only: bool,
    audio_format: str,
    max_height: int | None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--quiet",
        "--no-warnings",
        "--no-playlist",
        "--force-ipv4",
        "--socket-timeout",
        "60",
        "--retries",
        "10",
        "--fragment-retries",
        "10",
        "--retry-sleep",
        "2",
        "-o",
        str(destination),
    ]
    if audio_only:
        command += [
            "-x",
            "--audio-format",
            audio_format,
            "-S",
            "+size,+abr,+br,+res",
        ]
    elif max_height:
        command += [
            "--merge-output-format",
            "mp4",
            "-f",
            f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
        ]
    else:
        command += ["--merge-output-format", "mp4", "-S", "+res,+size,+br"]
    if cookies_path:
        command += ["--cookies", cookies_path]
    for name, value in asset.headers.items():
        command += ["--add-header", f"{name}:{value}"]
    command.append(asset.url)
    log(f"  yt-dlp -> {destination.name}")
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode:
        diagnostic = (completed.stderr or completed.stdout or "").strip()
        if diagnostic:
            log(f"  ! yt-dlp: {redact(diagnostic)}")
        if diagnostic_indicates_drm(diagnostic):
            raise DRMProtectedError("yt-dlp identified commercial DRM")
        raise subprocess.CalledProcessError(completed.returncode, command)


def diagnostic_indicates_drm(value: str) -> bool:
    diagnostic = value.lower()
    return any(
        marker in diagnostic
        for marker in (
            "drm protected",
            "drm-protected",
            "digital rights management",
            "widevine",
            "playready",
            "fairplay",
        )
    )


def hls_has_drm(client, asset: Asset) -> bool:
    """Detect commercial HLS DRM markers; ordinary AES-128 HLS is not DRM."""
    if ".m3u8" not in urlsplit(asset.url).path.lower():
        return False
    try:
        response = client.get(asset.url, headers=asset.headers, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
    except Exception as error:
        raise RuntimeError(
            f"HLS safety probe failed at {safe_url(asset.url)}: "
            f"{type(error).__name__}"
        ) from None
    manifest = response.text.lower()
    drm_markers = (
        "com.apple.streamingkeydelivery",
        "widevine",
        "playready",
        "skd://",
        'method=sample-aes',
    )
    return any(marker in manifest for marker in drm_markers)


def _write_description(lesson: Lesson, lesson_dir: Path) -> None:
    if not lesson.description.strip():
        return
    lesson_dir.mkdir(parents=True, exist_ok=True)
    (lesson_dir / f"{lesson.video_stem()}.description.md").write_text(
        f"# {lesson.title}\n\n{lesson.description.strip()}\n",
        encoding="utf-8",
    )


def _write_links(course_title: str, lessons: list[Lesson], course_dir: Path) -> None:
    lines = [f"# {course_title} - Links", ""]
    previous_path: list[str] = []
    for lesson in lessons:
        if not lesson.links:
            continue
        for depth, part in enumerate(lesson.path):
            if depth >= len(previous_path) or previous_path[depth] != part:
                lines.extend((f"{'#' * (depth + 2)} {part}", ""))
        previous_path = list(lesson.path)
        lines.extend(
            (
                f"{'#' * (len(lesson.path) + 2)} {lesson.title}",
                "",
                *(f"- {link}" for link in lesson.links),
                "",
            )
        )
    course_dir.mkdir(parents=True, exist_ok=True)
    (course_dir / "links.md").write_text("\n".join(lines), encoding="utf-8")


def run_lessons(
    *,
    platform: str,
    course_title: str,
    lessons: list[Lesson],
    course_dir: Path,
    client,
    args,
) -> int:
    """Write/download a resolved curriculum and return its failed lesson count."""
    course_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(course_dir, platform, course_title)
    _write_links(course_title, lessons, course_dir)
    log(f"[{platform}] {course_title} - {len(lessons)} lessons -> {course_dir}")

    if args.dry_run:
        drm_count = sum(lesson.drm for lesson in lessons)
        unresolved = sum(
            not lesson.drm and lesson.video is None for lesson in lessons
        )
        log(
            f"[dry-run] {len(lessons)} lessons | {drm_count} DRM (skip) | "
            f"{unresolved} without a resolved video"
        )
        for lesson in lessons:
            state = "DRM" if lesson.drm else ("--" if not lesson.video else "ok")
            log(f"  [{state}] {lesson.lesson_id()}")
        return unresolved

    for lesson in lessons:
        lesson_id = lesson.lesson_id()
        existing = manifest["lessons"].get(lesson_id, {})
        if args.resume and existing.get("status") == "done":
            continue
        if lesson.drm:
            manifest["lessons"][lesson_id] = {
                "status": "skipped-drm",
                "title": lesson.title,
            }
            save_manifest(course_dir, manifest)
            log(f"  [skipped-drm] {lesson_id}")
            continue
        if lesson.video is None:
            manifest["lessons"][lesson_id] = {
                "status": "failed",
                "title": lesson.title,
                "reason": "unresolved-video",
            }
            save_manifest(course_dir, manifest)
            log(f"  ! unresolved video: {lesson_id}")
            continue

        lesson_dir = course_dir.joinpath(*lesson.path)
        try:
            extension = args.audio_format if args.audio_only else "mp4"
            destination = lesson_dir / f"{lesson.video_stem()}.{extension}"
            if not (args.resume and destination.exists()):
                log(f"  v {lesson_id}")
                if lesson.video.use_ytdlp or args.audio_only:
                    _download_ytdlp(
                        lesson.video,
                        destination,
                        args.cookies,
                        audio_only=args.audio_only,
                        audio_format=args.audio_format,
                        max_height=args.max_height,
                    )
                else:
                    _download_http(client, lesson.video, destination, args.rate)
            _write_description(lesson, lesson_dir)
            for material in lesson.materials:
                name = (
                    material.suggested_name
                    or Path(urlsplit(material.url).path).name
                    or "material"
                )
                _download_http(
                    client,
                    material,
                    lesson_dir / "materials" / name,
                    args.rate,
                )
            manifest["lessons"][lesson_id] = {
                "status": "done",
                "title": lesson.title,
            }
        except DRMProtectedError:
            manifest["lessons"][lesson_id] = {
                "status": "skipped-drm",
                "title": lesson.title,
            }
            log(f"  [skipped-drm] {lesson_id}")
        except subprocess.CalledProcessError as error:
            manifest["lessons"][lesson_id] = {
                "status": "failed",
                "title": lesson.title,
                "reason": f"yt-dlp-exit-{error.returncode}",
            }
            log(f"  ! download failed: {lesson_id}: yt-dlp exit {error.returncode}")
        except Exception as error:  # noqa: BLE001 - preserve progress on long batches.
            manifest["lessons"][lesson_id] = {
                "status": "failed",
                "title": lesson.title,
                "reason": "download-error",
            }
            log(f"  ! failed: {lesson_id}: {redact(error)}")
        finally:
            save_manifest(course_dir, manifest)

    states = manifest["lessons"].values()
    done = sum(state.get("status") == "done" for state in states)
    drm_count = sum(state.get("status") == "skipped-drm" for state in states)
    failed = sum(state.get("status") == "failed" for state in states)
    log(
        f"[done] {done} downloaded | {drm_count} DRM-skipped | "
        f"{failed} failed -> {course_dir}"
    )
    return failed


def add_download_arguments(parser, *, default_cookies: str) -> None:
    parser.add_argument("--out", help="Override the generated course output directory.")
    parser.add_argument("--course-slug", help="Override the generated course folder name.")
    parser.add_argument(
        "--cookies",
        default=default_cookies,
        help=f"Netscape cookies.txt export (default: {default_cookies}).",
    )
    parser.add_argument(
        "--video",
        dest="audio_only",
        action="store_false",
        help="Download MP4 instead of the default transcription-ready audio.",
    )
    parser.set_defaults(audio_only=True)
    parser.add_argument(
        "--audio-format",
        default="m4a",
        choices=sorted(AUDIO_FORMATS),
        help="Audio container in default audio-only mode (default: m4a).",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        help="Cap MP4 height; implies --video.",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_RATE_SECONDS,
        help="Minimum seconds between platform API requests (default: 1.5).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Enumerate and resolve the curriculum without downloading media.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip lessons already marked done in manifest.json.",
    )


def normalize_download_arguments(args) -> None:
    if args.max_height:
        args.audio_only = False
    if args.rate < 0:
        raise SystemExit("--rate cannot be negative")
