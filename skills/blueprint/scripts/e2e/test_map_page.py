#!/usr/bin/env python3
"""The map page in a real browser: graph.py's map.html, opened in headless Chromium by Playwright.

    pip install -r requirements-dev.txt && python3 -m playwright install chromium
    python3 skills/blueprint/scripts/e2e/test_map_page.py

Pages come from fakerepo.py: the demo shop for the whole-page checks (offline, written twice),
and a small music studio for the named scenarios (looper, jams, pads, tempo). Input is real mouse
and keyboard events, so d3's own drag, zoom and click handling runs. Uses Playwright's Chromium,
or installed Chrome without it; skips when Playwright or a browser is missing. Nothing here is
used by the skill itself.
"""

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fakerepo import ENV, FakeRepo

try:
    from playwright.sync_api import Error as PlaywrightError, sync_playwright
except ImportError:
    sync_playwright = None

FAKEREPO = Path(__file__).resolve().parent / "fakerepo.py"

# Reads the canvas: every node's place in map coordinates and on screen, and the zoom.
STATE = """(() => {
  const svg = document.querySelector('#graph svg'), t = d3.zoomTransform(svg), box = svg.getBoundingClientRect();
  const screen = (x, y) => [box.left + t.x + x * t.k, box.top + t.y + y * t.k];
  const caps = {}, groups = {}, files = {};
  document.querySelectorAll('g.cap').forEach((g) => { const d = g.__data__;
    caps[d.id] = { x: d.x, y: d.y, s: screen(d.x, d.y), cls: g.getAttribute('class') }; });
  document.querySelectorAll('g.fgroup').forEach((g) => { const d = g.__data__;
    groups[d.id] = { x: d.x, y: d.y, r: d.r, s: screen(d.x, d.y), owners: d.owners, n: d.files.length,
      cls: g.getAttribute('class'), count: g.querySelector('.count').textContent,
      bubble: getComputedStyle(g.querySelector('.bubble')).display,
      anim: getComputedStyle(g).animationName,
      shown: [...g.querySelectorAll('g.file')].filter((f) => getComputedStyle(f).display !== 'none').length }; });
  document.querySelectorAll('g.file').forEach((g) => { const d = g.__data__;
    files[d.id] = { x: d.x, y: d.y, s: screen(d.x, d.y) }; });
  return { k: t.k, tx: t.x, ty: t.y, box: [box.left, box.top, box.right, box.bottom], caps, groups, files,
    panel: document.querySelector('#panel h2')?.textContent ?? null };
})()"""


def launch(playwright):
    """Playwright's own Chromium, else the Chrome installed on the machine; None without either."""
    for channel in (None, "chrome"):
        try:
            return playwright.chromium.launch(channel=channel)
        except PlaywrightError:
            pass
    return None


def wheel(page, x, y, dy):
    page.mouse.move(x, y)
    page.mouse.wheel(0, dy)


def drag(page, start, end):
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=20)
    page.mouse.up()


@unittest.skipUnless(sync_playwright, "needs Playwright: pip install -r requirements-dev.txt")
class MapPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Class cleanups run even when a subclass's setUpClass fails after this, unlike
        # tearDownClass, so one class's setup error doesn't leave Playwright running.
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = launch(cls.playwright)
        if not cls.browser:
            raise unittest.SkipTest("needs a browser: python3 -m playwright install chromium")
        cls.addClassCleanup(cls.browser.close)

    def open(self, path):
        """The page, offline: every request that isn't the page's own file fails, and is recorded."""
        page = self.browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1)
        page.errors, page.blocked = [], []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and page.errors.append(m.text))

        def offline(route):
            page.blocked.append(route.request.url)
            route.abort("internetdisconnected")
        page.route(lambda url: not url.startswith(("file:", "data:", "about:")), offline)
        page.goto(Path(path).resolve().as_uri())
        page.wait_for_function("document.querySelectorAll('g.cap').length > 0")
        page.wait_for_timeout(200)
        self.addCleanup(page.close)
        self.addCleanup(lambda: self.assertEqual(page.errors, [], "errors in the page"))
        return page

    def state(self, page):
        return page.evaluate(STATE)

    def click_cap(self, page, cap):
        page.mouse.click(*self.state(page)["caps"][cap]["s"])

    def toggle(self, page, kind):
        """Opens the "Show as nodes" menu and clicks one switch, as a user would."""
        if not page.evaluate("document.getElementById('nodes').open"):
            page.click("#nodes summary")
        before = page.is_checked(f"#{kind}")
        page.click(f"#{kind}")
        self.assertNotEqual(page.is_checked(f"#{kind}"), before)
        page.click("#repo")  # a press elsewhere closes the menu
        self.settle(page)

    def settle(self, page):
        """Waits out a glide, a fade-in or a refit: until the view and the nodes stop moving."""
        page.wait_for_timeout(400)
        last = None
        for _ in range(40):
            s = self.state(page)
            now = (s["k"], s["tx"], s["ty"], json.dumps(s["caps"], sort_keys=True))
            if now == last:
                return
            last = now
            page.wait_for_timeout(150)
        self.fail("the map kept moving")

    def zoom_out_below(self, page, k):
        s = self.state(page)
        cx, cy = (s["box"][0] + s["box"][2]) / 2, (s["box"][1] + s["box"][3]) / 2
        for _ in range(20):
            if self.state(page)["k"] < k:
                return
            wheel(page, cx, cy, 120)
            page.wait_for_timeout(50)
        self.fail("could not zoom out")


