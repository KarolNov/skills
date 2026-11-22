#!/usr/bin/env python3
"""Fake repos for testing blueprint's scripts end to end, and a realistic one to look at.

    python3 fakerepo.py [DIR]     build the demo shop in DIR and draw its map

As a library (the tests import it):

    with FakeRepo() as r:
        r.capability("auth/session", ["src/auth/**"], {"Expiry": ["Expired session redirects"]})
        r.write("src/auth/session.ts", "...")
        r.sync()                          # commit, then drift.py stamp --all: specs and code agree
        r.edit("src/auth/session.ts")     # now auth/session is code-moved
        r.drift_status()                  # {"auth/session": "code-moved"}
        r.map(), r.coverage()             # graph.py --json, coverage.py --json

Every state change goes through the real scripts (stamp, rename, artifacts add/checked), so a
test sees exactly what a user's repo would hold. shop() builds a seeded 22-capability repo with
every kind of node and problem in it; the CLI writes it to DIR (default: a new temp folder; an
existing DIR is replaced only when it holds an earlier demo) and prints the map's path and summary.

Standard library only. Nothing here is used by the skill itself.
"""

import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Ignore the developer's git config (signing, hooks, templates) in the throwaway repos.
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@t")
AT = "@" + "scenario"  # split, so this file's own lines never read as tags
MARK = ".demo-map"  # sits in a demo repo, so a rerun knows it may replace the folder


def tag(cap, scenario, comment="//"):
    """One tag line claiming a scenario."""
    return f"{comment} {AT} {cap}: {scenario}\n"


def baseline_text(purpose, requirements):
    """A baseline from {requirement title: [scenario names]}."""
    reqs = []
    for title, scenarios in requirements.items():
        body = f"The system SHALL handle {title.lower()}.\n\n" + "".join(
            f"- **Scenario: {s}**\n  - **WHEN** {s.lower()}\n  - **THEN** it is handled\n"
            for s in scenarios)
        reqs.append(f"### Requirement: {title}\n\n{body}")
    return f"## Purpose\n\n{purpose}\n\n## Requirements\n\n" + "\n".join(reqs)


class FakeRepo:
    def __init__(self, root=None):
        if root is None:
            self._tmp = tempfile.TemporaryDirectory()
            root = self._tmp.name
        else:
            self._tmp = None
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q")
        if not (self.root / ".blueprint/blueprint.json").exists():
            self.save({"version": 2, "domains": {}, "specs": {}})

    # Context manager / cleanup, so tests can `with` it or addCleanup(r.close).
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self._tmp:
            self._tmp.cleanup()

    # Files and git.
    def write(self, path, text=""):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def read(self, path):
        return (self.root / path).read_text()

    def edit(self, path, line="// edited\n"):
        """Append a line, so the file's hash changes."""
        self.write(path, self.read(path) + line)

    def remove(self, path):
        (self.root / path).unlink()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True, env=ENV).stdout

    def commit(self, message="change"):
        self.git("add", "-A")
        self.git("commit", "-qm", message, "--allow-empty")

    # blueprint.json.
    def load(self):
        return json.loads(self.read(".blueprint/blueprint.json"))

    def save(self, state):
        self.write(".blueprint/blueprint.json", json.dumps(state, indent=2) + "\n")

    def update(self, fn):
        state = self.load()
        fn(state)
        self.save(state)

    def domain(self, name, purpose=""):
        self.update(lambda s: s.setdefault("domains", {}).__setitem__(
            name, {"ref": f"https://notion.so/{name}", "purpose": purpose}))

    def capability(self, name, anchors, requirements=None, purpose=None, ref=True):
        """Map a capability and write its baseline. Stamped by the next sync()."""
        spec = {"anchors": list(anchors)}
        if ref:
            spec.update(ref=f"https://notion.so/{name.replace('/', '-')}", specVersion="v1")
        self.update(lambda s: s.setdefault("specs", {}).__setitem__(name, spec))
        if requirements is not None:
            self.write(f".blueprint/baseline/{name}.md",
                       baseline_text(purpose or f"{name} does its part.", requirements))

    def kinds(self, **kinds):
        """tests.kinds, as kind=[globs]."""
        self.update(lambda s: s.__setitem__("tests", {"kinds": kinds}))

    # The scripts. Each returns the CompletedProcess; the helpers below parse --json.
    def run(self, script, *args):
        return subprocess.run([sys.executable, str(HERE / script), *args], cwd=self.root,
                              capture_output=True, text=True, env=ENV)

    def drift(self, *args):
        return self.run("drift.py", *args)

    def checked_run(self, script, *args, ok=(0,)):
        out = self.run(script, *args)
        if out.returncode not in ok:
            raise AssertionError(f"{script} {' '.join(args)} exited {out.returncode}:\n"
                                 f"{out.stdout}{out.stderr}")
        return out

    def sync(self, *caps, message="sync"):
        """What a sync ends with: code committed, then the capabilities stamped as agreeing."""
        self.commit(message)
        self.checked_run("drift.py", "stamp", *(caps or ["--all"]))
        self.commit(f"{message}: stamp")

    def artifact(self, aid, kind, value, description, *caps):
        self.checked_run("drift.py", "artifacts", "add", "--id", aid, "--type", kind,
                         "--value", value, "--description", description, *caps)

    def drift_status(self):
        """{capability: status} from drift.py check."""
        out = self.checked_run("drift.py", "check", "--json", ok=(0, 1))
        return {r["capability"]: r["status"] for r in json.loads(out.stdout)}

    def moved(self):
        return sorted(c for c, s in self.drift_status().items() if s == "code-moved")

    def stale(self):
        """Ids of stale artifacts, from drift.py artifacts."""
        out = self.checked_run("drift.py", "artifacts", "--json")
        return sorted(a["id"] for a in json.loads(out.stdout))

    def coverage(self, *args):
        return json.loads(self.checked_run("coverage.py", "--json", *args, ok=(0, 1)).stdout)

    def map(self):
        return json.loads(self.checked_run("graph.py", "--json").stdout)

    def draw(self, out=None):
        """Write the map page; returns (path, summary line)."""
        args = ["--out", str(out)] if out else []
        lines = self.checked_run("graph.py", *args).stdout.strip().splitlines()
        return Path(lines[0]), lines[1]


