from __future__ import annotations

import contextlib
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
from course_to_markdown import openrouter_client
from course_to_markdown.gemini_client import (
    TruncatedResponseError,
    check_truncated,
)
from course_to_markdown.pipeline import max_repeated_ngram
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

    def test_repetition_loop_is_detected_without_finish_reason(self) -> None:
        loop = "one two three four five six seven eight "
        self.assertGreaterEqual(max_repeated_ngram(loop * 60), 50)
        self.assertLess(
            max_repeated_ngram(
                "one two three four five six seven eight "
                "nine ten eleven twelve"
            ),
            50,
        )


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


class FakeRateLimitResponse:
    def __init__(self, text: str = "", headers: dict | None = None):
        self.text = text
        self.headers = headers or {}


class FakeTranscriptResponse:
    """A well-formed HTTP 200 chat completion carrying `content`."""

    status_code = 200
    text = ""
    headers: dict = {}

    def __init__(self, content: str):
        self._content = content

    def json(self) -> dict:
        return {"choices": [{"finish_reason": "stop",
                             "message": {"content": self._content}}]}


@contextlib.contextmanager
def _patched(*, post, duration: float):
    """Drive `transcribe_file` against a fake transport and a fake ffprobe reading.

    Yields a real temp chunk because the client reads the audio bytes off disk. Sleep is
    stubbed so retry tests don't actually wait out the backoff.
    """
    saved = (openrouter_client.httpx.post,
             openrouter_client.audio.probe_duration,
             openrouter_client.time.sleep)
    openrouter_client.httpx.post = post
    openrouter_client.audio.probe_duration = lambda _p: duration
    openrouter_client.time.sleep = lambda _s: None
    try:
        with tempfile.TemporaryDirectory() as temporary:
            chunk = Path(temporary) / "chunk_000.mp3"
            chunk.write_bytes(b"fake audio bytes")
            yield chunk
    finally:
        (openrouter_client.httpx.post,
         openrouter_client.audio.probe_duration,
         openrouter_client.time.sleep) = saved


class OpenRouterClientTests(unittest.TestCase):
    """The OpenRouter path is an LLM transcribing, so it can fail in ways a real STT
    endpoint cannot: succeed while dropping the audio, or succeed while truncated."""

    def test_good_response_returns_transcript(self) -> None:
        payload = {"choices": [{"finish_reason": "stop",
                                "message": {"content": "  Vamos começar a aula.  "}}]}
        self.assertEqual(
            openrouter_client._extract_text(payload, "xiaomi/mimo-v2.5"),
            "Vamos começar a aula.",
        )

    def test_http_200_with_no_choices_is_rejected(self) -> None:
        """A provider can return 200 carrying an error body; indexing it kills the batch."""
        payload = {"error": {"message": "upstream exploded"}}
        with self.assertRaises(RuntimeError) as ctx:
            openrouter_client._extract_text(payload, "xiaomi/mimo-v2.5")
        self.assertIn("no choices", str(ctx.exception))

    def test_truncated_generation_is_rejected(self) -> None:
        payload = {"choices": [{"finish_reason": "length",
                                "message": {"content": "partial transcript"}}]}
        with self.assertRaises(RuntimeError) as ctx:
            openrouter_client._extract_text(payload, "xiaomi/mimo-v2.5")
        self.assertIn("finish_reason", str(ctx.exception))

    def test_silently_dropped_audio_is_rejected(self) -> None:
        """nvidia/nemotron-*-omni:free returns HTTP 200 + finish=stop and a polite refusal
        when its provider discards the audio part. Density is the only signal."""
        original = openrouter_client.audio.probe_duration
        openrouter_client.audio.probe_duration = lambda _p: 600.0  # 10 min of audio
        try:
            with self.assertRaises(openrouter_client.AudioNotReceived):
                openrouter_client._assert_audio_was_received(
                    "Desculpe, não foi possível transcrever o áudio.",
                    Path("chunk_000.mp3"), "nvidia/nemotron-omni:free")
        finally:
            openrouter_client.audio.probe_duration = original

    def test_realistic_transcript_density_passes(self) -> None:
        original = openrouter_client.audio.probe_duration
        openrouter_client.audio.probe_duration = lambda _p: 600.0
        try:
            openrouter_client._assert_audio_was_received(
                " ".join(["palavra"] * 1800),  # 180 wpm over 10 min
                Path("chunk_000.mp3"), "xiaomi/mimo-v2.5")
        finally:
            openrouter_client.audio.probe_duration = original

    def test_unknown_duration_skips_the_density_guard(self) -> None:
        """No ffprobe reading -> no basis to judge; never fail a lesson on a missing probe."""
        original = openrouter_client.audio.probe_duration
        openrouter_client.audio.probe_duration = lambda _p: None
        try:
            openrouter_client._assert_audio_was_received(
                "short", Path("chunk_000.mp3"), "xiaomi/mimo-v2.5")
        finally:
            openrouter_client.audio.probe_duration = original

    def test_rate_limit_window_decides_stop_vs_retry(self) -> None:
        stop = FakeRateLimitResponse("rate limit exceeded: requests per day")
        retry = FakeRateLimitResponse("rate limit exceeded: requests per minute")
        long_wait = FakeRateLimitResponse("", {"retry-after": "3600"})
        short_wait = FakeRateLimitResponse("", {"retry-after": "12"})
        self.assertTrue(openrouter_client._rate_limit_stops_run(stop))
        self.assertFalse(openrouter_client._rate_limit_stops_run(retry))
        self.assertTrue(openrouter_client._rate_limit_stops_run(long_wait))
        self.assertFalse(openrouter_client._rate_limit_stops_run(short_wait))

    def test_dropped_audio_is_retried_and_recovers(self) -> None:
        """~7% of MiMo requests drop the audio. It is a per-request delivery fault, so the
        identical request usually succeeds on a retry -- retrying beats leaving a residue."""
        good = " ".join(["palavra"] * 1800)  # 180 wpm over 10 min
        replies = [
            FakeTranscriptResponse("I don't see an audio file attached to your message."),
            FakeTranscriptResponse(good),
        ]
        calls: list[int] = []

        def fake_post(*_args, **_kwargs):
            calls.append(1)
            return replies.pop(0)

        with _patched(post=fake_post, duration=600.0) as chunk:
            text = openrouter_client.transcribe_file(
                chunk, "xiaomi/mimo-v2.5", "Portuguese", "key")

        self.assertEqual(text, good)
        self.assertEqual(len(calls), 2, "should have retried exactly once")

    def test_persistently_dropped_audio_still_fails(self) -> None:
        """Retrying must not turn a real failure into a silent pass -- a file that never
        transcribes has to surface as an error, not as an apology written to disk."""
        drop = "I don't see an audio file attached to your message."

        def fake_post(*_args, **_kwargs):
            return FakeTranscriptResponse(drop)

        with _patched(post=fake_post, duration=600.0) as chunk:
            with self.assertRaises(openrouter_client.AudioNotReceived):
                openrouter_client.transcribe_file(
                    chunk, "xiaomi/mimo-v2.5", "Portuguese", "key", max_attempts=3)

    def test_audio_format_defaults_to_mp3(self) -> None:
        self.assertEqual(openrouter_client._audio_format(Path("a.mp3")), "mp3")
        self.assertEqual(openrouter_client._audio_format(Path("a.wav")), "wav")
        self.assertEqual(openrouter_client._audio_format(Path("a.m4a")), "mp3")


if __name__ == "__main__":
    unittest.main()
