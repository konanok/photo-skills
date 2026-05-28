"""Tests for photo-previewer."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

# preview.py is in the same directory; make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from preview import (  # noqa: E402
    build_app,
    build_session_manifest,
    detect_mode,
    discover_sessions,
    grid_columns_for,
    load_config,
    main,
    make_handler,
    match_graded_to_style,
    start_server,
)


class TestDetectMode(unittest.TestCase):
    def test_session_mode_when_grading_params_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "20260528-100000"
            session.mkdir()
            (session / "grading_params.json").write_text("[]")
            self.assertEqual(detect_mode(session), "session")

    def test_browse_mode_when_subdirs_have_grading_params(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "RAW-2026-spring"
            project.mkdir()
            for sid in ("20260528-100000", "20260528-110000"):
                s = project / sid
                s.mkdir()
                (s / "grading_params.json").write_text("[]")
            self.assertEqual(detect_mode(project), "browse")

    def test_raises_when_neither_session_nor_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            with self.assertRaises(ValueError):
                detect_mode(empty)

    def test_raises_when_path_not_exists(self):
        with self.assertRaises(FileNotFoundError):
            detect_mode(Path("/nonexistent/path/xyz123-photo-previewer-test"))

    def test_raises_when_path_is_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "file.txt"
            f.write_text("hi")
            with self.assertRaises(NotADirectoryError):
                detect_mode(f)


class TestMatchGradedToStyle(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(
            match_graded_to_style("DSC_0001_暖春丝滑.jpg"),
            ("DSC_0001", "暖春丝滑"),
        )

    def test_subdir_prefix(self):
        # convert.py 子目录前缀格式：001_DSC_0001_暖春丝滑.jpg
        # 规则：rpartition 一次，最后一段是 style，前面整体是 stem
        self.assertEqual(
            match_graded_to_style("001_DSC_0001_暖春丝滑.jpg"),
            ("001_DSC_0001", "暖春丝滑"),
        )

    def test_style_with_underscore(self):
        # rpartition 一次：style 取最后一段，stem 是前面整体
        self.assertEqual(
            match_graded_to_style("DSC_0001_warm_spring.jpg"),
            ("DSC_0001_warm", "spring"),
        )

    def test_no_underscore_falls_back(self):
        # 文件名无下划线：整个 stem 是 stem，style 为 None
        self.assertEqual(
            match_graded_to_style("photo.jpg"),
            ("photo", None),
        )

    def test_jpeg_extension(self):
        self.assertEqual(
            match_graded_to_style("DSC_0001_暖春丝滑.jpeg"),
            ("DSC_0001", "暖春丝滑"),
        )


class TestGridColumns(unittest.TestCase):
    def test_desktop_buckets(self):
        cases = {1: 1, 2: 2, 3: 2, 4: 2, 5: 3, 9: 3, 10: 4, 16: 4, 17: 4, 100: 4}
        for n, cols in cases.items():
            with self.subTest(n=n):
                self.assertEqual(grid_columns_for(n), cols)

    def test_desktop_zero(self):
        self.assertEqual(grid_columns_for(0), 1)


def _make_session_fixture(tmp: Path) -> Path:
    """Create a minimal session: 2 photos × 2 styles + grading_params.json.

    Returns the session directory path.
    """
    session = tmp / "20260528-100000"
    session.mkdir()
    graded = session / "graded"
    graded.mkdir()
    (graded / "DSC_0001_暖春丝滑.jpg").write_bytes(b"fake-jpg-1")
    (graded / "DSC_0002_暖春丝滑.jpg").write_bytes(b"fake-jpg-2")
    (graded / "DSC_0001_胶片冷调.jpg").write_bytes(b"fake-jpg-3")
    (graded / "DSC_0002_胶片冷调.jpg").write_bytes(b"fake-jpg-4")
    params = [
        {"file": "/raw/DSC_0001.NEF", "style": "暖春丝滑"},
        {"file": "/raw/DSC_0002.NEF", "style": "暖春丝滑"},
        {"file": "/raw/DSC_0001.NEF", "style": "胶片冷调"},
        {"file": "/raw/DSC_0002.NEF", "style": "胶片冷调"},
    ]
    (session / "grading_params.json").write_text(json.dumps(params))
    return session


class TestBuildSessionManifest(unittest.TestCase):
    def test_basic_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = _make_session_fixture(Path(tmp))
            m = build_session_manifest(session)
            self.assertEqual(m["session_id"], "20260528-100000")
            self.assertEqual(set(m["styles"]), {"暖春丝滑", "胶片冷调"})
            self.assertEqual(len(m["cells_by_style"]["暖春丝滑"]), 2)
            for cell in m["cells_by_style"]["暖春丝滑"]:
                self.assertIn("stem", cell)
                self.assertIn("graded_filename", cell)
                self.assertIn("original_path", cell)
                self.assertFalse(cell["graded_missing"])

    def test_missing_graded_file_marks_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = _make_session_fixture(Path(tmp))
            (session / "graded" / "DSC_0001_暖春丝滑.jpg").unlink()
            m = build_session_manifest(session)
            cell = next(c for c in m["cells_by_style"]["暖春丝滑"] if c["stem"] == "DSC_0001")
            self.assertTrue(cell["graded_missing"])
            # Sibling cell still fine
            sibling = next(c for c in m["cells_by_style"]["暖春丝滑"] if c["stem"] == "DSC_0002")
            self.assertFalse(sibling["graded_missing"])

    def test_empty_graded_dir_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = _make_session_fixture(Path(tmp))
            for f in (session / "graded").iterdir():
                f.unlink()
            with self.assertRaises(ValueError) as ctx:
                build_session_manifest(session)
            self.assertIn("graded", str(ctx.exception).lower())

    def test_no_grading_params_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "s"
            session.mkdir()
            with self.assertRaises(FileNotFoundError):
                build_session_manifest(session)

    def test_subdir_prefix_fallback(self):
        """When graded files carry a subdirectory prefix (e.g. ``001_DSC_0001_<style>.jpg``)
        but ``grading_params.json`` references ``DSC_0001.NEF``, the fallback
        ``a_stem.endswith("_" + stem)`` must still resolve the match.
        """
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "20260528-100000"
            session.mkdir()
            graded = session / "graded"
            graded.mkdir()
            # Subdirectory-prefix flavour: the actual on-disk filename
            # has "001_" prepended (as photo-grader writes when RAW lives
            # in a subdir under --raw-dir).
            (graded / "001_DSC_0001_暖春丝滑.jpg").write_bytes(b"x")
            params = [{"file": "/raw/DSC_0001.NEF", "style": "暖春丝滑"}]
            (session / "grading_params.json").write_text(json.dumps(params))

            m = build_session_manifest(session)
            cells = m["cells_by_style"]["暖春丝滑"]
            self.assertEqual(len(cells), 1)
            self.assertFalse(cells[0]["graded_missing"])
            self.assertEqual(cells[0]["graded_filename"], "001_DSC_0001_暖春丝滑.jpg")
            # Original stem from params is preserved (not the prefixed variant)
            self.assertEqual(cells[0]["stem"], "DSC_0001")


class TestDiscoverSessions(unittest.TestCase):
    def test_lists_subdirs_with_grading_params_sorted_desc(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "RAW-spring"
            project.mkdir()
            for sid in ("20260528-100000", "20260528-110000", "20260527-090000"):
                s = project / sid
                s.mkdir()
                (s / "grading_params.json").write_text("[]")
            # Subdir without grading_params.json must be ignored.
            (project / "no-params").mkdir()
            sessions = discover_sessions(project)
            ids = [s["session_id"] for s in sessions]
            # YYYYMMDD-HHMMSS lexicographic desc == time desc
            self.assertEqual(ids, ["20260528-110000", "20260528-100000", "20260527-090000"])
            # Each entry includes a Path
            for entry in sessions:
                self.assertIsInstance(entry["path"], Path)
                self.assertTrue(entry["path"].is_dir())

    def test_empty_when_no_session_subdirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "empty"
            project.mkdir()
            self.assertEqual(discover_sessions(project), [])


_SCRIPT = Path(__file__).resolve().parent / "preview.py"


class TestCLIFailFast(unittest.TestCase):
    """End-to-end CLI tests that invoke ``preview.py`` as a subprocess.

    Verifies fail-fast behaviour for invalid inputs *before* any HTTP server
    is started. All cases here exercise the ``detect_mode`` raises path
    (nonexistent / non-directory / neither-session-nor-root), so ``main()``
    returns 2 immediately and the foreground ``serve_forever()`` is never
    reached — that's why the subprocess tests stay fast despite the script
    now containing a real server.
    """

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_SCRIPT), *args],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_no_args_exits_nonzero(self):
        r = self._run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage", (r.stderr + r.stdout).lower())

    def test_nonexistent_path_fails(self):
        r = self._run("/definitely/does/not/exist/xyz123-photo-previewer-test")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not", r.stderr.lower())

    def test_path_is_file_fails(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"hi")
            path = tf.name
        try:
            r = self._run(path)
            self.assertNotEqual(r.returncode, 0)
        finally:
            Path(path).unlink()

    def test_neither_session_nor_root_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self._run(tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("session", r.stderr.lower())


class TestServerStartup(unittest.TestCase):
    """Verify that the server can build an app, start, serve /api/manifest,
    and shut down cleanly. End-to-end smoke test for Task 2.2.
    """

    def test_session_mode_starts_and_serves_root_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "20260528-100000"
            session.mkdir()
            (session / "grading_params.json").write_text('[{"file":"/raw/X.NEF","style":"S"}]')
            graded = session / "graded"
            graded.mkdir()
            (graded / "X_S.jpg").write_bytes(b"x")

            app = build_app(session, mode="session")
            self.assertEqual(app["mode"], "session")
            self.assertEqual(app["default_session_id"], "20260528-100000")

            server, url = start_server(app, port=0)
            try:
                # Tiny pause to let the daemon thread bind and accept
                time.sleep(0.05)
                with urllib.request.urlopen(url + "/api/manifest", timeout=2) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read())
                    self.assertEqual(body["mode"], "session")
            finally:
                server.shutdown()
                server.server_close()

    def test_browse_mode_app_lazy_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "RAW-spring"
            project.mkdir()
            for sid in ("20260528-100000", "20260528-110000"):
                s = project / sid
                s.mkdir()
                (s / "grading_params.json").write_text("[]")
            app = build_app(project, mode="browse")
            self.assertEqual(app["mode"], "browse")
            self.assertIsNone(app["default_session_id"])
            self.assertEqual(set(app["sessions"].keys()), {"20260528-100000", "20260528-110000"})
            # Lazily — manifest is None until first access
            for entry in app["sessions"].values():
                self.assertIsNone(entry["manifest"])


def _make_browse_fixture(tmp: Path) -> Path:
    """Project with 2 sessions, each 1 photo × 1 style, no thumbnails."""
    project = tmp / "RAW-spring"
    project.mkdir()
    for sid, fname in (("20260528-100000", "A"), ("20260528-110000", "B")):
        s = project / sid
        s.mkdir()
        (s / "graded").mkdir()
        (s / "graded" / f"{fname}_S.jpg").write_bytes(b"jpg-" + fname.encode())
        (s / "grading_params.json").write_text(json.dumps([{"file": f"/raw/{fname}.NEF", "style": "S"}]))
    return project


class TestRoutes(unittest.TestCase):
    """Full route-table coverage for Task 2.3."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = _make_browse_fixture(Path(self.tmp.name))
        self.app = build_app(self.project, mode="browse")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        Thread(target=self.server.serve_forever, daemon=True).start()
        time.sleep(0.05)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    # ── /api/manifest (browse) ─────────────────────────────────────
    def test_root_lists_sessions_browse_mode(self):
        with urllib.request.urlopen(self.url + "/api/manifest", timeout=2) as r:
            body = json.loads(r.read())
            self.assertEqual(body["mode"], "browse")
            ids = [s["session_id"] for s in body["sessions"]]
            # Newest-first order
            self.assertEqual(ids, ["20260528-110000", "20260528-100000"])

    # ── /api/manifest/<sid> ────────────────────────────────────────
    def test_session_manifest_lazy_loaded(self):
        sid = "20260528-100000"
        # Pre-condition: manifest still None before request
        self.assertIsNone(self.app["sessions"][sid]["manifest"])
        with urllib.request.urlopen(self.url + f"/api/manifest/{sid}", timeout=2) as r:
            body = json.loads(r.read())
            self.assertEqual(body["session_id"], sid)
            self.assertIn("S", body["cells_by_style"])
        # Post-condition: cached
        self.assertIsNotNone(self.app["sessions"][sid]["manifest"])

    def test_session_manifest_404_for_unknown_sid(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url + "/api/manifest/nonexistent", timeout=2)
        self.assertEqual(ctx.exception.code, 404)

    # ── /img/<sid>/graded/<style>/<stem> ──────────────────────────
    def test_img_graded_serves_jpg_bytes(self):
        sid = "20260528-100000"
        with urllib.request.urlopen(self.url + f"/img/{sid}/graded/S/A", timeout=2) as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers.get("Content-Type"), "image/jpeg")
            self.assertEqual(r.read(), b"jpg-A")

    def test_img_graded_404_for_unknown_stem(self):
        sid = "20260528-100000"
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url + f"/img/{sid}/graded/S/NOPE", timeout=2)
        self.assertEqual(ctx.exception.code, 404)

    # ── /img/<sid>/original/<stem> ────────────────────────────────
    def test_img_original_404_when_thumbnail_missing(self):
        # Fixture never created any thumbnails, so this should always 404
        sid = "20260528-100000"
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url + f"/img/{sid}/original/A", timeout=2)
        self.assertEqual(ctx.exception.code, 404)

    def test_img_original_serves_thumbnail_when_present(self):
        # Synthesize a thumbnail at the conventional location and verify the
        # server returns it. Note: original_path in params is /raw/A.NEF, so
        # the conventional thumbnail path is /raw/thumbnails/A.jpg — we can
        # not write under /raw, so re-craft the fixture to reference an
        # in-tree raw dir instead.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            raw_dir = Path(tmp) / "raw"
            raw_dir.mkdir()
            thumbs = raw_dir / "thumbnails"
            thumbs.mkdir()
            (thumbs / "A.jpg").write_bytes(b"thumb-A-bytes")
            sid = "20260528-100000"
            s = project / sid
            s.mkdir()
            (s / "graded").mkdir()
            (s / "graded" / "A_S.jpg").write_bytes(b"jpg-A")
            (s / "grading_params.json").write_text(json.dumps([{"file": str(raw_dir / "A.NEF"), "style": "S"}]))
            app = build_app(project, mode="browse")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            url = f"http://127.0.0.1:{server.server_address[1]}"
            Thread(target=server.serve_forever, daemon=True).start()
            try:
                time.sleep(0.05)
                with urllib.request.urlopen(url + f"/img/{sid}/original/A", timeout=2) as r:
                    self.assertEqual(r.status, 200)
                    self.assertEqual(r.read(), b"thumb-A-bytes")
            finally:
                server.shutdown()
                server.server_close()