# The demo shop: a seeded, realistic repo.

DOMAINS = {
    "auth": ("Who the user is and what they may do.", ["session", "sso", "roles", "mfa"]),
    "billing": ("Charging customers and keeping the books straight.",
                ["invoices", "refunds", "tax", "subscriptions"]),
    "catalog": ("What the shop sells and what it costs.",
                ["search", "pricing", "inventory", "reviews"]),
    "orders": ("From cart to a placed order.", ["cart", "checkout", "history", "returns"]),
    "shipping": ("Getting parcels to the door.", ["rates", "tracking", "labels"]),
}
BARE = ["notifications", "audit-log", "api-gateway"]
UNTESTED = {"auth/mfa", "catalog/reviews"}
VERBS = ["rejects", "accepts", "retries", "expires", "rounds", "caches", "redirects", "emails",
         "locks", "merges", "splits", "refunds", "limits", "sorts", "filters", "logs", "flags",
         "recalculates"]
NOUNS = ["empty input", "expired token", "duplicate request", "foreign currency", "partial stock",
         "zero total", "unknown user", "stale price", "large basket", "missing address",
         "network timeout", "admin override", "guest user", "coupon code", "back-order",
         "split shipment", "tax-exempt buyer", "second device"]
# Files several capabilities anchor: what draws the lines between them.
SHARED = {
    "src/shared/money.ts": ["billing/invoices", "billing/refunds", "billing/tax", "catalog/pricing",
                            "orders/checkout"],
    "src/shared/db.ts": ["orders/cart", "orders/checkout", "orders/history", "billing/invoices",
                         "catalog/inventory"],
    "src/shared/user.ts": ["auth/session", "auth/sso", "auth/roles", "orders/history"],
    "src/shared/address.ts": ["shipping/rates", "shipping/labels", "orders/checkout"],
    "src/shared/events.ts": ["notifications", "audit-log", "orders/checkout", "billing/refunds"],
    "src/api/routes.ts": ["api-gateway", "orders/cart", "catalog/search", "auth/session"],
    "src/api/middleware.ts": ["api-gateway", "auth/session", "auth/roles"],
    "src/shared/stock.ts": ["catalog/inventory", "orders/cart", "orders/returns"],
}
# End-to-end flows: each claims scenarios of several capabilities.
FLOWS = {
    "checkout": ["orders/cart", "orders/checkout", "catalog/pricing", "billing/invoices",
                 "auth/session", "shipping/rates"],
    "login": ["auth/session", "auth/sso", "auth/mfa"],
    "refund": ["orders/returns", "billing/refunds", "notifications", "audit-log"],
    "search-and-buy": ["catalog/search", "catalog/inventory", "orders/cart", "orders/checkout"],
    "track-parcel": ["shipping/tracking", "shipping/labels", "notifications"],
    "admin": ["auth/roles", "audit-log", "api-gateway"],
    "subscription": ["billing/subscriptions", "billing/tax", "notifications"],
}
CAPS = [f"{d}/{c}" for d, (_, cs) in DOMAINS.items() for c in cs] + BARE
# The one capability whose code moves after the sync; the artifact that goes stale with it.
DRIFTED, STALE = "orders/checkout", "checkout-figma"


