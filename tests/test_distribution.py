#!/usr/bin/env python3
"""Consistency checks on the marketplace and the README: what makes each install line work.

    python3 tests/test_distribution.py

These read .claude-plugin/marketplace.json, the plugin manifests, SKILL.md frontmatter and the
README. They don't run /plugin install; where the `claude` CLI is on PATH, the mod is also put
through `claude plugin validate`, the check the README's "Adding a mod" asks for.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKET = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
PLUGINS = {p["name"]: p for p in MARKET["plugins"]}
README = (ROOT / "README.md").read_text()
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")


def frontmatter(skill_md):
    text = skill_md.read_text()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, f"{skill_md} has no frontmatter"
    return dict(re.findall(r"^([a-z-]+):\s*(.*)$", m.group(1), re.M))


def is_mod(plugin):
    return plugin["source"].startswith("./mods/")


def sections(text):
    """{### heading: its text up to the next ### or ##}. Headings inside ``` fences don't count;
    the fenced text stays in its section's body."""
    out, head, body, fenced = {}, None, [], False
    for line in text.splitlines(keepends=True):
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and re.match(r"#{2,3} ", line):
            if head and head.startswith("### "):
                out[head[4:].strip()] = "".join(body)
            head, body = line.rstrip("\n"), []
        else:
            body.append(line)
    if head and head.startswith("### "):
        out[head[4:].strip()] = "".join(body)
    return out


def broken_links(folder, root):
    """Relative Markdown links under folder that don't resolve, or resolve outside root."""
    bad = []
    for f in folder.rglob("*.md"):
        # Examples in code (fences and inline spans) aren't links.
        text = re.sub(r"(`+)[^\n]+?\1", "", re.sub(r"^```.*?^```", "", f.read_text(), flags=re.M | re.S))
        for target in LINK.findall(text):
            if re.match(r"[a-z]+:", target):
                continue
            dest = (f.parent / target).resolve()
            if not dest.exists() or root.resolve() not in (dest, *dest.parents):
                bad.append(f"{f.relative_to(root)} -> {target}")
    return bad


class Marketplace(unittest.TestCase):
    def test_every_listed_path_exists_and_every_skill_belongs_to_one_plugin(self):
        self.assertEqual(MARKET["name"], "karolnov-skills")
        owners = {}
        for p in MARKET["plugins"]:
            self.assertTrue((ROOT / p["source"]).is_dir(), p["name"])
            for s in p.get("skills", []):
                self.assertTrue((ROOT / s / "SKILL.md").is_file(), s)
                owners.setdefault(Path(s).name, []).append(p["name"])
        on_disk = {d.name for d in (ROOT / "skills").iterdir() if (d / "SKILL.md").is_file()}
        self.assertEqual(set(owners), on_disk)
        self.assertEqual({s: o for s, o in owners.items() if len(o) != 1}, {})

    # @scenario distribution: Blueprint family
    def test_blueprint_plugin_ships_the_whole_family(self):
        skills = PLUGINS["blueprint"]["skills"]
        self.assertEqual(sorted(Path(s).name for s in skills),
                         sorted(["blueprint-setup", "blueprint", "blueprint-drift", "blueprint-sync",
                                 "blueprint-tidy", "blueprint-backfill"]))
        for s in skills:
            # Each is available as /<name>: its frontmatter name matches the folder.
            self.assertEqual(frontmatter(ROOT / s / "SKILL.md").get("name"), Path(s).name, s)
        # The family's cross-links (../blueprint/references/...) resolve inside the family.
        with tempfile.TemporaryDirectory() as tmp:
            for s in skills:
                shutil.copytree(ROOT / s, Path(tmp) / Path(s).name)
            self.assertEqual(broken_links(Path(tmp), Path(tmp)), [])


class Readme(unittest.TestCase):
    # @scenario distribution: New plugin added
    def test_every_plugin_has_its_install_line_and_section(self):
        install = re.findall(r"^/plugin install ([\w-]+)@([\w-]+)", README, re.M)
        self.assertEqual(sorted(n for n, _ in install), sorted(PLUGINS))
        self.assertEqual({m for _, m in install}, {MARKET["name"]})
        heads = sections(README)
        for name, p in PLUGINS.items():
            if is_mod(p):
                continue
            self.assertIn(name, heads, f"no ### {name} section")
            # The section names each of its skills.
            for s in p["skills"]:
                self.assertRegex(heads[name], rf"/{re.escape(Path(s).name)}\b", f"{name}: {s}")

    def test_adding_a_skill_steps_are_there(self):
        self.assertIn("## Adding a skill", README)
        self.assertIn("## Adding a mod", README)


class ManualInstall(unittest.TestCase):
    # @scenario distribution: Copied skill
    def test_copied_blueprint_family_stands_alone(self):
        family = sorted(d for d in (ROOT / "skills").iterdir() if (d / "SKILL.md").is_file())
        with tempfile.TemporaryDirectory() as home:
            skills = Path(home) / ".claude/skills"
            skills.mkdir(parents=True)
            for d in family:
                shutil.copytree(d, skills / d.name)
                meta = frontmatter(skills / d.name / "SKILL.md")
                self.assertEqual(meta.get("name"), d.name)
                self.assertTrue(meta.get("description"), d.name)
            # Cross-links (../blueprint/references/...) resolve inside the copied family.
            self.assertEqual(broken_links(skills, skills), [])
            # Nothing that only a plugin install provides.
            for f in skills.rglob("*"):
                if f.is_file() and f.suffix in (".md", ".py", ".mjs", ".html", ".yml", ".json"):
                    self.assertNotIn("CLAUDE_PLUGIN_ROOT", f.read_text(errors="replace"),
                                     f.relative_to(skills))

    def test_readme_shows_the_copy(self):
        self.assertIn("cp -r skills/skills/blueprint* ~/.claude/skills/", README)


class Mods(unittest.TestCase):
    # @scenario distribution: Install the review pane
    def test_blueprint_ui_is_its_own_plugin_beside_blueprint(self):
        p = PLUGINS["blueprint-ui"]
        self.assertEqual(p["source"], "./mods/blueprint-ui")
        mod = ROOT / p["source"]
        manifest = json.loads((mod / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "blueprint-ui")
        modules = json.loads((mod / "hooks/hooks.json").read_text())["modules"]
        self.assertTrue(modules)
        for m in modules:
            self.assertTrue((mod / "hooks" / m).is_file(), m)
        # The module registers /blueprint-ui and answers it.
        register = "\n".join((mod / "hooks" / m).read_text() for m in modules)
        self.assertRegex(register, r"command\.register\(\{\s*name: 'blueprint-ui'")
        self.assertIn("on('command.run', { command: 'blueprint-ui' }", register)
        # The README installs it next to blueprint and describes it in blueprint's section.
        lines = [ln for ln in README.splitlines() if ln.startswith("/plugin install")]
        names = [ln.split()[2].split("@")[0] for ln in lines]
        self.assertEqual(names.index("blueprint-ui"), names.index("blueprint") + 1)
        self.assertIn("`blueprint-ui`", sections(README)["blueprint"])
        if shutil.which("claude"):
            try:
                out = subprocess.run(["claude", "plugin", "validate", str(mod)],
                                     capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                self.fail("claude plugin validate took over 120s")
            # Only the exit code: the CLI's wording changes between versions.
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
