"""A headless Chrome for the map tests, driven over --remote-debugging-pipe.

Standard library only: Chrome reads DevTools protocol messages on fd 3 and writes them on fd 4,
each a JSON object ending in a NUL byte, so no websocket client or Playwright is needed. Finds
Chrome or Chromium from $CHROME, the usual install paths or PATH; find() returns None without one.

    with Chrome() as c:
        page = c.page(block_network=True)
        page.goto(Path("map.html"))
        page.eval("document.title")
        page.click(x, y); page.drag((x0, y0), (x1, y1)); page.wheel(x, y, -300)

Nothing here is used by the skill itself.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


def find():
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for c in CANDIDATES:
        if os.access(c, os.X_OK):
            return c
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    return None


class Chrome:
    def __init__(self, width=1400, height=900):
        self._profile = tempfile.TemporaryDirectory()
        to_chrome_r, self._to_chrome = os.pipe()
        self._from_chrome, from_chrome_w = os.pipe()

        def fds():  # in the child: the pipe ends Chrome expects, as fds 3 and 4
            # Copied out of the way first, since either end may already sit on 3 or 4 (and
            # dup2 onto itself would keep it close-on-exec).
            r, w = os.dup(to_chrome_r), os.dup(from_chrome_w)
            os.dup2(r, 3)
            os.dup2(w, 4)

        self.proc = subprocess.Popen(
            [find(), "--headless=new", "--remote-debugging-pipe", "--no-first-run",
             "--no-default-browser-check", "--disable-extensions", "--disable-gpu",
             "--disable-background-networking", "--disable-component-update", "--mute-audio",
             f"--user-data-dir={self._profile.name}", f"--window-size={width},{height}",
             "about:blank"],
            preexec_fn=fds, close_fds=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(to_chrome_r)
        os.close(from_chrome_w)
        self._buf, self._next, self._handlers, self._events, self._replies = b"", 0, {}, [], {}
        self.width, self.height = width, height

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            self.send("Browser.close")
        except Exception:
            pass
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        for fd in (self._to_chrome, self._from_chrome):
            try:
                os.close(fd)
            except OSError:
                pass
        self._profile.cleanup()

    def _read(self):
        while b"\0" not in self._buf:
            chunk = os.read(self._from_chrome, 1 << 16)
            if not chunk:
                raise RuntimeError("Chrome closed the pipe")
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\0", 1)
        return json.loads(raw)

    def _dispatch(self, msg):
        h = self._handlers.get((msg.get("sessionId"), msg["method"]))
        if h:
            h(msg.get("params", {}))
        else:
            self._events.append(msg)

    def send(self, method, params=None, session=None):
        self._next += 1
        mine = self._next
        msg = {"id": mine, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        os.write(self._to_chrome, json.dumps(msg).encode() + b"\0")
        # A handler may send while this waits, so replies are kept by id, whoever reads them.
        while mine not in self._replies:
            got = self._read()
            if "id" in got:
                self._replies[got["id"]] = got
            elif "method" in got:
                self._dispatch(got)
        got = self._replies.pop(mine)
        if "error" in got:
            raise RuntimeError(f"{method}: {got['error']}")
        return got.get("result", {})

    def on(self, session, method, fn):
        self._handlers[(session, method)] = fn

    def page(self, block_network=False):
        target = self.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        session = self.send("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        return Page(self, session, block_network)


class Page:
    def __init__(self, chrome, session, block_network):
        self.c, self.s = chrome, session
        self.errors, self.blocked = [], []
        self.send("Runtime.enable")
        self.send("Page.enable")
        self.send("Emulation.setDeviceMetricsOverride", {"width": chrome.width, "height": chrome.height,
                                                        "deviceScaleFactor": 1, "mobile": False})
        chrome.on(session, "Runtime.exceptionThrown",
                  lambda p: self.errors.append(p["exceptionDetails"].get("exception", {})
                                               .get("description") or p["exceptionDetails"]["text"]))
        chrome.on(session, "Runtime.consoleAPICalled",
                  lambda p: p["type"] == "error" and self.errors.append(
                      " ".join(str(a.get("value", a.get("description"))) for a in p["args"])))
        if block_network:
            # Every request pauses here: the page's own file:// and data: loads go on; anything
            # else is failed as if offline, and recorded.
            self.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})

            def paused(p):
                url = p["request"]["url"]
                if url.startswith(("file:", "data:", "about:")):
                    self.c.send("Fetch.continueRequest", {"requestId": p["requestId"]}, self.s)
                else:
                    self.blocked.append(url)
                    self.c.send("Fetch.failRequest", {"requestId": p["requestId"],
                                                      "errorReason": "InternetDisconnected"}, self.s)
            chrome.on(session, "Fetch.requestPaused", paused)

    def send(self, method, params=None):
        return self.c.send(method, params, self.s)

    def eval(self, expr):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                           "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError(f"{expr[:80]}: {r['exceptionDetails']}")
        return r["result"].get("value")

    def sleep(self, seconds):
        """Wait while still answering Chrome (paused requests, events)."""
        end = time.time() + seconds
        while time.time() < end:
            self.eval("1")
            time.sleep(0.05)

    def wait(self, expr, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            if self.eval(expr):
                return
            time.sleep(0.05)
        raise AssertionError(f"timed out waiting for {expr}")

    def goto(self, path):
        self.send("Page.navigate", {"url": Path(path).resolve().as_uri()})
        self.wait("document.readyState === 'complete'")

    def mouse(self, kind, x, y, **kw):
        self.send("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, **kw})

    def click(self, x, y):
        self.mouse("mouseMoved", x, y)
        self.mouse("mousePressed", x, y, button="left", buttons=1, clickCount=1)
        self.mouse("mouseReleased", x, y, button="left", buttons=0, clickCount=1)

    def drag(self, start, end, steps=20):
        (x0, y0), (x1, y1) = start, end
        self.mouse("mouseMoved", x0, y0)
        self.mouse("mousePressed", x0, y0, button="left", buttons=1, clickCount=1)
        for i in range(1, steps + 1):
            self.mouse("mouseMoved", x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps,
                       button="left", buttons=1)
            time.sleep(0.01)
        self.mouse("mouseReleased", x1, y1, button="left", buttons=0, clickCount=1)

    def wheel(self, x, y, dy):
        self.mouse("mouseWheel", x, y, deltaX=0, deltaY=dy)

    def type(self, text):
        self.send("Input.insertText", {"text": text})
