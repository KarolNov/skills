"""Capture a logged-in browser session (cookies + storage) for an app."""

import json
import time
from urllib.parse import urljoin

from .config import WalkthroughError, auth_state_path, expand, write_private


def _storage_state(context):
    try:
        return context.storage_state(indexed_db=True)
    except TypeError:  # Playwright < 1.51
        return context.storage_state()


def _save(app, state):
    path = auth_state_path(app["name"])
    write_private(path, json.dumps(state))
    print(f"Saved session to {path}")


def login_manual(app, channel=None):
    """Open a real browser window; the user logs in and closes it, and we keep the session."""
    from playwright.sync_api import sync_playwright

    url = urljoin(app["base_url"].rstrip("/") + "/", app.get("login_url", "/").lstrip("/"))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel=channel or app.get("browser_channel"))
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        page.goto(url)
        print(f"Log in to {app['name']} in the browser window, then close the window.")
        state = None
        try:
            while browser.is_connected() and context.pages:
                state = _storage_state(context)
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        except Exception:
            pass  # the window was closed mid-snapshot; keep the last good one
        try:
            browser.close()
        except Exception:
            pass
    if not state or (not state.get("cookies") and not state.get("origins")):
        raise WalkthroughError("No session captured. Did the login finish before the window closed?")
    _save(app, state)


def login_credentials(app, headed=False):
    """Log in headlessly using the app's login steps and credentials from ~/.walkthrough/.env."""
    from playwright.sync_api import sync_playwright

    steps = app.get("login_steps")
    if not steps:
        raise WalkthroughError(f"App '{app['name']}' has auth=credentials but no login_steps.")
    url = urljoin(app["base_url"].rstrip("/") + "/", app.get("login_url", "/").lstrip("/"))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, channel=app.get("browser_channel"))
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        for step in steps:
            kind = step["do"]
            if kind == "fill":
                page.locator(step["target"]).first.fill(expand(step["value"]))
            elif kind == "click":
                page.locator(step["target"]).first.click()
            elif kind == "press":
                page.keyboard.press(step["key"])
            elif kind == "wait_for_url":
                page.wait_for_url(step["url"], timeout=30000)
            elif kind == "wait_for":
                page.locator(step["target"]).first.wait_for(state="visible", timeout=30000)
            elif kind == "goto":
                page.goto(urljoin(app["base_url"].rstrip("/") + "/", step["url"].lstrip("/")))
            else:
                raise WalkthroughError(f"Unknown login step {kind!r}")
        page.wait_for_load_state("networkidle")
        _save(app, _storage_state(context))
        browser.close()


def login(app, channel=None, headed=False):
    if app.get("auth") == "credentials":
        login_credentials(app, headed=headed)
    elif app.get("auth") == "storage-state":
        login_manual(app, channel=channel)
    else:
        print(f"App '{app['name']}' has auth=none; nothing to do.")
