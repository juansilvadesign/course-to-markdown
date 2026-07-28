#!/usr/bin/env python3
"""Authenticated Skool classroom downloader (Stage 0).

Reads the server-rendered Next.js curriculum using the user's exported Skool
session. Native Skool/Mux HLS and supported external embeds are passed to
yt-dlp; signed stream queries are suppressed from logs. The default output is
audio-only for Stage 1 transcription.

Example:

    .venv/bin/python downloaders/skool.py \
      "https://www.skool.com/win-elite-3896/classroom/3d94f2ce\
?md=424159aee10f42158da196f19ce0f7e0" --dry-run

Only use this with content your account is entitled to access. This script does
not automate login and never attempts to bypass DRM.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit, urlunsplit

try:
    from ._shared import (
        Asset,
        BROWSER_USER_AGENT,
        HTTP_TIMEOUT,
        Lesson,
        add_download_arguments,
        hls_has_drm,
        httpx,
        httpx_cookie_jar,
        log,
        normalize_download_arguments,
        parse_netscape_cookies,
        polite_sleep,
        redact,
        require_httpx,
        run_lessons,
        slugify,
    )
except ImportError:  # Direct script execution: python downloaders/skool.py
    from _shared import (  # type: ignore[no-redef]
        Asset,
        BROWSER_USER_AGENT,
        HTTP_TIMEOUT,
        Lesson,
        add_download_arguments,
        hls_has_drm,
        httpx,
        httpx_cookie_jar,
        log,
        normalize_download_arguments,
        parse_netscape_cookies,
        polite_sleep,
        redact,
        require_httpx,
        run_lessons,
        slugify,
    )


PLATFORM = "skool"
ORIGIN = "https://www.skool.com"


class _NextDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture = False
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.capture = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.capture:
            self.capture = False

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.parts.append(data)


def parse_next_data(page_html: str) -> dict:
    parser = _NextDataParser()
    parser.feed(page_html)
    if not parser.parts:
        raise RuntimeError("Skool page has no __NEXT_DATA__; session or page shape changed.")
    payload = json.loads("".join(parser.parts))
    page_props = ((payload.get("props") or {}).get("pageProps") or {})
    if not isinstance(page_props, dict):
        raise RuntimeError("Skool __NEXT_DATA__ has no pageProps object.")
    return page_props


def authenticate(cookies_path: str):
    require_httpx()
    cookies = parse_netscape_cookies(cookies_path)
    return httpx.Client(
        headers={
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Referer": ORIGIN + "/",
            "User-Agent": BROWSER_USER_AGENT,
        },
        cookies=httpx_cookie_jar(cookies),
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
    )


def fetch_page(client, url: str, rate: float) -> tuple[dict, str]:
    response = client.get(url)
    if response.status_code in {401, 403}:
        raise SystemExit(
            f"Skool rejected the exported session (HTTP {response.status_code}). "
            "Re-export cookies from www.skool.com while logged in."
        )
    response.raise_for_status()
    props = parse_next_data(response.text)
    polite_sleep(rate)
    return props, str(response.url)


def _node_title(node: dict) -> str:
    metadata = node.get("metadata") or {}
    return metadata.get("title") or node.get("name") or "Untitled"


def curriculum_nodes(course_wrapper: dict) -> tuple[dict, list[tuple[list[str], dict]]]:
    """Return the root course plus ordered leaf lesson nodes.

    Skool wraps each unit as {"course": <node>, "children": [...]}. Sets and
    sections become folders; module leaves become downloadable lessons.
    """
    root = course_wrapper.get("course") or {}
    leaves: list[tuple[list[str], dict]] = []

    def walk(wrapper: dict, parents: list[str]) -> None:
        node = wrapper.get("course") if isinstance(wrapper.get("course"), dict) else wrapper
        children = wrapper.get("children")
        if children is None and isinstance(node, dict):
            children = node.get("children")
        children = children or []
        if children:
            next_parents = parents
            if node is not root:
                next_parents = [*parents, slugify(_node_title(node))]
            for child in children:
                if isinstance(child, dict):
                    walk(child, next_parents)
            return
        if node is not root and isinstance(node, dict):
            leaves.append((parents, node))

    for child in course_wrapper.get("children") or []:
        if isinstance(child, dict):
            walk(child, [])
    return root, leaves


def _find_node(value: object, wanted_id: str) -> dict | None:
    if isinstance(value, dict):
        node = value.get("course") if isinstance(value.get("course"), dict) else value
        if str(node.get("id")) == wanted_id:
            return node
        for child in value.values():
            match = _find_node(child, wanted_id)
            if match:
                return match
    elif isinstance(value, list):
        for child in value:
            match = _find_node(child, wanted_id)
            if match:
                return match
    return None


def _tiptap_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    raw = value[4:] if value.startswith("[v2]") else value
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw.strip()

    parts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            kind = node.get("type")
            if kind == "text":
                parts.append(str(node.get("text") or ""))
            elif kind == "hardBreak":
                parts.append("\n")
            for child in node.get("content") or []:
                walk(child)
            if kind in {"paragraph", "heading", "bulletList", "orderedList", "listItem"}:
                parts.append("\n")
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(document)
    return "\n".join(line.strip() for line in "".join(parts).splitlines() if line.strip())


def _resource_links(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    links: list[str] = []
    if isinstance(value, list):
        for resource in value:
            if not isinstance(resource, dict):
                continue
            candidate = resource.get("url") or resource.get("link")
            if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                parsed = urlsplit(candidate)
                sensitive = {
                    "token",
                    "sig",
                    "signature",
                    "x-amz-signature",
                    "x-amz-credential",
                }
                query_names = {name.lower() for name in parse_qs(parsed.query)}
                if query_names & sensitive:
                    candidate = urlunsplit(
                        (parsed.scheme, parsed.netloc, parsed.path, "", "")
                    )
                links.append(candidate)
    return links


def _lesson_url(course_url: str, lesson_id: str) -> str:
    parsed = urlsplit(course_url)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode({"md": lesson_id}),
            "",
        )
    )


def _native_video_url(video: dict) -> str | None:
    playback_id = video.get("playbackId")
    token = video.get("playbackToken")
    if not playback_id or not token:
        return None
    path = f"/{quote(str(playback_id), safe='')}.m3u8"
    return urlunsplit(
        (
            "https",
            "stream.video.skool.com",
            path,
            urlencode({"token": str(token)}),
            "",
        )
    )


def enumerate_course(
    client,
    course_url: str,
    rate: float,
) -> tuple[str, str, list[Lesson]]:
    initial_props, final_url = fetch_page(client, course_url, rate)
    wrapper = initial_props.get("course") or {}
    if not isinstance(wrapper, dict):
        raise RuntimeError("Skool pageProps.course is missing.")
    root, nodes = curriculum_nodes(wrapper)
    metadata = root.get("metadata") or {}
    course_title = metadata.get("title") or root.get("name") or "Skool course"
    expected = metadata.get("numModules")
    if isinstance(expected, int) and expected > len(nodes):
        raise RuntimeError(
            f"Skool returned only {len(nodes)} of {expected} curriculum modules. "
            "Refusing a partial download; re-export the session and retry."
        )
    if not nodes:
        raise RuntimeError("Skool returned an empty curriculum.")

    current_md = (parse_qs(urlsplit(final_url).query).get("md") or [None])[0]
    counters: dict[tuple[str, ...], int] = defaultdict(int)
    lessons: list[Lesson] = []
    for path, summary in nodes:
        lesson_id = str(summary.get("id") or "")
        if not lesson_id:
            continue
        if lesson_id == current_md:
            props = initial_props
        else:
            props, _ = fetch_page(client, _lesson_url(final_url, lesson_id), rate)
        detail = _find_node(props.get("course") or {}, lesson_id) or summary
        lesson_metadata = detail.get("metadata") or {}
        title = _node_title(detail)
        video_url = lesson_metadata.get("videoLink")
        if not isinstance(video_url, str) or not video_url.startswith(("http://", "https://")):
            video_url = _native_video_url(props.get("video") or {})

        video = None
        drm = False
        if video_url:
            video = Asset(
                url=video_url,
                headers={
                    "Referer": final_url,
                    "User-Agent": BROWSER_USER_AGENT,
                },
                use_ytdlp=True,
            )
            if ".m3u8" in urlsplit(video_url).path.lower():
                drm = hls_has_drm(client, video)

        path_key = tuple(path)
        counters[path_key] += 1
        lessons.append(
            Lesson(
                path=list(path),
                order=counters[path_key],
                title=title,
                video=video,
                description=_tiptap_text(lesson_metadata.get("desc")),
                links=_resource_links(lesson_metadata.get("resources")),
                drm=drm,
            )
        )
    return course_title, final_url, lessons


def course_dir(args, course_url: str, title: str) -> Path:
    if args.out:
        return Path(args.out)
    parsed = urlsplit(course_url)
    parts = [part for part in parsed.path.split("/") if part]
    group = parts[0] if parts else "group"
    folder = args.course_slug or slugify(title)
    return (
        Path(__file__).resolve().parent.parent
        / "input"
        / PLATFORM
        / slugify(group)
        / folder
    )


def validate_course_url(value: str) -> None:
    parsed = urlsplit(value)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname not in {"skool.com", "www.skool.com"}:
        raise SystemExit("Expected a www.skool.com classroom URL.")
    if len(parts) < 3 or parts[1] != "classroom":
        raise SystemExit("Expected /<group>/classroom/<course> in the Skool URL.")


def run(args) -> int:
    normalize_download_arguments(args)
    validate_course_url(args.course_url)
    client = authenticate(args.cookies)
    try:
        try:
            title, final_url, lessons = enumerate_course(
                client,
                args.course_url,
                args.rate,
            )
        except SystemExit:
            raise
        except Exception as error:  # Never surface a signed playback query.
            raise SystemExit(f"Skool enumeration failed: {redact(error)}") from None
        return run_lessons(
            platform=PLATFORM,
            course_title=title,
            lessons=lessons,
            course_dir=course_dir(args, final_url, title),
            client=client,
            args=args,
        )
    finally:
        client.close()


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Download one authenticated Skool classroom course (Stage 0)."
    )
    parser.add_argument("course_url", help="www.skool.com/<group>/classroom/<course> URL.")
    add_download_arguments(parser, default_cookies="input/cookies-skool.txt")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
