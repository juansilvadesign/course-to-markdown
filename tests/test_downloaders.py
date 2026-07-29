from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from downloaders import designboost, skool
from downloaders._shared import (
    Asset,
    diagnostic_indicates_drm,
    hls_has_drm,
    parse_netscape_cookies,
    redact,
    safe_url,
)
from course_to_markdown.gemini_client import (
    TruncatedResponseError,
    check_truncated,
)
from scripts.transcribe_batches import (
    discover_batches,
    missing_transcripts,
    validate_batch,
)


class FakeResponse:
    def __init__(self, payload=None, *, text: str = "", status_code: int = 200):
        self._payload = payload
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, responses: dict[str, FakeResponse]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, endpoint: str, **_kwargs):
        self.calls.append(endpoint)
        return self.responses[endpoint]


class SharedDownloaderTests(unittest.TestCase):
    def test_netscape_parser_accepts_http_only_and_preserves_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cookie_file = Path(temporary) / "cookies.txt"
            cookie_file.write_text(
                "# Netscape HTTP Cookie File\n"
                "#HttpOnly_.example.com\tTRUE\t/\tTRUE\t2000000000\tsession\ta%2Fb\n",
                encoding="utf-8",
            )
            cookies = parse_netscape_cookies(cookie_file)
        self.assertEqual(cookies[0].domain, ".example.com")
        self.assertEqual(cookies[0].name, "session")
        self.assertEqual(cookies[0].value, "a%2Fb")

    def test_signed_urls_are_redacted_for_logs(self) -> None:
        value = "https://stream.example/video.m3u8?token=secret&sig=also-secret"
        self.assertNotIn("secret", redact(value))
        self.assertEqual(safe_url(value), "https://stream.example/video.m3u8")
        self.assertNotIn(
            "top-secret",
            redact("Authorization: Bearer top-secret\nCookie: sid=top-secret"),
        )

    def test_drm_guard_distinguishes_plain_aes_from_commercial_drm(self) -> None:
        plain = FakeClient(
            {
                "https://example.test/plain.m3u8": FakeResponse(
                    text="#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"key.bin\""
                )
            }
        )
        drm = FakeClient(
            {
                "https://example.test/drm.m3u8": FakeResponse(
                    text="#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,"
                    'KEYFORMAT="com.apple.streamingkeydelivery"'
                )
            }
        )
        self.assertFalse(
            hls_has_drm(plain, Asset("https://example.test/plain.m3u8"))
        )
        self.assertTrue(
            hls_has_drm(drm, Asset("https://example.test/drm.m3u8"))
        )
        self.assertTrue(diagnostic_indicates_drm("This video is DRM protected"))
        self.assertFalse(diagnostic_indicates_drm("ordinary extractor failure"))
        self.assertNotIn(
            "secret-token",
            redact(
                "ERROR: unable to download "
                "https://cdn.example.test/video.m3u8?token=secret-token"
            ),
        )
        self.assertEqual(
            redact(
                "ERROR https://cdn.example.test/video.m3u8"
                "?Policy=opaque&Key-Pair-Id=also-opaque"
            ),
            "ERROR https://cdn.example.test/video.m3u8?<redacted>",
        )

    def test_truncated_model_output_is_rejected(self) -> None:
        class FinishReason:
            name = "MAX_TOKENS"

        class Candidate:
            finish_reason = FinishReason()

        class Response:
            candidates = [Candidate()]

        with self.assertRaises(TruncatedResponseError):
            check_truncated(Response(), "transcription")


class DesignBoostTests(unittest.TestCase):
    def test_html_description_becomes_readable_text(self) -> None:
        self.assertEqual(
            designboost._plain_text("<p>First &amp; second</p><p>Third</p>"),
            "First & second\nThird",
        )

    def test_course_modules_resolve_ordered_class_details(self) -> None:
        client = FakeClient(
            {
                "/courses/7": FakeResponse(
                    {
                        "id": 7,
                        "name": "Course",
                        "modules": [
                            {
                                "id": 1,
                                "name": "Start",
                                "classes": [
                                    {"id": 10, "name": "Welcome", "is_blocked": False},
                                    {"id": 11, "name": "Locked", "is_blocked": True},
                                ],
                            }
                        ],
                    }
                ),
                "/classes/10": FakeResponse(
                    {
                        "id": 10,
                        "name": "Welcome",
                        "description": "<p>Hello</p>",
                        "video_url": "https://vimeo.com/123",
                    }
                ),
            }
        )
        title, lessons = designboost.enumerate_content(client, "courses", 7, 0)
        self.assertEqual(title, "Course")
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0].lesson_id(), "01-start/01-welcome")
        self.assertEqual(lessons[0].description, "Hello")
        self.assertEqual(
            client.calls,
            ["/courses/7", "/classes/10"],
        )