class TestConfigLoading(unittest.TestCase):
    """Verify config.toml resolution and CLI-precedence behaviour."""

    def test_load_config_returns_empty_when_path_missing(self):
        self.assertEqual(load_config("/nonexistent/path/photo-previewer-config.toml"), {})

    def test_load_config_reads_flat_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.toml"
            cfg_path.write_text(
                'port = 8765\nexternal_url = "https://example.com/preview/"\n',
                encoding="utf-8",
            )
            cfg = load_config(cfg_path)
            self.assertEqual(cfg["port"], 8765)
            self.assertEqual(cfg["external_url"], "https://example.com/preview/")

    def test_load_config_ignores_malformed_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.toml"
            cfg_path.write_text("port = not-a-number-this-is-bad-toml = =", encoding="utf-8")
            # Should not raise — invalid TOML logs a warning to stderr and
            # returns {} so the previewer can still run on CLI flags alone.
            self.assertEqual(load_config(cfg_path), {})

    def test_external_url_from_cli_overrides_internal(self):
        """When --external-url is given, the startup banner uses it instead
        of the internal http://127.0.0.1:<port>/ address.
        """
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "20260528-100000"
            session.mkdir()
            (session / "graded").mkdir()
            (session / "graded" / "A_S.jpg").write_bytes(b"x")
            (session / "grading_params.json").write_text('[{"file":"/raw/A.NEF","style":"S"}]')

            # Run main() in a thread because it blocks on serve_forever();
            # we only need the first line of stdout to verify the banner.
            import io
            import contextlib

            stdout_buf = io.StringIO()
            external = "https://my-host.example.com/preview/"

            def _run():
                with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(io.StringIO()):
                    main([str(session), "--external-url", external])

            t = Thread(target=_run, daemon=True)
            t.start()
            # Give main a moment to print the banner before we tear it down
            time.sleep(0.15)
            # The banner is "Preview ready: <url>\n" — check it carries the
            # external URL we requested rather than the internal 127.0.0.1
            banner = stdout_buf.getvalue().splitlines()
            self.assertTrue(banner, "no banner printed by main()")
            self.assertIn(external, banner[0])
            self.assertNotIn("127.0.0.1", banner[0])

            # main() is still serve_forever()ing in the daemon thread; let
            # the test process exit kill it. There is no clean shutdown
            # path that doesn't reach into main()'s server instance.