def shop(root=None, seed=7):
    """The demo shop, synced and then drifted on purpose. Returns (repo, {cap: [scenarios]})."""
    rnd, r = random.Random(seed), FakeRepo(root)
    scenarios = {}
    for d, (purpose, _) in DOMAINS.items():
        r.domain(d, purpose)
    for cap in CAPS:
        for name in rnd.sample(["index", "service", "store", "rules", "client", "types", "view",
                                "worker"], rnd.randint(2, 5)):
            r.write(f"src/{cap}/{name}.ts", f"// {cap}\nexport const x = {rnd.random()};\n")
        reqs, names = {}, []
        for i in range(rnd.randint(3, 6)):
            mine = []
            for _ in range(rnd.randint(1, 4)):
                n = f"{rnd.choice(VERBS).capitalize()} {rnd.choice(NOUNS)}"
                while n in names:
                    n = f"{rnd.choice(VERBS).capitalize()} {rnd.choice(NOUNS)}"
                names.append(n)
                mine.append(n)
            reqs[f"{cap.split('/')[-1].replace('-', ' ').capitalize()} rule {i + 1}"] = mine
        scenarios[cap] = names
        r.capability(cap, [f"src/{cap}/**", "!**/*.test.ts"]
                     + [f for f, cs in SHARED.items() if cap in cs], reqs,
                     purpose=f"{cap} does its part of the shop.")
    for f in SHARED:
        r.write(f, f"// shared {f}\nexport const y = 1;\n")
    _tests(r, rnd, scenarios)
    r.kinds(unit=["src/**/*.test.ts"], e2e=["e2e/**"])
    r.write(MARK, "Made by skills/blueprint/scripts/fakerepo.py; safe to delete.\n")
    r.sync()
    r.artifact("billing-help", "webpage", "https://help.shop.example/billing", "Billing help centre",
               "billing")
    r.artifact(STALE, "webpage", "https://figma.com/file/checkout", "Checkout flow design",
               "orders/checkout", "orders/cart")
    r.artifact("tracking-runbook", "notion", "https://notion.so/tracking-runbook",
               "Tracking on-call runbook", "shipping/tracking")
    r.artifact("api-docs", "file", "shop/docs:api/README.md", "Public API docs", "api-gateway",
               "auth/session")
    r.commit("artifacts")
    # On purpose: code moves in one capability after the sync (and so under one artifact).
    r.edit(f"src/{DRIFTED}/" + sorted(p.name for p in (r.root / "src" / DRIFTED).glob("*.ts")
                                      if not p.name.endswith(".test.ts"))[0])
    r.commit("checkout tweak")
    return r, scenarios


def _tests(r, rnd, scenarios):
    # Unit tests beside the code, each claiming some of its capability's scenarios, now and then
    # a neighbour's.
    for cap in CAPS:
        if cap in UNTESTED:
            continue
        for i in range(rnd.randint(1, 4)):
            tags = [tag(cap, s) for s in rnd.sample(scenarios[cap],
                                                    min(len(scenarios[cap]), rnd.randint(1, 3)))]
            if rnd.random() < 0.25:
                near = [c for c in CAPS if c.split("/")[0] == cap.split("/")[0] and c != cap] or CAPS
                other = rnd.choice(near)
                tags.append(tag(other, rnd.choice(scenarios[other])))
            name = ["service", "rules", "store", "edge", "api"][i]
            r.write(f"src/{cap}/{name}.test.ts",
                    "".join(f"{t}it('case {k}', () => {{}});\n" for k, t in enumerate(tags)))
    for flow, caps in FLOWS.items():
        for part in range(rnd.randint(1, 3)):
            tags = [tag(c, rnd.choice(scenarios[c])) for c in rnd.sample(caps, rnd.randint(2, len(caps)))]
            r.write(f"e2e/{flow}{'' if part == 0 else f'-{part + 1}'}.spec.ts",
                    "".join(tags) + "test('flow', async () => {});\n")
    # Problems: a reworded scenario and an unknown capability (orphans), a tag outside every kind.
    r.write("e2e/legacy.spec.ts", tag("orders/checkout", "Rejects empty basket")
            + tag("payments/stripe", "Charges card"))
    r.write("scripts/smoke.test.ts", tag("catalog/search", scenarios["catalog/search"][0]))


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv:
        root = Path(argv[0]).resolve()
        if root.exists():
            if not (root / MARK).is_file():
                sys.exit(f"{root} exists and isn't an earlier demo; give a new folder")
            shutil.rmtree(root)
    else:
        root = Path(tempfile.mkdtemp(prefix="demo-map-"))
    r, _ = shop(root)
    path, line = r.draw(root / "map.html")
    print(path)
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
