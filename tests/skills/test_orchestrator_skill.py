"""Unit tests for the Multi-Agent Orchestrator skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import unittest
import yaml

REPO = Path(__file__).resolve().parents[2]
IN_REPO_DIR = REPO / "skills" / "autonomous-ai-agents" / "orchestrator"
LOCAL_DIR = Path.home() / ".shiina" / "skills" / "autonomous-ai-agents" / "orchestrator"


class TestOrchestratorSkill(unittest.TestCase):
    def test_skill_files_exist(self):
        """SKILL.md and scripts/orchestrator.py must exist in-repo and in user skills."""
        self.assertTrue((IN_REPO_DIR / "SKILL.md").exists(), "In-repo SKILL.md missing")
        self.assertTrue((IN_REPO_DIR / "scripts" / "orchestrator.py").exists(), "In-repo orchestrator.py missing")
        self.assertTrue((LOCAL_DIR / "SKILL.md").exists(), "Local SKILL.md missing")
        self.assertTrue((LOCAL_DIR / "scripts" / "orchestrator.py").exists(), "Local orchestrator.py missing")

    def test_frontmatter_hardline_standards(self):
        """SKILL.md must strictly follow Shiina frontmatter standards."""
        content = (IN_REPO_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\n"), "SKILL.md must start with ---")
        parts = content.split("---\n", 2)
        self.assertGreaterEqual(len(parts), 3, "Frontmatter must be closed with ---")

        data = yaml.safe_load(parts[1])
        self.assertEqual(data.get("name"), "orchestrator")
        self.assertIn("description", data)

        desc = data["description"]
        self.assertLessEqual(len(desc), 60, f"Description length {len(desc)} > 60 chars")
        self.assertTrue(desc.endswith("."), "Description must end with a period")
        self.assertIn("linux", data.get("platforms", []))

    def test_qoder_free_tier_constraint_documented(self):
        """Skill docs must document that Qoder subagents use only free qoder-flash."""
        content = (IN_REPO_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("qoder-flash", content.lower())
        self.assertIn("free", content.lower())
        self.assertIn("qwen 3.8 flash", content.lower())

    def test_tokenharbor_free_tier_constraint_documented(self):
        """Skill docs must document TokenHarbor with deepseek-v4.1-flash:free for UI, auditing, and optimizations."""
        content = (IN_REPO_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("tokenharbor", content.lower())
        self.assertIn("deepseek-v4.1-flash:free", content.lower())
        self.assertIn("ui making", content.lower())
        self.assertIn("auditing", content.lower())
        self.assertIn("optimizations", content.lower())

    def test_orchestrator_script_status(self):
        """orchestrator.py status --json must return valid JSON without errors."""
        script = IN_REPO_DIR / "scripts" / "orchestrator.py"
        res = subprocess.run([sys.executable, str(script), "status", "--json"], capture_output=True, text=True, timeout=10)
        self.assertEqual(res.returncode, 0, f"status failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertIn("Google Antigravity (AGY)", data)
        self.assertIn("Qoder", data)
        self.assertIn("TokenHarbor", data)
        self.assertIn("OpenCode Zen", data)
        self.assertIn("Kiro CLI", data)
        self.assertEqual(data["TokenHarbor"]["status"], "ready")

    def test_orchestrator_script_plan_free_tier_qoder(self):
        """orchestrator.py plan --json must assign only qoder-flash to Qoder subtasks."""
        script = IN_REPO_DIR / "scripts" / "orchestrator.py"
        res = subprocess.run(
            [sys.executable, str(script), "plan", "--task", "Implement user signup flow and tests", "--json"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(res.returncode, 0, f"plan failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertIn("stages", data)

        qoder_subagents = []
        for stage in data["stages"]:
            for sa in stage.get("subagents", []):
                if "qoder" in sa.get("provider", "").lower():
                    qoder_subagents.append(sa)

        self.assertTrue(len(qoder_subagents) > 0, "No Qoder subagents found in plan")
        for sa in qoder_subagents:
            self.assertEqual(sa["provider"], "qoder-flash", f"Qoder subagent must use qoder-flash, got {sa['provider']}")
            self.assertIn("qwen 3.8 flash", sa["model"].lower())

    def test_orchestrator_script_plan_tokenharbor(self):
        """orchestrator.py plan --json must assign deepseek-v4.1-flash:free for UI, auditing, and optimizations."""
        script = IN_REPO_DIR / "scripts" / "orchestrator.py"
        res = subprocess.run(
            [sys.executable, str(script), "plan", "--task", "Build frontend UI and audit performance", "--json"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(res.returncode, 0, f"plan failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertIn("stages", data)

        th_subagents = []
        for stage in data["stages"]:
            for sa in stage.get("subagents", []):
                if "tokenharbor" in sa.get("provider", "").lower():
                    th_subagents.append(sa)

        self.assertTrue(len(th_subagents) >= 3, f"Expected at least 3 TokenHarbor subagents, got {len(th_subagents)}")
        for sa in th_subagents:
            self.assertEqual(sa["provider"], "tokenharbor")
            self.assertIn("deepseek-v4.1-flash:free", sa["model"].lower())

        roles = [sa["role"].lower() for sa in th_subagents]
        self.assertTrue(any("ui" in r for r in roles), "Missing UI role in TokenHarbor subagents")
        self.assertTrue(any("auditor" in r for r in roles), "Missing Auditor role in TokenHarbor subagents")
        self.assertTrue(any("optimization" in r for r in roles), "Missing Optimization role in TokenHarbor subagents")


if __name__ == "__main__":
    unittest.main()