class TestFrontendSkeleton(unittest.TestCase):
    """Smoke checks on the inlined HTML — full UX is verified by the manual
    checklist in SKILL.md.
    """

    def test_root_serves_html_with_required_skeleton(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "20260528-100000"
            session.mkdir()
            (session / "graded").mkdir()
            (session / "graded" / "A_S.jpg").write_bytes(b"x")
            (session / "grading_params.json").write_text('[{"file":"/raw/A.NEF","style":"S"}]')
            app = build_app(session, mode="session")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            url = f"http://127.0.0.1:{server.server_address[1]}"
            Thread(target=server.serve_forever, daemon=True).start()
            try:
                time.sleep(0.05)
                with urllib.request.urlopen(url + "/", timeout=2) as r:
                    self.assertEqual(r.status, 200)
                    html = r.read().decode("utf-8")
                # Required structural anchors
                self.assertIn('id="grid"', html)
                self.assertIn('id="mode-indicator"', html)
                self.assertIn('id="style-tabs"', html)
                # Mobile-friendly viewport meta
                self.assertIn("width=device-width", html)
            finally:
                server.shutdown()
                server.server_close()

    def test_index_html_contains_required_js_symbols(self):
        """Behaviour-level UX is covered by the manual checklist; here we
        only verify the JS module wires up the symbols our spec calls for.
        """
        from preview import INDEX_HTML

        for symbol in (
            "loadManifest",
            "renderGrid",
            "renderTabs",
            "toggleMode",
            "preloadAll",
            "addEventListener('click'",
            "addEventListener('keydown'",
        ):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, INDEX_HTML)

    def test_index_html_has_mobile_touch_handlers(self):
        from preview import INDEX_HTML

        for symbol in (
            "touchstart",
            "touchend",
            "dblclick",
            "<dialog",
            "showModal",
            "pinch-zoom",
        ):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
