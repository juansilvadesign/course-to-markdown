#!/usr/bin/env python3
"""Authenticated DesignBoost downloader (Stage 0).

Uses the student's exported `design-boost.auth_token` cookie against the same
JSON API used by aluno.designboost.com.br. It supports courses, workshops,
single classes/lives, and the AI catalog. Vimeo media is delegated to yt-dlp;
only the smallest audio rendition is kept by default.

Examples (run from the course-to-markdown root):

    .venv/bin/python downloaders/designboost.py --list
    .venv/bin/python downloaders/designboost.py --all courses --limit 1 --dry-run
    .venv/bin/python downloaders/designboost.py \
      "https://aluno.designboost.com.br/sala-de-aula/32/491?type=course" --dry-run

Only use this with content your account is entitled to access. This script does
not automate login and never attempts to bypass DRM.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

try:
    from ._shared import (
        Asset,
        BROWSER_USER_AGENT,
        HTTP_TIMEOUT,
        Lesson,
        add_download_arguments,
        cookie_value,
        httpx,
        log,
        normalize_download_arguments,
        parse_netscape_cookies,
        polite_sleep,
        redact,
        require_httpx,
        run_lessons,
        slugify,
    )
except ImportError:  # Direct script execution: python downloaders/designboost.py
    from _shared import (  # type: ignore[no-redef]
        Asset,
        BROWSER_USER_AGENT,
        HTTP_TIMEOUT,
        Lesson,
        add_download_arguments,
        cookie_value,
        httpx,
        log,
        normalize_download_arguments,
        parse_netscape_cookies,
        polite_sleep,
        redact,
        require_httpx,
        run_lessons,
        slugify,
    )


PLATFORM = "designboost"
API_BASE = "https://api.designboost.com.br/student"
MEMBER_ORIGIN = "https://aluno.designboost.com.br"
COLLECTIONS = ("courses", "workshops", "single-classes", "ai-classes")
TYPE_ALIASES = {
    "course": "courses",
    "courses": "courses",
    "imersao": "courses",
    "workshop": "workshops",
    "workshops": "workshops",
    "live": "single-classes",
    "single": "single-classes",
    "single-class": "single-classes",
    "single-classes": "single-classes",
    "ai": "ai-classes",
    "ia": "ai-classes",
    "ai-class": "ai-classes",
    "ai-classes": "ai-classes",
}


def authenticate(cookies_path: str):
    require_httpx()
    cookies = parse_netscape_cookies(cookies_path)
    encoded_token = cookie_value(cookies, "design-boost.auth_token")
    if not encoded_token:
        raise SystemExit(
            "The DesignBoost export has no `design-boost.auth_token`. Re-export "
            "cookies while logged in at aluno.designboost.com.br."
        )
    token = unquote(encoded_token)
    return httpx.Client(
        base_url=API_BASE,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Origin": MEMBER_ORIGIN,
            "Referer": MEMBER_ORIGIN + "/",
            "User-Agent": BROWSER_USER_AGENT,
        },
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
    )


def api_get(client, endpoint: str, rate: float) -> dict:
    response = client.get(endpoint)
    if response.status_code == 401:
        raise SystemExit(
            "DesignBoost rejected the exported session (HTTP 401). Re-export "
            "cookies from aluno.designboost.com.br while logged in."
        )
    response.raise_for_status()
    payload = response.json()
    polite_sleep(rate)
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def list_collection(client, collection: str, rate: float) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        response = client.get(
            f"/{collection}",
            params={"page": page, "per_page": 100},
        )
        if response.status_code == 401:
            raise SystemExit(
                "DesignBoost rejected the exported session (HTTP 401). Re-export "
                "cookies from aluno.designboost.com.br while logged in."
            )
        response.raise_for_status()
        payload = response.json()
        page_items = payload.get("data", []) if isinstance(payload, dict) else []
        items.extend(item for item in page_items if isinstance(item, dict))
        last_page = int(payload.get("last_page") or page)
        polite_sleep(rate)
        if page >= last_page:
            return items
        page += 1


def list_catalog(client, rate: float) -> dict[str, list[dict]]:
    return {
        collection: list_collection(client, collection, rate)
        for collection in COLLECTIONS
    }


def print_catalog(catalog: dict[str, list[dict]]) -> None:
    for collection, items in catalog.items():
        log(f"\n=== {collection} ({len(items)}) ===")
        for item in items:
            blocked = "  [LOCKED]" if item.get("is_blocked") else ""
            log(f"  #{item.get('id')!s:<4} {item.get('name', '')}{blocked}")
    log(f"\ntotal: {sum(len(items) for items in catalog.values())}")


def _plain_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _video_asset(video_url: object) -> Asset | None:
    if not isinstance(video_url, str) or not video_url.startswith(("http://", "https://")):
        return None
    return Asset(
        url=video_url,
        headers={
            "Referer": MEMBER_ORIGIN + "/",
            "User-Agent": BROWSER_USER_AGENT,
        },
        use_ytdlp=True,
    )


def enumerate_content(
    client,
    collection: str,
    content_id: int,
    rate: float,
) -> tuple[str, list[Lesson]]:
    if collection == "single-classes":
        detail = api_get(client, f"/single-classes/{content_id}", rate)
        title = detail.get("name") or f"single-class-{content_id}"
        return title, [
            Lesson(
                path=[],
                order=1,
                title=title,
                video=_video_asset(detail.get("video_url")),
                description=_plain_text(detail.get("description")),
            )
        ]

    detail_collection = "courses" if collection in {"courses", "ai-classes"} else "workshops"
    detail = api_get(client, f"/{detail_collection}/{content_id}", rate)
    title = detail.get("name") or f"{collection}-{content_id}"
    lessons: list[Lesson] = []
    modules = detail.get("modules") or []
    for module_index, module in enumerate(modules, 1):
        if not isinstance(module, dict) or module.get("is_blocked"):
            continue
        module_title = module.get("name") or f"Module {module_index}"
        path = [f"{module_index:02d}-{slugify(module_title)}"]
        for lesson_index, summary in enumerate(module.get("classes") or [], 1):
            if not isinstance(summary, dict) or summary.get("is_blocked"):
                continue
            lesson_id = summary.get("id")
            if lesson_id is None:
                continue
            lesson = api_get(client, f"/classes/{lesson_id}", rate)
            lesson_title = lesson.get("name") or summary.get("name") or f"Class {lesson_id}"
            lessons.append(
                Lesson(
                    path=path,
                    order=lesson_index,
                    title=lesson_title,
                    video=_video_asset(lesson.get("video_url")),
                    description=_plain_text(lesson.get("description")),
                )
            )

    if not lessons and detail.get("video_url"):
        lessons.append(
            Lesson(
                path=[],
                order=1,
                title=title,
                video=_video_asset(detail.get("video_url")),
                description=_plain_text(detail.get("description")),
            )
        )
    if not lessons:
        raise RuntimeError(
            f"{collection}/{content_id} returned no accessible classes; refusing "
            "to write a false-success manifest"
        )
    return title, lessons


def _catalog_match(
    client,
    content_id: int,
    type_hint: str | None,
    rate: float,
) -> str:
    if type_hint and type_hint in TYPE_ALIASES:
        return TYPE_ALIASES[type_hint]
    matches: list[str] = []
    for collection, items in list_catalog(client, rate).items():
        if any(str(item.get("id")) == str(content_id) for item in items):
            matches.append(collection)
    if not matches:
        raise SystemExit(
            f"Content #{content_id} is not present in the authenticated DesignBoost catalogs."
        )
    if len(matches) > 1:
        raise SystemExit(
            f"Content #{content_id} exists in multiple catalogs ({', '.join(matches)}). "
            "Use the classroom URL with its ?type= parameter."
        )
    return matches[0]


def parse_content_ref(client, value: str, rate: float) -> tuple[str, int]:
    if value.isdigit():
        content_id = int(value)
        return _catalog_match(client, content_id, None, rate), content_id

    parsed = urlsplit(value)
    if not parsed.hostname or not parsed.hostname.endswith("designboost.com.br"):
        raise SystemExit("Expected a DesignBoost classroom URL or numeric content ID.")
    parts = [part for part in parsed.path.split("/") if part]
    if "sala-de-aula" not in parts:
        raise SystemExit(
            "The DesignBoost public/member root is a catalog, not one course. "
            "Use --list, --all <type>, or a /sala-de-aula/<id> URL."
        )
    index = parts.index("sala-de-aula")
    if index + 1 >= len(parts) or not parts[index + 1].isdigit():
        raise SystemExit("The classroom URL does not contain a numeric content ID.")
    content_id = int(parts[index + 1])
    query = parse_qs(parsed.query)
    type_hint = (query.get("type") or [None])[0]
    return _catalog_match(client, content_id, type_hint, rate), content_id


def course_dir(args, collection: str, content_id: int, title: str) -> Path:
    if args.out:
        return Path(args.out)
    folder = args.course_slug or slugify(title)
    root = Path(__file__).resolve().parent.parent / "input" / PLATFORM
    return root / collection / f"{content_id}-{folder}"


def run_one(args, client, collection: str, content_id: int) -> int:
    title, lessons = enumerate_content(client, collection, content_id, args.rate)
    return run_lessons(
        platform=PLATFORM,
        course_title=title,
        lessons=lessons,
        course_dir=course_dir(args, collection, content_id, title),
        client=client,
        args=args,
    )


def run(args) -> int:
    normalize_download_arguments(args)
    client = authenticate(args.cookies)
    try:
        if args.list_only:
            print_catalog(list_catalog(client, args.rate))
            return 0
        if args.all:
            collections = COLLECTIONS if args.all == "all" else (args.all,)
            queue: list[tuple[str, dict]] = []
            for collection in collections:
                queue.extend(
                    (collection, item)
                    for item in list_collection(client, collection, args.rate)
                    if not item.get("is_blocked")
                )
            if args.limit:
                queue = queue[: args.limit]
            if args.out or args.course_slug:
                raise SystemExit("--out/--course-slug cannot be combined with --all.")
            log(f"[{PLATFORM}] batch: {len(queue)} content item(s)")
            failed_items = 0
            for index, (collection, item) in enumerate(queue, 1):
                content_id = int(item["id"])
                log(f"\n───── [{index}/{len(queue)}] {collection}/{content_id} ─────")
                try:
                    failed_items += bool(run_one(args, client, collection, content_id))
                except KeyboardInterrupt:
                    raise
                except Exception as error:  # noqa: BLE001 - keep a catalog batch resumable.
                    failed_items += 1
                    log(f"  ! item failed: {collection}/{content_id}: {redact(error)}")
            return 1 if failed_items else 0

        collection, content_id = parse_content_ref(client, args.course_url, args.rate)
        return 1 if run_one(args, client, collection, content_id) else 0
    finally:
        client.close()


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Download authenticated DesignBoost courses (Stage 0)."
    )
    parser.add_argument(
        "course_url",
        nargs="?",
        help="aluno.designboost.com.br classroom URL or numeric content ID.",
    )
    parser.add_argument("--list", dest="list_only", action="store_true")
    parser.add_argument(
        "--all",
        choices=(*COLLECTIONS, "all"),
        help="Download one authenticated catalog (or all catalogs), sequentially.",
    )
    parser.add_argument("--limit", type=int, help="With --all, process at most N items.")
    add_download_arguments(
        parser,
        default_cookies="input/cookies-designboost.txt",
    )
    args = parser.parse_args(argv)
    selected = sum(bool(value) for value in (args.course_url, args.list_only, args.all))
    if selected != 1:
        parser.error("choose exactly one course URL/ID, --list, or --all <type>.")
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
