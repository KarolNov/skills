# Logging in to the app being recorded

The recorder starts every run from a saved browser session in
`~/.walkthrough/auth/<app>.json` (cookies, localStorage and IndexedDB). There are two ways
to produce it.

## Saved session (`--auth storage-state`)

`wt login <app>` opens a real Chromium window at the login page. The user logs in any way
they like (SSO, 2FA, magic link). With a `logged_in_check`, the window closes by itself
once that element shows up, and the session is saved then. Without one, the user waits for
the app to load and closes the window; the session is snapshotted every half second while
the window is open, so closing it too quickly can save a half-finished login.

- Sessions expire on the app's schedule. Symptom: a recording of the login page, or the
  error "Session ... looks expired" when `logged_in_check` is set. Fix: `wt login <app>`.
- **"This browser may not be secure"** (Google, some IdPs block Playwright's Chromium):
  use installed Chrome instead: `wt login <app> --channel chrome`. To make it permanent,
  `wt app add <app> ... --channel chrome` (recording also uses it, so Chrome must be installed).
- **Magic links / email codes:** fine. Open the email on another device or paste the
  link into the same window.
- `sessionStorage`-only auth isn't captured (rare). Use credentials mode for those apps.

## Stored credentials (`--auth credentials`)

For a plain email + password test account. `~/.walkthrough/apps/<app>.json` holds the
login steps; the secrets stay in `.env`:

```json
{
  "name": "acme",
  "base_url": "https://staging.acme.dev",
  "auth": "credentials",
  "login_url": "/login",
  "logged_in_check": "[data-testid=user-menu]",
  "login_steps": [
    { "do": "fill", "target": "input[name=email]", "value": "$WT_ACME_USER" },
    { "do": "fill", "target": "input[name=password]", "value": "$WT_ACME_PASSWORD" },
    { "do": "click", "target": "button[type=submit]" },
    { "do": "wait_for_url", "url": "**/dashboard" }
  ]
}
```

Login step actions: `fill` (`target`, `value`), `click` (`target`), `press` (`key`),
`goto` (`url`), `wait_for` (`target`), `wait_for_url` (`url`). Two-page logins (email,
then password) are just more steps.

If the session file is missing, the recorder logs in automatically before recording. To
refresh it on demand: `wt login <app>`; add `--headed` to watch.

Credentials mode can't get past 2FA or CAPTCHAs; use a saved session for those apps.

## Which account

Recommend a **dedicated walkthrough/demo account** seeded with realistic fake data:

- Real customer names, emails, invoices or internal URLs on screen end up in a video
  that gets shared.
- Tutorials click real buttons. Creating, inviting and deleting things should happen in
  a sandbox, not in someone's live workspace.
- A stable account means stable selectors and the same screens on every re-record.

Local dev and staging environments are best. Record production only with a demo account,
and never record destructive flows there.

## Security

- `auth/*.json` holds live session cookies: anyone with the file is logged in as that
  user. It's created with mode 600 inside a 700 directory. Never commit, upload or paste it.
- `.env` holds API keys and passwords: same rules.
- To revoke: delete `~/.walkthrough/auth/<app>.json` and log that session out in the app.
