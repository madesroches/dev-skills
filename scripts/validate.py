#!/usr/bin/env python3
"""Repo consistency checks for the dev-skills plugin.

Run from anywhere: python3 scripts/validate.py
Exits non-zero and prints one line per problem found. Checks:

1. Every skills/*/SKILL.md has parseable frontmatter with the required keys,
   and its `name` matches its directory.
2. plugin.json parses and its version has a matching `## [x.y.z]` heading in
   CHANGELOG.md.
3. plugin.json and marketplace.json agree on the plugin name and description.
4. README.md's skill table and CLAUDE.md's architecture section mention every
   skill.
5. Tool-declaration heuristic: a skill body that instructs use of a
   distinctively-named tool (Task, Skill, AskUserQuestion) must declare it in
   `allowed-tools`. Lines containing "cannot" are ignored (negative mentions
   like "cannot use the Skill tool").
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_KEYS = ("name", "description", "argument-hint", "allowed-tools")
# Tools whose capitalized name appearing in a skill body reliably signals use.
# Deliberately excludes ambiguous words (Read, Write, Edit) and tools that
# skill bodies only tell *subagents* to use (WebFetch in verification prompts).
HEURISTIC_TOOLS = ("Task", "Skill", "AskUserQuestion")

errors = []


def err(msg: str) -> None:
    errors.append(msg)


def parse_frontmatter(text: str, path: Path):
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        err(f"{path}: missing or unterminated frontmatter block")
        return None
    fields = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z-]+):\s*(.*)$", line)
        if km:
            fields[km.group(1)] = km.group(2).strip().strip('"')
    return fields


def check_skills():
    skill_names = []
    for skill_file in sorted(ROOT.glob("skills/*/SKILL.md")):
        text = skill_file.read_text()
        rel = skill_file.relative_to(ROOT)
        fields = parse_frontmatter(text, rel)
        if fields is None:
            continue
        for key in REQUIRED_KEYS:
            if key not in fields:
                err(f"{rel}: frontmatter missing required key '{key}'")
        dirname = skill_file.parent.name
        if fields.get("name") and fields["name"] != dirname:
            err(f"{rel}: frontmatter name '{fields['name']}' != directory '{dirname}'")
        skill_names.append(dirname)

        allowed = fields.get("allowed-tools", "")
        body = text[text.find("---\n", 4) + 4 :]
        for tool in HEURISTIC_TOOLS:
            pattern = re.compile(rf"\b{tool}\b")
            mentioned = any(
                pattern.search(line) and "cannot" not in line
                for line in body.splitlines()
            )
            if mentioned and not re.search(rf"\b{tool}\b", allowed):
                err(f"{rel}: body instructs use of {tool} but allowed-tools lacks it")
    return skill_names


def check_manifests():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())

    version = plugin.get("version", "")
    changelog = (ROOT / "CHANGELOG.md").read_text()
    if f"## [{version}]" not in changelog:
        err(f"plugin.json version {version} has no '## [{version}]' entry in CHANGELOG.md")

    entry = marketplace["plugins"][0]
    if entry.get("name") != plugin.get("name"):
        err("plugin name differs between plugin.json and marketplace.json")
    if entry.get("description") != plugin.get("description"):
        err("plugin description differs between plugin.json and marketplace.json")


def check_docs(skill_names):
    readme = (ROOT / "README.md").read_text()
    claude_md = (ROOT / "CLAUDE.md").read_text()
    for name in skill_names:
        if f"`/{name}`" not in readme:
            err(f"README.md skill table does not mention `/{name}`")
        if f"{name}/SKILL.md" not in claude_md:
            err(f"CLAUDE.md architecture section does not mention {name}/SKILL.md")


def main() -> int:
    names = check_skills()
    check_manifests()
    check_docs(names)
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print(f"OK: {len(names)} skills, manifests, changelog, and docs are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
