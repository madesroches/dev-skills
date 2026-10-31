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
6. Skill-invocation names: a skill body that invokes another skill of this
   plugin must use its qualified name (`dev-skills:design`). A bare name can
   resolve to a Claude Code built-in command of the same name (the built-in
   `/design` refuses model invocation).
7. Model tiers: a skill that uses a `{{coding}}`/`{{thinking}}` placeholder must
   carry the canonical model-tier declaration byte-for-byte (and vice versa);
   model names (sonnet, opus, haiku, fable) may appear only in that declaration
   or a frontmatter `model:` value; unknown `{{...}}` tokens are rejected.
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

# The one paragraph that binds the placeholders to model aliases. Byte-identical
# in every skill that uses a placeholder; the only place (besides a frontmatter
# `model:` value) a model alias may appear in a skill file.
MODEL_TIERS_DECLARATION = (
    "**Model tiers.** This skill names models by role. `{{coding}}` is the tier for well-specified,\n"
    "mechanical work \u2014 pass `model: \"sonnet\"`. `{{thinking}}` is the tier for judgment \u2014 pass\n"
    "`model: \"opus\"`. To run on other models, remap those aliases with Claude Code's\n"
    "`ANTHROPIC_DEFAULT_SONNET_MODEL` / `ANTHROPIC_DEFAULT_OPUS_MODEL`, or swap the two quoted\n"
    "values for another alias (`sonnet`, `opus`, `haiku`, `fable`) here."
)
TIER_PLACEHOLDERS = ("{{coding}}", "{{thinking}}")
MODEL_WORDS = re.compile(r"\b(?:sonnet|opus|haiku|fable)\b", re.IGNORECASE)

errors = []


def check_model_tiers(rel, text):
    """Return problem strings for one skill file (pure; see check 7 above)."""
    problems = []
    has_decl = MODEL_TIERS_DECLARATION in text
    # Keep the declaration's newlines so reported line numbers match the file.
    rest = text.replace(MODEL_TIERS_DECLARATION, "\n" * MODEL_TIERS_DECLARATION.count("\n"))
    # A frontmatter `model:` value may be an alias (frontmatter cannot hold a placeholder).
    fm = re.match(r"\A---\n(.*?)\n---\n", rest, re.DOTALL)
    if fm:
        lines = [
            re.sub(r"^(model:).*$", r"\1", ln) for ln in fm.group(1).splitlines()
        ]
        rest = "---\n" + "\n".join(lines) + "\n---\n" + rest[fm.end() :]
    uses = any(p in rest for p in TIER_PLACEHOLDERS)
    if uses and not has_decl:
        problems.append(f"{rel}: uses a model-tier placeholder without the canonical declaration")
    if has_decl and not uses:
        problems.append(f"{rel}: carries the model-tier declaration but never uses a placeholder")
    for lineno, line in enumerate(rest.splitlines(), 1):
        for m in MODEL_WORDS.finditer(line):
            problems.append(
                f"{rel}:{lineno}: names model '{m.group(0)}' outside the declaration; "
                "use {{coding}} or {{thinking}}"
            )
        for tok in re.findall(r"\{\{[^}]*\}\}", line):
            if tok not in TIER_PLACEHOLDERS:
                problems.append(f"{rel}:{lineno}: unknown placeholder token {tok}")
    return problems


def check_qualified_invocations(skill_names, plugin_name):
    names = "|".join(sorted(map(re.escape, skill_names), key=len, reverse=True))
    # "`x` skill via the `Skill` tool" or "invoke(s/d) [the] `x`", across line wraps.
    patterns = (
        re.compile(rf"`({names})`\s+skill\s+via\s+the\s+`Skill`\s+tool"),
        re.compile(rf"\binvoke[sd]?\s+(?:the\s+)?`({names})`", re.IGNORECASE),
    )
    for skill_file in sorted(ROOT.glob("skills/*/SKILL.md")):
        text = skill_file.read_text()
        rel = skill_file.relative_to(ROOT)
        hits = {
            (text.count("\n", 0, m.start()) + 1, m.group(1))
            for pattern in patterns
            for m in pattern.finditer(text)
        }
        for line, name in sorted(hits):
            err(f"{rel}:{line}: invokes bare `{name}`; use `{plugin_name}:{name}`")


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
        for problem in check_model_tiers(rel, text):
            err(problem)

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
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    check_qualified_invocations(names, plugin["name"])
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print(f"OK: {len(names)} skills, manifests, changelog, and docs are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