def studio(root):
    """A small music app: looper and jams share the clock, pads stands apart, samples has 23 files."""
    r = FakeRepo(root)
    r.domain("studio", "Making music live.")
    r.domain("library", "Sounds kept on disk.")
    r.capability("studio/looper", ["src/looper/**", "src/shared/clock.ts"],
                 {"Layers": ["Overdub a take"], "Tempo": ["Tap the beat"]})
    r.capability("studio/jams", ["src/jams/**", "src/shared/clock.ts"], {"Sessions": ["Invite a friend"]})
    r.capability("studio/pads", ["src/pads/**"], {"Velocity": ["Soft hit"]})
    r.capability("studio/metronome", ["src/metronome/**"], {"Tempo sync": ["Follows the looper"]})
    r.capability("library/samples", ["src/samples/**"], {"Import": ["Drop a folder"]})
    r.capability("library/presets", ["src/presets/**"], {"Save": ["Name a preset"]})
    for c in ["looper", "jams", "pads", "metronome", "presets"]:
        for f in ["index", "store"]:
            r.write(f"src/{c}/{f}.ts", "export {};\n")
    for i in range(23):
        r.write(f"src/samples/s{i:02}.ts", "export {};\n")
    r.write("src/shared/clock.ts", "export {};\n")
    r.sync()
    return r


