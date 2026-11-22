#!/usr/bin/env python3
"""Build a realistic fake repo and draw its capability map, to try map changes at a real size.

    python3 demo_map.py [DIR]

Writes a git repo for a made-up shop into DIR (default: a new temp folder; an existing DIR
is replaced only when it holds an earlier demo) and runs the graph.py next to this script in it,
printing the map's path and summary line. The repo has 5 domains and 3 capabilities outside any
domain (22 in all), files shared across them, baselines with requirements and scenarios, unit
tests beside the code and end-to-end flows claiming scenarios through tags, 4 artifacts, and on
purpose: one capability whose code drifted, one stale artifact, two untested capabilities, two
orphan tags and one unclassified tag. Seeded, so every run gives the same repo and picture.

Standard library only. Nothing here is used by the skill itself.
"""

import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARK = ".demo-map"  # sits in the generated repo, so a rerun knows it may replace the folder

DOMAINS = {
    "auth": ("Who the user is and what they may do.", ["session", "sso", "roles", "mfa"]),
    "billing": ("Charging customers and keeping the books straight.", ["invoices", "refunds", "tax", "subscriptions"]),
    "catalog": ("What the shop sells and what it costs.", ["search", "pricing", "inventory", "reviews"]),
    "orders": ("From cart to a placed order.", ["cart", "checkout", "history", "returns"]),
    "shipping": ("Getting parcels to the door.", ["rates", "tracking", "labels"]),
}
BARE = ["notifications", "audit-log", "api-gateway"]
UNTESTED = {"auth/mfa", "catalog/reviews"}
VERBS = ["rejects", "accepts", "retries", "expires", "rounds", "caches", "redirects", "emails", "locks", "merges",
         "splits", "refunds", "limits", "sorts", "filters", "logs", "flags", "recalculates"]
NOUNS = ["empty input", "expired token", "duplicate request", "foreign currency", "partial stock", "zero total",
         "unknown user", "stale price", "large basket", "missing address", "network timeout", "admin override",
         "guest user", "coupon code", "back-order", "split shipment", "tax-exempt buyer", "second device"]
# Files several capabilities anchor: what draws the lines between them.
SHARED = {
    "src/shared/money.ts": ["billing/invoices", "billing/refunds", "billing/tax", "catalog/pricing", "orders/checkout"],
    "src/shared/db.ts": ["orders/cart", "orders/checkout", "orders/history", "billing/invoices", "catalog/inventory"],
    "src/shared/user.ts": ["auth/session", "auth/sso", "auth/roles", "orders/history"],
    "src/shared/address.ts": ["shipping/rates", "shipping/labels", "orders/checkout"],
    "src/shared/events.ts": ["notifications", "audit-log", "orders/checkout", "billing/refunds"],
    "src/api/routes.ts": ["api-gateway", "orders/cart", "catalog/search", "auth/session"],
    "src/api/middleware.ts": ["api-gateway", "auth/session", "auth/roles"],
    "src/shared/stock.ts": ["catalog/inventory", "orders/cart", "orders/returns"],
}
# End-to-end flows: each claims scenarios of several capabilities.
FLOWS = {
    "checkout": ["orders/cart", "orders/checkout", "catalog/pricing", "billing/invoices", "auth/session", "shipping/rates"],
    "login": ["auth/session", "auth/sso", "auth/mfa"],
    "refund": ["orders/returns", "billing/refunds", "notifications", "audit-log"],
    "search-and-buy": ["catalog/search", "catalog/inventory", "orders/cart", "orders/checkout"],
    "track-parcel": ["shipping/tracking", "shipping/labels", "notifications"],
    "admin": ["auth/roles", "audit-log", "api-gateway"],
    "subscription": ["billing/subscriptions", "billing/tax", "notifications"],
}
TAG = "// @" + "scenario"  # split, so this script's own lines never read as tags


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:12]


