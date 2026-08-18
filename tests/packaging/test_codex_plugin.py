from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

from scripts.common import load_yaml


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_NAME = "game-studio-codex-kit"
MARKETPLACE_NAME = "gamestudio-codex-kit"
REPOSITORY_URL = "https://github.com/hoatv2211/GameStudio-CodexKIT.git"


class CodexPluginPackagingTests(unittest.TestCase):
    def test_root_manifest_packages_the_canonical_skill_catalog(self) -> None:
        manifest_path = ROOT / ".codex-plugin" / "plugin.json"
        self.assertTrue(manifest_path.is_file(), manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(PLUGIN_NAME, manifest["name"])
        self.assertEqual("1.4.0", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual(REPOSITORY_URL.removesuffix(".git"), manifest["repository"])
        self.assertEqual("MIT", manifest["license"])
        self.assertTrue(manifest["description"])
        self.assertTrue(manifest["author"]["name"])

        interface = manifest["interface"]
        self.assertEqual("GameStudio Codex Kit", interface["displayName"])
        self.assertEqual("HoaTV Studio", interface["developerName"])
        self.assertLessEqual(len(interface["defaultPrompt"]), 3)
        for prompt in interface["defaultPrompt"]:
            self.assertLessEqual(len(prompt), 128)

        capabilities = load_yaml(ROOT / "registry" / "capabilities.yaml")["capabilities"]
        registered = {entry["id"] for entry in capabilities}
        packaged = {
            directory.name
            for directory in (ROOT / manifest["skills"]).iterdir()
            if directory.is_dir() and (directory / "SKILL.md").is_file()
        }
        self.assertEqual(35, len(registered))
        self.assertEqual(registered, packaged)

    def test_repo_marketplace_exposes_the_root_github_plugin(self) -> None:
        marketplace_path = ROOT / ".claude-plugin" / "marketplace.json"
        self.assertTrue(marketplace_path.is_file(), marketplace_path)
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))

        self.assertEqual(MARKETPLACE_NAME, marketplace["name"])
        self.assertEqual("GameStudio Codex Kit", marketplace["interface"]["displayName"])
        self.assertEqual(1, len(marketplace["plugins"]))

        entry = marketplace["plugins"][0]
        self.assertEqual(PLUGIN_NAME, entry["name"])
        self.assertEqual(
            {"source": "url", "url": REPOSITORY_URL, "ref": "main"},
            entry["source"],
        )
        self.assertEqual(
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            entry["policy"],
        )
        self.assertEqual("Productivity", entry["category"])

    def test_manifest_name_and_marketplace_entry_are_stable_identifiers(self) -> None:
        manifest_path = ROOT / ".codex-plugin" / "plugin.json"
        marketplace_path = ROOT / ".claude-plugin" / "marketplace.json"
        self.assertTrue(manifest_path.is_file(), manifest_path)
        self.assertTrue(marketplace_path.is_file(), marketplace_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))

        self.assertTrue(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", manifest["name"]))
        self.assertEqual(manifest["name"], marketplace["plugins"][0]["name"])

    def test_promotion_artifacts_are_checked_out_with_lf_endings(self) -> None:
        paths = [
            "registry/promotion-artifacts/localization-authority-audit-fpc/project-snapshot.json",
            "registry/promotion-artifacts/localization-authority-audit-fpc/fpc-global-residue-authority/localization-report.txt",
        ]
        result = subprocess.run(
            ["git", "check-attr", "eol", "--", *paths],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        for path in paths:
            self.assertIn(f"{path}: eol: lf", result.stdout)


if __name__ == "__main__":
    unittest.main()
