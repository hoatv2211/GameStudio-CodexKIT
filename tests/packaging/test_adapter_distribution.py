from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.packaging.packs_adapters_support import (
    PackagingTestCase,
    apply_reviewed_project_adapter,
    temporary_directory,
    tree_digest,
)


class AdapterDistributionTests(PackagingTestCase):
    def test_bundled_agent_overlay_imports_standalone(self) -> None:
        source_root = Path(__file__).resolve().parents[2]
        scripts_root = source_root / "skills" / "studio-project-scaffold" / "scripts"
        helper = scripts_root / "agent_overlay.py"

        self.assertTrue(helper.is_file(), helper)
        completed = subprocess.run(
            [sys.executable, "-B", "-c", "import agent_overlay"],
            cwd=scripts_root,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_hermes_adapter_packaged_runtime_operates_outside_repository(self) -> None:
        from scripts.generate_adapters import generate_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            temp_root = Path(temp)
            adapter = temp_root / "hermes"
            outside = temp_root / "outside"
            outside.mkdir()
            generate_adapter(source_root, "hermes", adapter)
            packaged_scaffold = adapter / "skills" / "studio-project-scaffold"
            packaged_scripts = packaged_scaffold / "scripts"
            profile_path = outside / "project-profile.yaml"
            profile_path.write_text(
                """schema_version: 1
workspace:
  name: packaged-runtime
  root_git: false
  default_concurrency: 2
repositories:
  - id: server
    path: server
    git_root: true
    subsystems: [server]
    owner_skill: studio-project-intake
    validation: []
exclusions: []
agents:
  specialists:
    - id: server-specialist
      repository: server
      reasoning_effort: high
      constraints: [preserve protocol compatibility]
cross_project_contracts: []
""",
                encoding="utf-8",
            )
            script = """
import json
import os
import tomllib
from pathlib import Path
import agent_overlay
import project_profile

try:
    import scripts.agent_overlay
except ModuleNotFoundError:
    pass
else:
    raise AssertionError('repository-root scripts package must not be importable')

scripts_root = Path(os.environ['PYTHONPATH']).resolve()
assert Path(agent_overlay.__file__).resolve().is_relative_to(scripts_root)
assert Path(project_profile.__file__).resolve().is_relative_to(scripts_root)
profile = project_profile.load_project_profile(
    Path('project-profile.yaml'), known_skills={'studio-project-intake'}
)
plan = agent_overlay.plan_agent_overlay(
    Path('project'),
    template_root=scripts_root.parent / 'templates' / 'agents',
    profile_path=Path('project-profile.yaml'),
    known_skills={'studio-project-intake'},
)
operations = {item['path']: item['content'] for item in plan['operations']}
investigator = tomllib.loads(operations['.codex/agents/investigator.toml'])
print(json.dumps({
    'workspace': profile['workspace']['name'],
    'activated_roles': plan['activated_roles'],
    'operation_paths': sorted(operations),
    'investigator': investigator,
}, sort_keys=True))
"""
            completed = subprocess.run(
                [sys.executable, "-B", "-c", script],
                cwd=outside,
                env={"PYTHONPATH": str(packaged_scripts)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual("packaged-runtime", result["workspace"])
            self.assertEqual(
                ["implementer", "investigator", "server-specialist", "verifier"],
                result["activated_roles"],
            )
            self.assertIn(
                ".codex/agents/server-specialist.toml",
                result["operation_paths"],
            )
            self.assertEqual(
                {
                    "name": "investigator",
                    "description": (
                        "Read-only ownership and dependency discovery for unclear or "
                        "independently explorable game-studio work."
                    ),
                    "model_reasoning_effort": "high",
                    "sandbox_mode": "read-only",
                },
                {
                    field: result["investigator"][field]
                    for field in (
                        "name",
                        "description",
                        "model_reasoning_effort",
                        "sandbox_mode",
                    )
                },
            )
            self.assertIn(
                "Stay read-only. Locate authoritative owner files",
                result["investigator"]["developer_instructions"],
            )


if __name__ == "__main__":
    unittest.main()