class Shop(MapPage):
    """The demo shop, as `fakerepo.py DIR` writes it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name) / "shop"
        out = subprocess.run([sys.executable, str(FAKEREPO), str(cls.dir)], capture_output=True,
                             text=True, env=ENV, check=True)
        cls.map = Path(out.stdout.splitlines()[0])

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._tmp.cleanup()

    # @scenario blueprint/map: Offline
    def test_offline_the_map_draws_and_every_control_works(self):
        html = self.map.read_text()
        self.assertNotRegex(html, r"<script[^>]+src=|<link[^>]+href=\"https?:")
        page = self.open(self.map)
        s = self.state(page)
        self.assertEqual(len(s["caps"]), 22)
        self.assertEqual(page.evaluate("document.querySelectorAll('.hull').length"), 5)
        # Search: matches listed, the rest dimmed; Escape clears it.
        page.click("#q")
        page.keyboard.type("refund")
        self.assertRegex(page.evaluate("document.getElementById('count').textContent"), r"^\d+ capabilit")
        self.assertTrue(page.evaluate("document.querySelectorAll('.result').length > 0"))
        self.assertTrue(page.evaluate("document.querySelectorAll('g.cap.dim').length > 0"))
        page.keyboard.press("Escape")
        self.assertEqual(page.evaluate("document.querySelectorAll('g.cap.dim').length"), 0)
        # "/" focuses the search.
        page.click("#repo")
        page.keyboard.press("/")
        self.assertEqual(page.evaluate("document.activeElement.id"), "q")
        # A capability opens its panel; the back link returns to the overview.
        self.click_cap(page, "orders/checkout")
        self.assertEqual(self.state(page)["panel"], "orders/checkout")
        page.click("#panel a.back")
        self.assertEqual(page.evaluate("document.querySelectorAll('#panel a.back').length"), 0)
        self.assertNotEqual(self.state(page)["panel"], "orders/checkout")
        # Each kind of node switches on and off.
        self.assertTrue(page.evaluate("document.getElementById('artifacts').checked"))
        arts = lambda: page.evaluate("document.querySelectorAll('g.file.art').length")
        self.assertGreater(arts(), 0)
        self.toggle(page, "artifacts")
        self.assertEqual(arts(), 0)
        self.toggle(page, "files")
        self.assertGreater(page.evaluate("document.querySelectorAll('g.fgroup .bubble:not(.art):not(.test)').length"), 0)
        self.toggle(page, "tests")
        self.assertGreater(page.evaluate("document.querySelectorAll('g.file.test').length"), 0)
        self.assertEqual(page.evaluate("document.getElementById('nodes-on').textContent"), "files, tests")
        # Scroll zooms, dragging the background pans, Fit puts it back.
        fitted = self.state(page)
        cx, cy = (fitted["box"][0] + fitted["box"][2]) / 2, fitted["box"][1] + 30
        wheel(page, cx, cy, -400)
        self.settle(page)
        self.assertGreater(self.state(page)["k"], fitted["k"])
        before = self.state(page)
        drag(page, (cx, cy), (cx + 120, cy + 60))
        self.settle(page)
        after = self.state(page)
        self.assertAlmostEqual(after["tx"] - before["tx"], 120, delta=2)
        page.click("#fit")
        self.settle(page)
        self.assertAlmostEqual(self.state(page)["k"], fitted["k"], delta=0.02)
        # The legend opens.
        self.assertFalse(page.evaluate("document.getElementById('legend').open"))
        page.click("#legend summary")
        self.assertTrue(page.evaluate("document.getElementById('legend').open"))
        # Nothing left the machine, nothing failed.
        self.assertEqual(page.blocked, [])
        self.assertEqual(page.errors, [])

    # @scenario blueprint/map: Same picture twice
    def test_written_twice_every_node_is_in_the_same_place(self):
        again = self.dir / "again.html"
        out = subprocess.run([sys.executable, str(FAKEREPO.parent.parent / "graph.py"), "--out", str(again)],
                             cwd=self.dir, capture_output=True, text=True, env=ENV, check=True)
        self.assertIn("22 capabilities", out.stdout)
        pictures = []
        for path in (self.map, again):
            page = self.open(path)
            first = self.state(page)
            self.toggle(page, "files")
            self.toggle(page, "tests")
            pictures.append((first, self.state(page)))
        for (a, b) in zip(*pictures):
            for kind in ("caps", "groups", "files"):
                self.assertEqual(sorted(a[kind]), sorted(b[kind]), kind)
                for id_ in a[kind]:
                    self.assertAlmostEqual(a[kind][id_]["x"], b[kind][id_]["x"], places=6, msg=id_)
                    self.assertAlmostEqual(a[kind][id_]["y"], b[kind][id_]["y"], places=6, msg=id_)
            self.assertEqual((a["k"], a["tx"], a["ty"]), (b["k"], b["tx"], b["ty"]))
        self.assertGreater(len(pictures[0][1]["files"]), 100)


class Studio(MapPage):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = studio(Path(cls._tmp.name) / "studio")
        cls.map, _ = cls.repo.draw(cls.repo.root / "map.html")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._tmp.cleanup()

    def samples(self, s):
        [g] = [g for g in s["groups"].values() if g["owners"] == ["library/samples"]]
        return g

    # @scenario blueprint/map: Many files
    def test_23_files_are_one_bubble_until_zoomed_in_or_clicked(self):
        for how in ("click", "zoom"):
            with self.subTest(how=how):
                page = self.open(self.map)
                self.zoom_out_below(page, 1.3)
                self.toggle(page, "files")
                s = self.state(page)
                self.assertLess(s["k"], 1.3)
                g = self.samples(s)
                self.assertEqual((g["n"], g["count"], g["bubble"], g["shown"]), (23, "23", "inline", 0))
                self.assertNotIn("split", g["cls"])
                if how == "click":
                    page.mouse.click(*g["s"])
                    page.wait_for_timeout(600)
                else:
                    for _ in range(20):
                        if self.state(page)["k"] >= 1.3:
                            break
                        wheel(page, *self.samples(self.state(page))["s"], -100)
                        page.wait_for_timeout(50)
                g = self.samples(self.state(page))
                self.assertIn("split", g["cls"])
                self.assertEqual((g["bubble"], g["shown"]), ("none", 23))

    # @scenario blueprint/map: Follow a neighbour
    def test_click_looper_then_jams_in_its_neighbours(self):
        page = self.open(self.map)
        self.click_cap(page, "studio/looper")
        self.assertEqual(self.state(page)["panel"], "studio/looper")
        self.assertIn("Shares files with", page.evaluate("document.getElementById('panel').textContent"))
        page.click('#panel a.link[data-id="studio/jams"]')
        page.wait_for_timeout(600)  # the 350ms pan
        s = self.state(page)
        self.assertEqual(s["panel"], "studio/jams")
        x0, y0, x1, y1 = s["box"]
        self.assertAlmostEqual(s["caps"]["studio/jams"]["s"][0], (x0 + x1) / 2, delta=1)
        self.assertAlmostEqual(s["caps"]["studio/jams"]["s"][1], (y0 + y1) / 2, delta=1)
        self.assertIn(" sel", s["caps"]["studio/jams"]["cls"])

    # @scenario blueprint/map: Find the logic for tempo
    def test_tempo_lists_highlights_and_opens_the_tempo_requirement(self):
        page = self.open(self.map)
        page.click("#q")
        page.keyboard.type("tempo")
        results = page.evaluate("[...document.querySelectorAll('.result')].map((r) => r.dataset.id)")
        self.assertEqual(sorted(results), ["studio/looper", "studio/metronome"])
        self.assertEqual(page.evaluate("document.getElementById('count').textContent"), "2 capabilities match")
        for cap, c in self.state(page)["caps"].items():
            if cap in results:
                self.assertIn("hit", c["cls"].split(), cap)
                self.assertNotIn("dim", c["cls"].split(), cap)
            else:
                self.assertIn("dim", c["cls"].split(), cap)
        page.click('.result[data-id="studio/looper"]')
        self.assertEqual(self.state(page)["panel"], "studio/looper")
        opened = page.evaluate("[...document.querySelectorAll('#panel details.req')].map((d) => "
                           "[d.querySelector('summary').textContent.trim(), d.open, "
                           "[...d.querySelectorAll('mark')].map((m) => m.textContent)])")
        by = {title.split(" ")[0]: (is_open, marks) for title, is_open, marks in opened}
        self.assertEqual(by["Tempo"][0], True)
        self.assertTrue(by["Tempo"][1])
        self.assertEqual({m.lower() for m in by["Tempo"][1]}, {"tempo"})
        self.assertEqual(by["Layers"], (False, []))

    # @scenario blueprint/map: Drop a node
    def test_dropped_pads_stays_with_its_files_and_the_rest_barely_move(self):
        page = self.open(self.map)
        self.toggle(page, "files")
        before = self.state(page)
        pads = before["caps"]["studio/pads"]
        own = [f for f, v in before["files"].items() if f.startswith("file:src/pads/")]
        self.assertEqual(len(own), 2)
        # The emptiest spot on the canvas, away from every node and the edges.
        x0, y0, x1, y1 = before["box"]
        points = [n["s"] for n in [*before["caps"].values(), *before["files"].values(),
                                   *before["groups"].values()]]
        spot = max(((x, y) for x in range(int(x0) + 80, int(x1) - 80, 20)
                    for y in range(int(y0) + 80, int(y1) - 80, 20)),
                   key=lambda p: min(math.dist(p, q) for q in points))
        self.assertGreater(min(math.dist(spot, q) for q in points), 100)
        drag(page, pads["s"], spot)
        page.wait_for_timeout(1500)  # let the simulation settle
        after = self.state(page)
        self.assertAlmostEqual(after["caps"]["studio/pads"]["s"][0], spot[0], delta=1)
        self.assertAlmostEqual(after["caps"]["studio/pads"]["s"][1], spot[1], delta=1)
        self.assertIn("pinned", after["caps"]["studio/pads"]["cls"])
        for f in own:  # its files came along, in the same place under it
            dx0 = before["files"][f]["s"][0] - pads["s"][0]
            dy0 = before["files"][f]["s"][1] - pads["s"][1]
            self.assertAlmostEqual(after["files"][f]["s"][0] - spot[0], dx0, delta=2, msg=f)
            self.assertAlmostEqual(after["files"][f]["s"][1] - spot[1], dy0, delta=2, msg=f)
        for cap, c in before["caps"].items():
            if cap != "studio/pads":
                self.assertLess(math.dist(c["s"], after["caps"][cap]["s"]), 40, cap)
        page.wait_for_timeout(1000)
        self.assertEqual(self.state(page)["caps"]["studio/pads"]["s"], after["caps"]["studio/pads"]["s"])


class OneDomain(MapPage):
    """Three capabilities in one domain: fitted, the view is the domain, close up."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.TemporaryDirectory()
        r = FakeRepo(Path(cls._tmp.name) / "duo")
        r.domain("studio", "Making music live.")
        r.capability("studio/looper", ["src/looper/**", "src/shared/clock.ts"], {"Tempo": ["Tap"]})
        r.capability("studio/jams", ["src/jams/**", "src/shared/clock.ts"], {"Sessions": ["Invite"]})
        r.capability("studio/pads", ["src/pads/**"], {"Velocity": ["Soft hit"]})
        for c in ["looper", "jams", "pads"]:
            r.write(f"src/{c}/index.ts", "export {};\n")
        r.write("src/shared/clock.ts", "export {};\n")
        r.sync()
        cls.map, _ = r.draw(r.root / "map.html")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._tmp.cleanup()

    # @scenario blueprint/map: Files switched on
    def test_files_switched_on_keep_the_view_and_fade_in(self):
        page = self.open(self.map)
        box = page.locator(".hull").bounding_box()  # the domain: selected and centred
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(600)
        before = self.state(page)
        self.assertGreater(before["k"], 1.3)  # zoomed in
        self.assertEqual(before["groups"], {})
        # Watch the file groups as they arrive: they start transparent.
        page.evaluate("window.seen = []; new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach("
                  "(n) => n.classList && n.classList.contains('fgroup') && "
                  "window.seen.push([n.getAttribute('class'), getComputedStyle(n).opacity])))).observe("
                  "document.querySelector('#graph svg'), { childList: true, subtree: true })")
        self.toggle(page, "files")
        after = self.state(page)
        self.assertTrue(after["groups"])
        x0, y0, x1, y1 = after["box"]
        for f in after["files"].values():  # the GIVEN: every new file node is in view
            self.assertTrue(x0 <= f["s"][0] <= x1 and y0 <= f["s"][1] <= y1, f)
        self.assertEqual((after["k"], after["tx"], after["ty"]), (before["k"], before["tx"], before["ty"]))
        for g in after["groups"].values():
            self.assertIn("enter", g["cls"].split())
            self.assertEqual(g["anim"], "enter")
        seen = page.evaluate("window.seen")
        self.assertTrue(seen)
        self.assertTrue(all("enter" in cls for cls, _ in seen))


