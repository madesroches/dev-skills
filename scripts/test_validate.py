"""Unit tests for scripts/validate.py's pure checks. Run: python3 scripts/test_validate.py"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate import MODEL_TIERS_DECLARATION as DECL  # noqa: E402
from validate import check_model_tiers  # noqa: E402

FM = "---\nname: x\ndescription: d\nargument-hint: a\nallowed-tools: Read\n---\n"


def skill(body, fm=FM):
    return fm + "\n# X\n\n" + body + "\n"


class CheckModelTiers(unittest.TestCase):
    def test_clean_file_passes(self):
        text = skill(DECL + "\n\nSpawn the fixer with `model` = `{{coding}}`.")
        self.assertEqual(check_model_tiers("x", text), [])

    def test_file_without_tiers_passes(self):
        self.assertEqual(check_model_tiers("x", skill("Plain body.")), [])

    def test_placeholder_without_declaration_fails(self):
        problems = check_model_tiers("x", skill("Use `{{thinking}}`."))
        self.assertEqual(len(problems), 1)
        self.assertIn("without the canonical declaration", problems[0])

    def test_declaration_without_placeholder_fails(self):
        problems = check_model_tiers("x", skill(DECL + "\n\nNothing else."))
        self.assertEqual(len(problems), 1)
        self.assertIn("never uses a placeholder", problems[0])

    def test_altered_declaration_fails(self):
        altered = DECL.replace("mechanical", "simple")
        problems = check_model_tiers("x", skill(altered + "\n\nUse `{{coding}}`."))
        self.assertTrue(any("without the canonical declaration" in p for p in problems))

    def test_brand_name_in_body_fails(self):
        text = skill(DECL + "\n\nUse `{{coding}}`, i.e. an Opus agent.")
        problems = check_model_tiers("x", text)
        self.assertEqual(len(problems), 1)
        self.assertIn("'Opus'", problems[0])

    def test_brand_name_in_frontmatter_fails(self):
        fm = FM.replace("description: d", "description: a sonnet fixer")
        text = skill(DECL + "\n\nUse `{{coding}}`.", fm=fm)
        self.assertEqual(len(check_model_tiers("x", text)), 1)

    def test_brand_name_inside_declaration_passes(self):
        # The declaration itself names every alias; that must not trip the sweep.
        self.assertIn("haiku", DECL)
        text = skill(DECL + "\n\nUse `{{thinking}}`.")
        self.assertEqual(check_model_tiers("x", text), [])

    def test_alias_as_frontmatter_model_value_passes(self):
        fm = FM.replace("allowed-tools: Read\n", "allowed-tools: Read\nmodel: opus\n")
        self.assertEqual(check_model_tiers("x", skill("Plain body.", fm=fm)), [])

    def test_unknown_token_fails(self):
        text = skill(DECL + "\n\nUse `{{coding}}` and `{{fast}}`.")
        problems = check_model_tiers("x", text)
        self.assertEqual(len(problems), 1)
        self.assertIn("{{fast}}", problems[0])

    def test_line_number_counts_declaration_lines(self):
        text = skill(DECL + "\n\nUse `{{coding}}`.\nBad opus here.")
        expected = text.splitlines().index("Bad opus here.") + 1
        problems = check_model_tiers("x", text)
        self.assertEqual(len(problems), 1)
        self.assertIn(f"x:{expected}:", problems[0])


if __name__ == "__main__":
    unittest.main()