class Shop:
    def __init__(self, root):
        self.root, self.rnd, self.files = root, random.Random(7), {}
        self.caps = [f"{d}/{c}" for d, (_, cs) in DOMAINS.items() for c in cs] + BARE

    def write(self, path, text):
        self.files[path] = text
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text)

    def anchored(self, cap):
        """The non-test files a capability's anchors match (its folder and the shared files it names)."""
        return sorted(p for p in self.files if not p.endswith(".test.ts")
                      and (p.startswith(f"src/{cap}/") or cap in SHARED.get(p, [])))

    def build(self):
        rnd, specs, scenarios = self.rnd, {}, {}
        for cap in self.caps:
            for name in rnd.sample(["index", "service", "store", "rules", "client", "types", "view", "worker"],
                                   rnd.randint(2, 5)):
                self.write(f"src/{cap}/{name}.ts", f"// {cap}\nexport const x = {rnd.random()};\n")
            specs[cap] = {"anchors": [f"src/{cap}/**", "!**/*.test.ts"] + [f for f, cs in SHARED.items() if cap in cs]}
            scenarios[cap] = self.baseline(cap)
        for f in SHARED:
            self.write(f, f"// shared {f}\nexport const y = 1;\n")
        self.tests(scenarios)

        # Stamps: everything in sync but orders/checkout, one of whose files changed since.
        for cap in self.caps:
            specs[cap].update(ref=f"https://notion.so/{cap.replace('/', '-')}", specVersion="v1", syncedCommit="abc",
                              anchorsFiles={p: digest(self.files[p]) for p in self.anchored(cap)})
        specs["orders/checkout"]["anchorsFiles"][self.anchored("orders/checkout")[0]] = "0" * 12
        state = {
            "version": 2,
            "domains": {d: {"ref": f"https://notion.so/{d}", "purpose": p} for d, (p, _) in DOMAINS.items()},
            "specs": specs,
            "artifacts": {
                "billing-help": self.artifact("webpage", "https://help.shop.example/billing", "Billing help centre", ["billing"]),
                "checkout-figma": self.artifact("figma", "https://figma.com/file/checkout", "Checkout flow design",
                                                ["orders/checkout", "orders/cart"], stale=True),
                "tracking-runbook": self.artifact("notion", "https://notion.so/tracking-runbook", "Tracking on-call runbook",
                                                  ["shipping/tracking"]),
                "api-docs": self.artifact("file", "shop/docs:api/README.md", "Public API docs", ["api-gateway", "auth/session"]),
            },
            "tests": {"kinds": {"unit": ["src/**/*.test.ts"], "e2e": ["e2e/**"]}},
        }
        self.write(".blueprint/blueprint.json", json.dumps(state, indent=2) + "\n")
        self.write(MARK, "Made by skills/blueprint/scripts/demo_map.py; safe to delete.\n")

    def baseline(self, cap):
        """Writes the capability's baseline, 3-6 requirements of 1-4 scenarios; returns the scenario names."""
        rnd, reqs, names = self.rnd, [], []
        for r in range(rnd.randint(3, 6)):
            mine = []
            for _ in range(rnd.randint(1, 4)):
                n = f"{rnd.choice(VERBS).capitalize()} {rnd.choice(NOUNS)}"
                while n in names:
                    n = f"{rnd.choice(VERBS).capitalize()} {rnd.choice(NOUNS)}"
                names.append(n)
                mine.append(n)
            title = f"{cap.split('/')[-1].replace('-', ' ').capitalize()} rule {r + 1}"
            body = f"The {cap} module SHALL handle case {r + 1}.\n\n" + "".join(
                f"- **Scenario: {n}**\n  - **GIVEN** a {cap} request\n  - **WHEN** it {n.lower()}\n"
                f"  - **THEN** the result is recorded\n" for n in mine)
            reqs.append(f"### Requirement: {title}\n\n{body}")
        self.write(f".blueprint/baseline/{cap}.md",
                   f"## Purpose\n\n{cap} does its part of the shop.\n\n## Requirements\n\n" + "\n".join(reqs))
        return names

    def tests(self, scenarios):
        rnd = self.rnd
        # Unit tests beside the code, each claiming some of its capability's scenarios, now and then a neighbour's.
        for cap in self.caps:
            if cap in UNTESTED:
                continue
            for i in range(rnd.randint(1, 4)):
                tags = [f"{TAG} {cap}: {s}" for s in rnd.sample(scenarios[cap], min(len(scenarios[cap]), rnd.randint(1, 3)))]
                if rnd.random() < 0.25:
                    near = [c for c in self.caps if c.split("/")[0] == cap.split("/")[0] and c != cap] or self.caps
                    other = rnd.choice(near)
                    tags.append(f"{TAG} {other}: {rnd.choice(scenarios[other])}")
                name = ["service", "rules", "store", "edge", "api"][i]
                self.write(f"src/{cap}/{name}.test.ts",
                           "".join(f"{t}\nit('case {k}', () => {{}});\n" for k, t in enumerate(tags)))
        for flow, caps in FLOWS.items():
            for part in range(rnd.randint(1, 3)):
                tags = [f"{TAG} {c}: {rnd.choice(scenarios[c])}" for c in rnd.sample(caps, rnd.randint(2, len(caps)))]
                self.write(f"e2e/{flow}{'' if part == 0 else f'-{part + 1}'}.spec.ts",
                           "\n".join(tags) + "\ntest('flow', async () => {});\n")
        # Problems: a reworded scenario and an unknown capability (orphans), a tag outside every kind.
        self.write("e2e/legacy.spec.ts", f"{TAG} orders/checkout: Rejects empty basket\n{TAG} payments/stripe: Charges card\n")
        self.write("scripts/smoke.test.ts", f"{TAG} catalog/search: {scenarios['catalog/search'][0]}\n")

    def artifact(self, kind, value, description, names, stale=False):
        caps = [c for n in names for c in ([n] if n in self.caps else [c for c in self.caps if c.startswith(n + "/")])]
        files = sorted({p for c in caps for p in self.anchored(c)})
        checked = {p: digest(self.files[p]) for p in files}
        if stale:
            checked[files[0]] = "0" * 12
        return {"type": kind, "value": value, "description": description, "capabilities": names, "checkedFiles": checked}


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
        root.mkdir(parents=True)
    else:
        root = Path(tempfile.mkdtemp(prefix="demo-map-"))
    Shop(root).build()
    # Ignore the developer's git config (signing, hooks, templates) in the throwaway repo.
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    for args in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *args], cwd=root, check=True, env=env)
    return subprocess.run([sys.executable, str(HERE / "graph.py"), "--out", str(root / "map.html")],
                          cwd=root, env=env).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