class SkoolTests(unittest.TestCase):
    def test_next_data_parser_extracts_page_props(self) -> None:
        payload = {"props": {"pageProps": {"course": {"children": []}}}}
        page = (
            '<html><script id="__NEXT_DATA__" type="application/json">'
            f"{json.dumps(payload)}</script></html>"
        )
        self.assertEqual(skool.parse_next_data(page), payload["props"]["pageProps"])

    def test_curriculum_flattens_sets_but_not_course_title(self) -> None:
        wrapper = {
            "course": {
                "id": "root",
                "unitType": "course",
                "metadata": {"title": "Course"},
            },
            "children": [
                {
                    "course": {
                        "id": "set",
                        "unitType": "set",
                        "metadata": {"title": "Part One"},
                    },
                    "children": [
                        {
                            "course": {
                                "id": "lesson",
                                "unitType": "module",
                                "metadata": {"title": "Lesson"},
                            }
                        }
                    ],
                }
            ],
        }
        root, leaves = skool.curriculum_nodes(wrapper)
        self.assertEqual(root["id"], "root")
        self.assertEqual(leaves[0][0], ["part-one"])
        self.assertEqual(leaves[0][1]["id"], "lesson")

    def test_native_video_url_keeps_token_internal(self) -> None:
        url = skool._native_video_url(
            {"playbackId": "playback/id", "playbackToken": "signed.value"}
        )
        self.assertIsNotNone(url)
        parsed = urlsplit(url or "")
        self.assertEqual(parsed.hostname, "stream.video.skool.com")
        self.assertEqual(parse_qs(parsed.query)["token"], ["signed.value"])
        self.assertNotIn("signed.value", safe_url(url or ""))

    def test_resource_links_drop_signed_queries(self) -> None:
        resources = json.dumps(
            [
                {
                    "url": "https://files.example/guide.pdf"
                    "?X-Amz-Signature=secret&X-Amz-Credential=credential"
                }
            ]
        )
        self.assertEqual(
            skool._resource_links(resources),
            ["https://files.example/guide.pdf"],
        )

    def test_tiptap_v2_description_becomes_text(self) -> None:
        document = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "world"}],
                },
            ],
        }
        self.assertEqual(
            skool._tiptap_text("[v2]" + json.dumps(document)),
            "Hello\nworld",
        )


class TranscriptionFanoutTests(unittest.TestCase):
    def test_discovers_only_direct_media_courses_and_rejects_dirty_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_root = root / "input"
            output_root = root / "output"
            clean = input_root / "clean"
            dirty = input_root / "dirty"
            empty = input_root / "empty"
            for directory in (clean, dirty, empty):
                directory.mkdir(parents=True)
            (clean / "lesson.m4a").write_bytes(b"media")
            (clean / "manifest.json").write_text(
                json.dumps({"lessons": {"lesson": {"status": "done"}}}),
                encoding="utf-8",
            )
            (dirty / "lesson.m4a").write_bytes(b"media")
            (dirty / "lesson.m4a.part").write_bytes(b"partial")
            (dirty / "manifest.json").write_text(
                json.dumps({"lessons": {"lesson": {"status": "failed"}}}),
                encoding="utf-8",
            )

            batches = discover_batches(input_root, output_root)
            clean_problems = validate_batch(batches[0])
            dirty_problems = validate_batch(batches[1])
            missing_before = missing_transcripts(batches[0])
            transcript = output_root / "clean" / "lesson.transcript.txt"
            transcript.parent.mkdir(parents=True)
            transcript.write_text("done", encoding="utf-8")
            missing_after = missing_transcripts(batches[0])

        self.assertEqual([batch.name for batch in batches], ["clean", "dirty"])
        self.assertEqual(clean_problems, [])
        self.assertEqual(missing_before, [Path("lesson.m4a")])
        self.assertEqual(missing_after, [])
        self.assertEqual(
            dirty_problems,
            ["1 partial download(s)", "1 failed manifest lesson(s)"],
        )


if __name__ == "__main__":
    unittest.main()