class Scored(MapPage):
    """The studio with check output no fixture produces yet: pads imports moved, metronome possibly affected."""

    MAYBE = "src/shared/tempo.ts bpm changed, 2 imports away, via @studio/core (weight 0.5) → 0.13"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.TemporaryDirectory()
        repo = studio(Path(cls._tmp.name) / "studio")
        out = subprocess.run([sys.executable, str(FAKEREPO.parent.parent / "graph.py"), "--json"], cwd=repo.root,
                             capture_output=True, text=True, env=ENV, check=True)
        data = json.loads(out.stdout)
        rows = {"studio/pads": {"status": "deps-moved", "chance": 0.5, "confidence": "medium",
                                "reasons": ["src/shared/hit.ts velocity changed, 1 import away → 0.5",
                                            "confidence medium: no test results given"]},
                "studio/metronome": {"status": "possibly-affected", "chance": 0.13, "confidence": "medium",
                                     "reasons": [cls.MAYBE, "confidence medium: no test results given"]}}
        for n in data["nodes"]:
            n.update(rows.get(n["id"], {}))
        # Rendered in a child run inside the fake repo: graph imports drift, which finds the repo on import.
        cls.map = repo.root / "scored.html"
        render = ("import json, sys; sys.path.insert(0, sys.argv[1]); import graph; "
                  "sys.stdout.write(graph.render(json.load(sys.stdin)))")
        page = subprocess.run([sys.executable, "-c", render, str(FAKEREPO.parent.parent)], cwd=repo.root,
                              input=json.dumps(data), capture_output=True, text=True, env=ENV, check=True)
        cls.map.write_text(page.stdout, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._tmp.cleanup()

    # @scenario blueprint/map: Possibly affected
    def test_possibly_affected_is_tinted_and_its_panel_explains_it(self):
        page = self.open(self.map)
        caps = self.state(page)["caps"]
        self.assertIn("maybe", caps["studio/metronome"]["cls"].split())
        self.assertNotIn("drift", caps["studio/metronome"]["cls"].split())
        self.assertIn("drift", caps["studio/pads"]["cls"].split())
        # The lighter tint: a different, paler fill than the drift color's.
        fill = lambda cap: page.evaluate(f"getComputedStyle(document.querySelector('g.cap.{cap} rect')).fill")
        self.assertNotEqual(fill("maybe"), fill("drift"))
        self.click_cap(page, "studio/metronome")
        panel = page.evaluate("document.getElementById('panel').textContent")
        self.assertIn("possibly affected", panel)
        self.assertIn("0.13", panel)
        self.assertIn("confidence medium", panel)
        self.assertIn(self.MAYBE, panel)

    def test_imports_moved_panel_and_overview(self):
        page = self.open(self.map)
        overview = page.evaluate("document.getElementById('panel').textContent")
        self.assertIn("Code drifted", overview)
        self.assertIn("imports moved", overview)
        self.assertIn("Possibly affected", overview)
        self.click_cap(page, "studio/pads")
        panel = page.evaluate("document.getElementById('panel').textContent")
        self.assertIn("imports moved", panel)
        self.assertIn("/blueprint-sync studio/pads", panel)
        self.assertIn("0.5", panel)



class NoDrift(MapPage):
    """The studio with looper's code moved and a stale artifact, drawn with --no-drift."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.TemporaryDirectory()
        repo = studio(Path(cls._tmp.name) / "studio")
        repo.artifact("looper-help", "webpage", "https://help.example.com/looper", "Looper help", "studio/looper")
        repo.edit("src/looper/index.ts")
        assert repo.moved() == ["studio/looper"] and repo.stale() == ["looper-help"]
        cls.map = repo.root / "public.html"
        subprocess.run([sys.executable, str(FAKEREPO.parent.parent / "graph.py"), "--no-drift",
                        "--out", str(cls.map)], cwd=repo.root, capture_output=True, text=True,
                       env=ENV, check=True)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._tmp.cleanup()

    # @scenario blueprint/map: Drifted capability without drift
    def test_moved_capability_is_drawn_normally_and_the_legend_says_so(self):
        page = self.open(self.map)
        caps = self.state(page)["caps"]
        self.assertFalse({"drift", "maybe"} & set(caps["studio/looper"]["cls"].split()))
        self.assertEqual(page.evaluate("document.querySelectorAll('g.cap.drift, g.cap.maybe').length"), 0)
        page.click("#legend summary")
        legend = page.inner_text("#legend")
        self.assertIn("Drift is not shown on this map.", legend)
        self.assertNotIn("code drifted", legend)
        self.click_cap(page, "studio/looper")
        panel = page.evaluate("document.getElementById('panel').textContent")
        self.assertNotIn("Drift chance", panel)
        self.assertNotIn("drifted", panel)
        self.assertNotIn("/blueprint-sync", panel)
        self.assertNotIn("null", panel)

    # @scenario blueprint/map: Stale artifact without drift
    def test_stale_artifact_is_drawn_without_a_stale_mark(self):
        page = self.open(self.map)
        self.assertEqual(page.evaluate("document.querySelectorAll('g.file.art').length"), 1)
        self.assertEqual(page.evaluate("document.querySelectorAll('g.file.art.drift, .bubble.drift').length"), 0)
        overview = page.evaluate("document.getElementById('panel').textContent")
        self.assertNotIn("Stale artifacts", overview)
        self.click_cap(page, "studio/looper")
        panel = page.evaluate("document.getElementById('panel').textContent")
        self.assertIn("looper-help", panel)
        self.assertNotIn("stale", panel)

if __name__ == "__main__":
    unittest.main()
