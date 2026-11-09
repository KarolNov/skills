"""Capture a logged-in browser session (cookies + storage) for an app."""

import json
import time
from .config import WalkthroughError, auth_state_path, expand, resolve_url, write_private


def _storage_state(context):
    try:
        return context.storage_state(indexed_db=True)
    except TypeError:  # Playwright < 1.51
        return context.storage_state()


def _save(app, state):
    path = auth_state_path(app["name"])
    write_private(path, json.dumps(state))
    print(f"Saved session to {path}")


def _logged_in(context, check):
    return any(page.locator(check).first.is_visible() for page in context.pages)


def login_manual(app, channel=None):
    """Open a real browser window; the user logs in, and we keep the session.

    With a logged_in_check the window closes by itself once it is visible. Without one, the
    user closes it and the last snapshot taken while it was open is kept.
    """
    from playwright.sync_api import sync_playwright

    check = app.get("logged_in_check")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel=channel or app.get("browser_channel"))
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        page.goto(resolve_url(app["base_url"], app.get("login_url", "/")))
        if check:
            print(f"Log in to {app['name']} in the browser window; it closes by itself once you're in.")
        else:
            print(f"Log in to {app['name']} in the browser window, wait for the app to load, then close the window.")
        state = None
        try:
            while browser.is_connected() and context.pages:
                if check and _logged_in(context, check):
                    time.sleep(1.5)  # let post-login requests set their cookies
                    state = _storage_state(context)
                    break
                state = _storage_state(context)
                time.sleep(0.5)
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


def login_credentials(app, headed=False, channel=None):
    """Log in headlessly using the app's login steps and credentials from ~/.walkthrough/.env."""
    from playwright.sync_api import sync_playwright

    steps = app.get("login_steps")
    if not steps:
        raise WalkthroughError(f"App '{app['name']}' has auth=credentials but no login_steps.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, channel=channel or app.get("browser_channel"))
        context = browser.new_context()
        page = context.new_page()
        page.goto(resolve_url(app["base_url"], app.get("login_url", "/")), wait_until="domcontentloaded")
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
                page.goto(resolve_url(app["base_url"], step["url"]))
            else:
                raise WalkthroughError(f"Unknown login step {kind!r}")
        page.wait_for_load_state("networkidle")
        _save(app, _storage_state(context))
        browser.close()


def login(app, channel=None, headed=False):
    if app.get("auth") == "credentials":
        login_credentials(app, headed=headed, channel=channel)
    elif app.get("auth") == "storage-state":
        login_manual(app, channel=channel)
    else:
        print(f"App '{app['name']}' has auth=none; nothing to do.")
