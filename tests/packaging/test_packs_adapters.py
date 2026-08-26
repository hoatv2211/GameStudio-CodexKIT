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

def temporary_directory() -> tempfile.TemporaryDirectory:
    directory = tempfile.TemporaryDirectory(prefix="gamestudio-packaging-")
    directory.name = str(Path(directory.name).resolve())
    return directory


def tree_digest(root: Path) -> str:
    def add_field(hasher, value: bytes) -> None:
        hasher.update(len(value).to_bytes(8, "big"))
        hasher.update(value)

    def is_reparse(info: os.stat_result) -> bool:
        attributes = getattr(info, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_flag)

    try:
        root_info = root.lstat()
    except FileNotFoundError:
        root_info = None
    if root_info is not None and (root.is_symlink() or is_reparse(root_info)):
        raise RuntimeError(f"tree digest root is a symlink or reparse point: {root}")

    entries: list[tuple[bytes, bytes, bytes]] = []

    def collect(directory: Path) -> None:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                path = Path(entry.path)
                relative_text = path.relative_to(root).as_posix()
                relative = relative_text.encode("utf-8")
                info = entry.stat(follow_symlinks=False)
                is_link = entry.is_symlink()
                if is_link or is_reparse(info):
                    try:
                        target = os.fsencode(os.readlink(path))
                    except OSError:
                        raise RuntimeError(
                            f"tree digest cannot read reparse target: {relative_text}"
                        ) from None
                    entry_type = b"link" if is_link else b"reparse"
                    entries.append((relative, entry_type, target))
                elif stat.S_ISDIR(info.st_mode):
                    collect(path)
                elif stat.S_ISREG(info.st_mode):
                    entries.append((relative, b"file", path.read_bytes()))

    if root.is_dir():
        collect(root)

    hasher = hashlib.sha256()
    for relative, entry_type, content in sorted(entries):
        add_field(hasher, entry_type)
        add_field(hasher, relative)
        add_field(hasher, content)
    return hasher.hexdigest()


class TreeDigestTests(unittest.TestCase):
    def test_tree_digest_frames_paths_and_contents_without_legacy_collision(self) -> None:
        def legacy_tree_digest(root: Path) -> str:
            hasher = hashlib.sha256()
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
                hasher.update(path.read_bytes())
            return hasher.hexdigest()

        with temporary_directory() as temp:
            temp_root = Path(temp)
            first = temp_root / "first"
            second = temp_root / "second"
            first.mkdir()
            second.mkdir()
            (first / "a").write_bytes(b"bc")
            (second / "ab").write_bytes(b"c")

            self.assertEqual(legacy_tree_digest(first), legacy_tree_digest(second))
            self.assertNotEqual(tree_digest(first), tree_digest(second))

    def test_tree_digest_frames_symlink_target_without_traversal(self) -> None:
        with temporary_directory() as temp:
            temp_root = Path(temp)
            first = temp_root / "first"
            second = temp_root / "second"
            first.mkdir()
            second.mkdir()
            first_target = temp_root / "first-target.bin"
            second_target = temp_root / "second-target.bin"
            first_target.write_bytes(b"same external content")
            second_target.write_bytes(b"same external content")
            try:
                (first / "link").symlink_to(first_target)
                (second / "link").symlink_to(second_target)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink creation unavailable: {error}")

            first_digest = tree_digest(first)
            self.assertNotEqual(first_digest, tree_digest(second))
            first_target.write_bytes(b"changed outside tree")
            self.assertEqual(first_digest, tree_digest(first))

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_tree_digest_frames_junction_target_without_traversal(self) -> None:
        with temporary_directory() as temp:
            temp_root = Path(temp)
            first = temp_root / "first"
            second = temp_root / "second"
            first.mkdir()
            second.mkdir()
            first_target = temp_root / "first-target"
            second_target = temp_root / "second-target"
            first_target.mkdir()
            second_target.mkdir()
            (first_target / "external.bin").write_bytes(b"same external content")
            (second_target / "external.bin").write_bytes(b"same external content")

            for link, target in (
                (first / "junction", first_target),
                (second / "junction", second_target),
            ):
                completed = subprocess.run(
                    ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode != 0:
                    self.skipTest(
                        f"junction creation unavailable: {completed.stderr or completed.stdout}"
                    )

            first_digest = tree_digest(first)
            self.assertNotEqual(first_digest, tree_digest(second))
            (first_target / "external.bin").write_bytes(b"changed outside tree")
            self.assertEqual(first_digest, tree_digest(first))

def apply_reviewed_project_adapter(
    source_root: Path,
    project: Path,
    *,
    reviewer: str,
    backup_root: Path,
) -> dict[str, object]:
    from scripts.generate_adapters import apply_project_adapter, report_project_adapter

    report = report_project_adapter(source_root, project)
    return apply_project_adapter(
        source_root,
        project,
        reviewer=reviewer,
        backup_root=backup_root,
        approved_plan_digest=report["plan_digest"],
    )

class PackagingTests(unittest.TestCase):
    def create_directory_alias(self, link: Path, target: Path) -> None:
        if os.name == "nt":
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                self.skipTest(
                    f"junction creation unavailable: {completed.stderr or completed.stdout}"
                )
            return
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")

    def remove_directory_alias(self, link: Path) -> None:
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()

    def assert_uninstall_report_disjoint(self, report: dict[str, object]) -> None:
        self.assertTrue(
            set(report["removed"]).isdisjoint(report["preserved_drift"]),
            report,
        )

    def assert_recovery_journal_truthful(
        self, project: Path, report: dict[str, object]
    ) -> None:
        recovery_relative = report.get("recovery_manifest")
        if not isinstance(recovery_relative, str):
            return
        recovery_path = project / recovery_relative
        recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
        for record in recovery["files"]:
            artifact = project / record["quarantine_path"]
            if record["state"] in {"pending", "moved", "removing"}:
                self.assertTrue(artifact.is_file(), record)
                self.assertEqual(
                    record["sha256"],
                    hashlib.sha256(artifact.read_bytes()).hexdigest(),
                )
            elif record["state"] == "removed":
                self.assertFalse(os.path.lexists(artifact), record)
                self.assertIn(record["path"], report["removed"])
            elif record["state"] == "missing":
                self.assertFalse(os.path.lexists(artifact), record)
                self.assertIn(record["path"], report["preserved_drift"])
            elif record["state"] == "drifted":
                self.assertTrue(artifact.is_file(), record)
                observed = hashlib.sha256(artifact.read_bytes()).hexdigest()
                self.assertEqual(record["observed_sha256"], observed)
                self.assertNotEqual(record["sha256"], observed)
                self.assertIn(record["path"], report["preserved_drift"])

    def test_sync_packages_readme_markdown_as_template(self) -> None:
        from scripts.sync_skill_resources import sync_skill_resources

        with temporary_directory() as temp:
            root = Path(temp)
            skill = root / "skills" / "example-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: example-skill\n---\n", encoding="utf-8")
            (root / "README.md").write_text("# Reviewer reproduction\n", encoding="utf-8")
            registry = root / "registry" / "skill-resources.yaml"
            registry.parent.mkdir()
            registry.write_text(
                "\n".join([
                    "schema_version: 2",
                    "bundled:",
                    "  example-skill:",
                    "  - source: README.md",
                    "    destination: templates/readme.md",
                    "repository_only: {}",
                    "",
                ]),
                encoding="utf-8",
            )
            destination = skill / "templates" / "readme.md"

            self.assertEqual([destination], sync_skill_resources(root))
            self.assertEqual(
                "<!-- Generated by scripts/sync_skill_resources.py. Do not edit manually. -->",
                destination.read_text(encoding="utf-8").splitlines()[0],
            )

    def test_agent_overlay_plan_is_pure_and_materializes_generic_roles(self) -> None:
        from scripts.agent_overlay import plan_agent_overlay

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "missing-project"

            plan = plan_agent_overlay(
                project,
                template_root=(
                    source_root / "skills" / "studio-project-scaffold" / "templates" / "agents"
                ),
            )

            self.assertFalse(project.exists())
            self.assertEqual([], plan["preserved"])
            self.assertEqual([], plan["collisions"])
            self.assertEqual(
                ["implementer", "investigator", "verifier"],
                plan["activated_roles"],
            )
            self.assertEqual(
                {
                    ".codex/agents/implementer.toml",
                    ".codex/agents/investigator.toml",
                    ".codex/agents/verifier.toml",
                    ".codex/agents.generated.toml",
                },
                {operation["path"] for operation in plan["operations"]},
            )

    def test_agent_overlay_plan_adds_profile_specialists_deterministically(self) -> None:
        import tomllib
        import yaml

        from scripts.agent_overlay import plan_agent_overlay

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            profile_path = project / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 1,
                        "workspace": {
                            "name": "sample-game",
                            "root_git": False,
                            "default_concurrency": 2,
                        },
                        "repositories": [
                            {
                                "id": "server",
                                "path": "server",
                                "git_root": True,
                                "subsystems": ["server", "lua"],
                                "owner_skill": "studio-project-intake",
                                "validation": [],
                            }
                        ],
                        "exclusions": [],
                        "agents": {
                            "specialists": [
                                {
                                    "id": "server-specialist",
                                    "repository": "server",
                                    "reasoning_effort": "xhigh",
                                    "constraints": [
                                        "preserve frame budget",
                                        "preserve protocol compatibility",
                                    ],
                                }
                            ]
                        },
                        "cross_project_contracts": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            first = plan_agent_overlay(
                project,
                template_root=(
                    source_root / "skills" / "studio-project-scaffold" / "templates" / "agents"
                ),
                profile_path=profile_path,
                known_skills={"studio-project-intake"},
            )
            second = plan_agent_overlay(
                project,
                template_root=(
                    source_root / "skills" / "studio-project-scaffold" / "templates" / "agents"
                ),
                profile_path=profile_path,
                known_skills={"studio-project-intake"},
            )

            self.assertEqual(first, second)
            self.assertEqual(
                ["implementer", "investigator", "server-specialist", "verifier"],
                first["activated_roles"],
            )
            operations = {operation["path"]: operation["content"] for operation in first["operations"]}
            specialist_path = ".codex/agents/server-specialist.toml"
            self.assertIn(specialist_path, operations)
            specialist = tomllib.loads(operations[specialist_path])
            self.assertEqual("server-specialist", specialist["name"])
            self.assertEqual("xhigh", specialist["model_reasoning_effort"])
            self.assertEqual("workspace-write", specialist["sandbox_mode"])
            self.assertIn("preserve frame budget", specialist["developer_instructions"])
            activation = tomllib.loads(operations[".codex/agents.generated.toml"])
            self.assertEqual(
                "./agents/server-specialist.toml",
                activation["agents"]["server-specialist"]["config_file"],
            )

    def test_agent_overlay_omits_unmanaged_specialist_from_activation(self) -> None:
        import yaml

        from scripts.agent_overlay import plan_agent_overlay

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            profile_path = project / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 1,
                        "workspace": {
                            "name": "sample-game",
                            "root_git": False,
                            "default_concurrency": 2,
                        },
                        "repositories": [
                            {
                                "id": "server",
                                "path": "server",
                                "git_root": True,
                                "subsystems": ["server"],
                                "owner_skill": "studio-project-intake",
                                "validation": [],
                            }
                        ],
                        "exclusions": [],
                        "agents": {
                            "specialists": [
                                {
                                    "id": "server-specialist",
                                    "repository": "server",
                                    "reasoning_effort": "high",
                                    "constraints": ["preserve protocol compatibility"],
                                }
                            ]
                        },
                        "cross_project_contracts": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            unmanaged = project / ".codex" / "agents" / "server-specialist.toml"
            unmanaged.parent.mkdir(parents=True)
            unmanaged.write_text('name = "local-server-specialist"\n', encoding="utf-8")

            plan = plan_agent_overlay(
                project,
                template_root=(
                    source_root / "skills" / "studio-project-scaffold" / "templates" / "agents"
                ),
                profile_path=profile_path,
                known_skills={"studio-project-intake"},
            )

            self.assertIn(".codex/agents/server-specialist.toml", plan["preserved"])
            self.assertIn(
                {
                    "path": ".codex/agents/server-specialist.toml",
                    "kind": "unmanaged-agent",
                    "role_id": "server-specialist",
                },
                plan["collisions"],
            )
            self.assertNotIn("server-specialist", plan["activated_roles"])
            activation = next(
                operation["content"]
                for operation in plan["operations"]
                if operation["path"] == ".codex/agents.generated.toml"
            )
            self.assertNotIn("server-specialist", activation)

    def test_agent_overlay_marker_mention_does_not_claim_local_agent(self) -> None:
        from scripts.agent_overlay import MARKER, plan_agent_overlay

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            local_agent = project / ".codex" / "agents" / "investigator.toml"
            local_agent.parent.mkdir(parents=True)
            local_agent.write_text(
                f'name = "local-investigator"\ndescription = "mentions {MARKER}"\n',
                encoding="utf-8",
            )

            plan = plan_agent_overlay(
                project,
                template_root=(
                    source_root / "skills" / "studio-project-scaffold" / "templates" / "agents"
                ),
            )

            relative = ".codex/agents/investigator.toml"
            self.assertIn(relative, plan["preserved"])
            self.assertIn(
                {"path": relative, "kind": "unmanaged-agent", "role_id": "investigator"},
                plan["collisions"],
            )
            self.assertNotIn(relative, {operation["path"] for operation in plan["operations"]})

    def test_agent_overlay_marker_mention_does_not_claim_local_activation(self) -> None:
        from scripts.agent_overlay import MARKER, plan_agent_overlay

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            activation = project / ".codex" / "agents.generated.toml"
            activation.parent.mkdir(parents=True)
            activation.write_text(
                f'[agents.local]\ndescription = "mentions {MARKER}"\n',
                encoding="utf-8",
            )

            plan = plan_agent_overlay(
                project,
                template_root=(
                    source_root / "skills" / "studio-project-scaffold" / "templates" / "agents"
                ),
            )

            relative = ".codex/agents.generated.toml"
            self.assertIn(relative, plan["preserved"])
            self.assertIn(
                {"path": relative, "kind": "unmanaged-activation"},
                plan["collisions"],
            )
            self.assertNotIn(relative, {operation["path"] for operation in plan["operations"]})
            self.assertEqual([], plan["activated_roles"])

    def test_agent_overlay_preserves_unmanaged_activation(self) -> None:
        from scripts.agent_overlay import plan_agent_overlay

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            activation = project / ".codex" / "agents.generated.toml"
            activation.parent.mkdir(parents=True)
            activation.write_text('[agents.local]\nconfig_file = "./agents/local.toml"\n', encoding="utf-8")

            plan = plan_agent_overlay(
                project,
                template_root=(
                    source_root / "skills" / "studio-project-scaffold" / "templates" / "agents"
                ),
            )

            self.assertIn(".codex/agents.generated.toml", plan["preserved"])
            self.assertIn(
                {"path": ".codex/agents.generated.toml", "kind": "unmanaged-activation"},
                plan["collisions"],
            )
            self.assertNotIn(
                ".codex/agents.generated.toml",
                {operation["path"] for operation in plan["operations"]},
            )
            self.assertEqual([], plan["activated_roles"])

    def test_agent_overlay_rejects_invalid_generic_role_ids(self) -> None:
        from scripts.agent_overlay import plan_agent_overlay

        with temporary_directory() as temp:
            temp_root = Path(temp)
            template_root = temp_root / "templates"
            template_root.mkdir()
            (template_root / "safe.toml").write_text(
                'name = "con"\ndescription = "bad"\ndeveloper_instructions = "bad"\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "invalid generic role id"):
                plan_agent_overlay(temp_root / "project", template_root=template_root)

    def test_agent_overlay_rejects_reserved_profile_specialist_defensively(self) -> None:
        import scripts.agent_overlay as overlay

        source_root = Path(__file__).resolve().parents[2]
        profile = {
            "repositories": [
                {
                    "id": "server",
                    "path": "server",
                }
            ],
            "agents": {
                "specialists": [
                    {
                        "id": "con",
                        "repository": "server",
                        "reasoning_effort": "high",
                        "constraints": ["preserve protocol compatibility"],
                    }
                ]
            },
        }
        with temporary_directory() as temp:
            temp_root = Path(temp)
            profile_path = temp_root / "profile.yaml"
            profile_path.write_text("placeholder\n", encoding="utf-8")

            with mock.patch.object(overlay, "load_project_profile", return_value=profile):
                with self.assertRaisesRegex(ValueError, "invalid specialist role id"):
                    overlay.plan_agent_overlay(
                        temp_root / "project",
                        template_root=(
                            source_root
                            / "skills"
                            / "studio-project-scaffold"
                            / "templates"
                            / "agents"
                        ),
                        profile_path=profile_path,
                    )

    def test_agent_overlay_reports_unmanaged_noncolliding_local_roles(self) -> None:
        from scripts.agent_overlay import plan_agent_overlay

        source_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(
            prefix="gamestudio-packaging-relative-",
            dir=Path.cwd(),
        ) as temp:
            project = Path(temp) / "project"
            local_role = project / ".codex" / "agents" / "local-reviewer.toml"
            local_role.parent.mkdir(parents=True)
            local_role.write_text(
                'name = "local-reviewer"\ndescription = "Local role"\n',
                encoding="utf-8",
            )

            relative_project = Path(os.path.relpath(project, Path.cwd()))
            plan = plan_agent_overlay(
                relative_project,
                template_root=(
                    source_root / "skills" / "studio-project-scaffold" / "templates" / "agents"
                ),
            )

            self.assertIn(".codex/agents/local-reviewer.toml", plan["preserved"])
            self.assertNotIn(
                ".codex/agents/local-reviewer.toml",
                {collision["path"] for collision in plan["collisions"]},
            )
            self.assertNotIn(
                ".codex/agents/local-reviewer.toml",
                {operation["path"] for operation in plan["operations"]},
            )

    def test_pack_build_is_deterministic_and_generated(self) -> None:
        from scripts.build_packs import build_all_packs
        from scripts.catalog_graph import resolve_pack_skill_closure
        from scripts.common import load_yaml

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            output = Path(temp) / "packs"
            first = build_all_packs(source_root, output)
            first_digest = tree_digest(output)
            second = build_all_packs(source_root, output)
            second_digest = tree_digest(output)
            self.assertEqual(first_digest, second_digest)
            self.assertEqual(first, second)
            self.assertEqual(
                {"studio-core", "unity", "cpp-lua-mmorpg", "production-design-liveops", "production-management", "content-production", "product-analytics"},
                set(first),
            )
            content_manifest = json.loads(
                (output / "content-production" / "manifest.json").read_text(encoding="utf-8")
            )
            packs = load_yaml(source_root / "registry" / "packs.yaml")["packs"]
            capabilities = load_yaml(
                source_root / "registry" / "capabilities.yaml"
            )["capabilities"]
            resolved_skills = resolve_pack_skill_closure(
                packs,
                capabilities,
                "content-production",
            )
            self.assertEqual(resolved_skills, content_manifest["skills"])
            for skill in resolved_skills:
                self.assertTrue(
                    (output / "content-production" / "skills" / skill).is_dir(),
                    skill,
                )
            self.assertEqual(
                [
                    "level-and-content-design-review",
                    "narrative-quest-content-contract",
                    "art-asset-pipeline-preflight",
                    "animation-rigging-import-audit",
                    "audio-content-pipeline-review",
                    "unity-ui-art-and-motion-production",
                    "game-screenshot-showcase-and-store-packaging",
                ],
                content_manifest["declared_skills"],
            )
            manifest = json.loads((output / "studio-core" / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("Do not edit manually", manifest["_generated"])
            generated_skill = output / "studio-core" / "skills" / "studio-project-intake" / "SKILL.md"
            generated_text = generated_skill.read_text(encoding="utf-8")
            self.assertIn("# Generated by scripts/build_packs.py", "\n".join(generated_text.splitlines()[:3]))
            generated_helper = (
                output
                / "studio-core"
                / "skills"
                / "studio-project-scaffold"
                / "scripts"
                / "project_scaffold.py"
            )
            self.assertTrue(generated_helper.is_file())
            self.assertTrue(
                generated_helper.read_text(encoding="utf-8").startswith(
                    "# Generated by scripts/build_packs.py. Do not edit manually."
                )
            )
            scaffold_copies = sorted(output.glob("*/skills/studio-project-scaffold"))
            self.assertTrue(scaffold_copies)
            for scaffold in scaffold_copies:
                for role in ("investigator", "implementer", "verifier"):
                    template = scaffold / "templates" / "agents" / f"{role}.toml"
                    self.assertTrue(template.is_file(), template)
                    text = template.read_text(encoding="utf-8")
                    self.assertTrue(
                        text.startswith("# Generated by scripts/build_packs.py. Do not edit manually.")
                    )
                    self.assertIn(
                        "# Generated by scripts/sync_skill_resources.py. Do not edit manually.",
                        text,
                    )
            generated_schema = (
                output
                / "production-design-liveops"
                / "skills"
                / "release-candidate-preflight"
                / "schemas"
                / "release-preflight.schema.json"
            )
            schema = json.loads(generated_schema.read_text(encoding="utf-8"))
            self.assertEqual(
                "Generated by scripts/build_packs.py. Do not edit manually.",
                schema["$comment"],
            )

    def test_pack_build_rejects_partial_catalog_before_mutation(self) -> None:
        from scripts.build_packs import build_pack

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "packs.yaml").write_text(
                "schema_version: 1\npacks:\n"
                "- id: demo-pack\n"
                "  description: Demo pack\n"
                "  skills: [demo]\n"
                "  depends_on: []\n",
                encoding="utf-8",
            )
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            output = Path(temp) / "packs"

            with self.assertRaisesRegex(FileNotFoundError, "capabilities.yaml"):
                build_pack(root, pack, output)

            self.assertFalse(output.exists())

    def test_pack_build_rejects_caller_metadata_drift_from_catalog(self) -> None:
        from scripts.build_packs import build_pack

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "packs.yaml").write_text(
                "schema_version: 1\npacks:\n"
                "- id: demo-pack\n"
                "  description: Canonical pack\n"
                "  skills: [demo]\n"
                "  depends_on: []\n",
                encoding="utf-8",
            )
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n"
                "  path: skills/demo/SKILL.md\n"
                "  depends_on: []\n",
                encoding="utf-8",
            )
            caller_pack = {
                "id": "demo-pack",
                "description": "Caller drift",
                "skills": ["demo"],
                "depends_on": [],
            }
            output = Path(temp) / "packs"

            with self.assertRaisesRegex(ValueError, "does not match canonical catalog"):
                build_pack(root, caller_pack, output)

            self.assertFalse(output.exists())

    def test_json_resource_generation_is_valid_deterministic_and_replaces_sync_marker(self) -> None:
        import scripts.build_packs as packs
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            resource = Path(temp) / "schema.json"
            resource.write_text(
                '{\n  "$comment": "Generated by scripts/sync_skill_resources.py. '
                'Do not edit manually.",\n  "type": "object",\n  "properties": {}\n}\n',
                encoding="utf-8",
            )

            for module, marker in (
                (packs, packs.MARKER),
                (adapters, adapters.MARKER),
            ):
                first = module._generated_resource(resource)
                second = module._generated_resource(resource)
                parsed = json.loads(first)
                self.assertEqual(marker, parsed["$comment"])
                self.assertEqual("object", parsed["type"])
                self.assertEqual({}, parsed["properties"])
                self.assertEqual(first, second)
                self.assertTrue(first.endswith("\n"))

    def test_json_resource_generation_rejects_non_object_and_incompatible_comment(self) -> None:
        import scripts.build_packs as packs
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            resource = Path(temp) / "schema.json"
            for content, message in (
                ('["not", "an", "object"]\n', "JSON object"),
                ('{"$comment": "owned elsewhere", "type": "object"}\n', "incompatible"),
                (
                    '{"$comment": "first", "$comment": "second", "type": "object"}\n',
                    "duplicate JSON key",
                ),
            ):
                resource.write_text(content, encoding="utf-8")
                for module in (packs, adapters):
                    with self.assertRaisesRegex(ValueError, message):
                        module._generated_resource(resource)

    def test_pack_build_rejects_output_nested_in_skill_source_before_mutation(self) -> None:
        from scripts.build_packs import build_pack

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output = skill / "generated"
            before = tree_digest(skill)
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }

            with self.assertRaisesRegex(ValueError, "overlaps"):
                build_pack(root, pack, output)

            self.assertEqual(before, tree_digest(skill))
            self.assertFalse(output.exists())

    def test_standard_adapter_rejects_output_nested_in_skill_source_before_mutation(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = skill / "generated"
            before = tree_digest(skill)

            with self.assertRaisesRegex(ValueError, "overlaps"):
                generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(skill))
            self.assertFalse(output.exists())

    def test_pack_cleanup_rejects_marker_only_in_unmanaged_body(self) -> None:
        from scripts.build_packs import build_pack

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output = Path(temp) / "packs"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            build_pack(root, pack, output)
            note = output / "demo-pack" / "notes.txt"
            note_text = (
                "Local note mentions Generated by scripts/build_packs.py. "
                "Do not edit manually.\n"
            )
            note.write_text(note_text, encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "unmanaged"):
                build_pack(root, pack, output)

            self.assertEqual(note_text, note.read_text(encoding="utf-8"))

    def test_pack_and_adapter_normalize_parser_valid_frontmatter(self) -> None:
        from scripts.build_packs import build_pack
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "--- \nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "packs.yaml").write_text(
                "schema_version: 1\npacks:\n"
                "- id: demo-pack\n"
                "  description: Demo pack\n"
                "  skills: [demo]\n"
                "  depends_on: []\n",
                encoding="utf-8",
            )
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }

            pack_output = Path(temp) / "packs"
            build_pack(root, pack, pack_output)
            pack_lines = (
                pack_output / "demo-pack" / "skills" / "demo" / "SKILL.md"
            ).read_text(encoding="utf-8").splitlines()
            self.assertEqual("---", pack_lines[0])
            self.assertEqual(
                "# Generated by scripts/build_packs.py. Do not edit manually.",
                pack_lines[1],
            )

            adapter_output = Path(temp) / "adapter"
            generate_adapter(root, "hermes", adapter_output)
            adapter_lines = (
                adapter_output / "skills" / "demo" / "SKILL.md"
            ).read_text(encoding="utf-8").splitlines()
            self.assertEqual("---", adapter_lines[0])
            self.assertEqual(
                "# Generated by scripts/generate_adapters.py. Do not edit manually.",
                adapter_lines[1],
            )

    def test_pack_build_rejects_unsafe_pack_id_before_mutation(self) -> None:
        from scripts.build_packs import build_pack

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = temp_root / "nested" / "packs"
            escaped = temp_root / "escaped"
            pack = {
                "id": "../../escaped",
                "description": "Unsafe pack",
                "skills": ["demo"],
                "depends_on": [],
            }

            with self.assertRaisesRegex(ValueError, "unsafe pack id"):
                build_pack(root, pack, output_root)

            self.assertFalse(output_root.exists())
            self.assertFalse(escaped.exists())

    def test_pack_build_rejects_unsafe_skill_name_before_mutation(self) -> None:
        from scripts.build_packs import build_pack

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            outside = root / "outside"
            outside.mkdir(parents=True)
            (outside / "SKILL.md").write_text(
                "---\nname: outside\n---\n\n# Outside\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            pack = {
                "id": "demo-pack",
                "description": "Unsafe skill",
                "skills": ["../outside"],
                "depends_on": [],
            }

            with self.assertRaisesRegex(ValueError, "unsafe pack skill"):
                build_pack(root, pack, output_root)

            self.assertFalse(output_root.exists())

    def test_standard_adapter_rejects_unsafe_capability_id_before_mutation(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: ../../escaped\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = temp_root / "adapter"
            escaped = temp_root / "escaped"

            with self.assertRaisesRegex(ValueError, "unsafe capability id"):
                generate_adapter(root, "hermes", output)

            self.assertFalse(output.exists())
            self.assertFalse(escaped.exists())

    def test_standard_adapter_rejects_capability_path_outside_skills(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            outside = root / "outside" / "demo"
            outside.mkdir(parents=True)
            (outside / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: outside/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"

            with self.assertRaisesRegex(ValueError, "canonical skills"):
                generate_adapter(root, "hermes", output)

            self.assertFalse(output.exists())

    def test_standard_adapter_rejects_output_alias_without_touching_external_target(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            external = temp_root / "external-adapter"
            generate_adapter(root, "hermes", external)
            before = tree_digest(external)
            alias = temp_root / "adapter-alias"
            if os.name == "nt":
                completed = subprocess.run(
                    ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(external)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode != 0:
                    self.skipTest(
                        f"junction creation unavailable: {completed.stderr or completed.stdout}"
                    )
            else:
                try:
                    alias.symlink_to(external, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"symlink creation unavailable: {error}")
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "symlink or reparse point"):
                generate_adapter(root, "hermes", alias)

            self.assertEqual(before, tree_digest(external))
            self.assertTrue(os.path.lexists(alias))

    def test_pack_rejects_output_in_unselected_canonical_skills_sibling(self) -> None:
        from scripts.build_packs import build_pack

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            skills_root = root / "skills"
            before = tree_digest(skills_root)
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }

            with self.assertRaisesRegex(ValueError, "canonical skills"):
                build_pack(root, pack, skills_root / "generated-packs")

            self.assertEqual(before, tree_digest(skills_root))

    def test_standard_adapter_rejects_output_in_unselected_canonical_skills_sibling(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            skills_root = root / "skills"
            before = tree_digest(skills_root)

            with self.assertRaisesRegex(ValueError, "canonical skills"):
                generate_adapter(root, "hermes", skills_root / "generated-adapter")

            self.assertEqual(before, tree_digest(skills_root))

    def test_pack_source_swap_after_walk_never_packages_external_content(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            resources = skill / "resources"
            resources.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (resources / "note.txt").write_text("trusted source\n", encoding="utf-8")
            external = temp_root / "external"
            external.mkdir()
            (external / "note.txt").write_text("external payload\n", encoding="utf-8")
            backup = skill / "resources.original"
            output_root = temp_root / "packs"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            original_walk = packs._walk_files
            swapped = False

            def swap_after_walk(path: Path, **kwargs: object) -> object:
                nonlocal swapped
                walked = original_walk(path, **kwargs)
                if path == skill and kwargs.get("ignore_runtime_cache") and not swapped:
                    resources.rename(backup)
                    self.create_directory_alias(resources, external)
                    swapped = True
                return walked

            try:
                with mock.patch.object(packs, "_walk_files", side_effect=swap_after_walk):
                    packs.build_pack(root, pack, output_root)
            finally:
                if os.path.lexists(resources) and swapped:
                    self.remove_directory_alias(resources)
                if backup.exists():
                    backup.rename(resources)

            generated = (
                output_root / "demo-pack" / "skills" / "demo" / "resources" / "note.txt"
            ).read_text(encoding="utf-8")
            self.assertIn("trusted source", generated)
            self.assertNotIn("external payload", generated)

    def test_pack_rejects_nested_directory_replaced_after_parent_scan(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            nested = skill / "resources"
            nested.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (nested / "note.txt").write_text("trusted source\n", encoding="utf-8")
            external = temp_root / "external"
            external.mkdir()
            (external / "note.txt").write_text("external payload\n", encoding="utf-8")
            external_before = tree_digest(external)
            backup = skill / "resources.original"
            output_root = temp_root / "packs"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            original_scandir = packs.os.scandir
            swapped = False

            class SwapOnDirectoryCheck:
                def __init__(self, entry: os.DirEntry[str]) -> None:
                    self._entry = entry

                def __getattr__(self, name: str) -> object:
                    return getattr(self._entry, name)

                def is_dir(self, *, follow_symlinks: bool = True) -> bool:
                    nonlocal swapped
                    result = self._entry.is_dir(follow_symlinks=follow_symlinks)
                    if Path(self._entry.path) == nested and result and not swapped:
                        nested.rename(backup)
                        self_outer.create_directory_alias(nested, external)
                        swapped = True
                    return result

            self_outer = self

            def scanning(path: str | os.PathLike[str]) -> object:
                entries = list(original_scandir(path))
                if Path(path) == skill:
                    return iter(SwapOnDirectoryCheck(entry) for entry in entries)
                return iter(entries)

            try:
                with mock.patch.object(packs.os, "scandir", side_effect=scanning):
                    with self.assertRaisesRegex(ValueError, "reparse point|changed"):
                        packs.build_pack(root, pack, output_root)
            finally:
                if os.path.lexists(nested) and swapped:
                    self.remove_directory_alias(nested)
                if backup.exists():
                    backup.rename(nested)

            self.assertFalse((output_root / "demo-pack").exists())
            self.assertEqual(external_before, tree_digest(external))

    def test_pack_rejects_directory_replaced_inside_scandir(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            nested = skill / "resources"
            nested.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (nested / "note.txt").write_text("trusted source\n", encoding="utf-8")
            external = temp_root / "external"
            external.mkdir()
            (external / "note.txt").write_text("external payload\n", encoding="utf-8")
            external_before = tree_digest(external)
            backup = skill / "resources.original"
            output_root = temp_root / "packs"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            original_scandir = packs.os.scandir
            swapped = False

            def swap_inside_scan(path: str | os.PathLike[str]) -> object:
                nonlocal swapped
                if Path(path) == nested and not swapped:
                    nested.rename(backup)
                    self.create_directory_alias(nested, external)
                    swapped = True
                return original_scandir(path)

            try:
                with mock.patch.object(packs.os, "scandir", side_effect=swap_inside_scan):
                    with self.assertRaisesRegex(ValueError, "reparse point|changed"):
                        packs.build_pack(root, pack, output_root)
            finally:
                if os.path.lexists(nested) and swapped:
                    self.remove_directory_alias(nested)
                if backup.exists():
                    backup.rename(nested)

            self.assertFalse((output_root / "demo-pack").exists())
            self.assertEqual(external_before, tree_digest(external))

    def test_standard_adapter_source_swap_after_walk_never_packages_external_content(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            resources = skill / "resources"
            resources.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (resources / "note.txt").write_text("trusted source\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            external = temp_root / "external"
            external.mkdir()
            (external / "note.txt").write_text("external payload\n", encoding="utf-8")
            backup = skill / "resources.original"
            output = temp_root / "adapter"
            original_walk = adapters._walk_adapter_files
            swapped = False

            def swap_after_walk(path: Path, **kwargs: object) -> object:
                nonlocal swapped
                walked = original_walk(path, **kwargs)
                if path == skill and kwargs.get("ignore_runtime_cache") and not swapped:
                    resources.rename(backup)
                    self.create_directory_alias(resources, external)
                    swapped = True
                return walked

            try:
                with mock.patch.object(
                    adapters,
                    "_walk_adapter_files",
                    side_effect=swap_after_walk,
                ):
                    adapters.generate_adapter(root, "hermes", output)
            finally:
                if os.path.lexists(resources) and swapped:
                    self.remove_directory_alias(resources)
                if backup.exists():
                    backup.rename(resources)

            generated = (
                output / "skills" / "demo" / "resources" / "note.txt"
            ).read_text(encoding="utf-8")
            self.assertIn("trusted source", generated)
            self.assertNotIn("external payload", generated)

    def test_standard_adapter_rejects_nested_directory_replaced_after_parent_scan(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            nested = skill / "resources"
            nested.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (nested / "note.txt").write_text("trusted source\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            external = temp_root / "external"
            external.mkdir()
            (external / "note.txt").write_text("external payload\n", encoding="utf-8")
            external_before = tree_digest(external)
            backup = skill / "resources.original"
            output = temp_root / "adapter"
            original_scandir = adapters.os.scandir
            swapped = False

            class SwapOnDirectoryCheck:
                def __init__(self, entry: os.DirEntry[str]) -> None:
                    self._entry = entry

                def __getattr__(self, name: str) -> object:
                    return getattr(self._entry, name)

                def is_dir(self, *, follow_symlinks: bool = True) -> bool:
                    nonlocal swapped
                    result = self._entry.is_dir(follow_symlinks=follow_symlinks)
                    if Path(self._entry.path) == nested and result and not swapped:
                        nested.rename(backup)
                        self_outer.create_directory_alias(nested, external)
                        swapped = True
                    return result

            self_outer = self

            def scanning(path: str | os.PathLike[str]) -> object:
                entries = list(original_scandir(path))
                if Path(path) == skill:
                    return iter(SwapOnDirectoryCheck(entry) for entry in entries)
                return iter(entries)

            try:
                with mock.patch.object(adapters.os, "scandir", side_effect=scanning):
                    with self.assertRaisesRegex(ValueError, "reparse point|changed"):
                        adapters.generate_adapter(root, "hermes", output)
            finally:
                if os.path.lexists(nested) and swapped:
                    self.remove_directory_alias(nested)
                if backup.exists():
                    backup.rename(nested)

            self.assertFalse(output.exists())
            self.assertEqual(external_before, tree_digest(external))

    def test_standard_adapter_rejects_directory_replaced_inside_scandir(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            temp_root = Path(temp)
            root = temp_root / "kit"
            skill = root / "skills" / "demo"
            nested = skill / "resources"
            nested.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            (nested / "note.txt").write_text("trusted source\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            external = temp_root / "external"
            external.mkdir()
            (external / "note.txt").write_text("external payload\n", encoding="utf-8")
            external_before = tree_digest(external)
            backup = skill / "resources.original"
            output = temp_root / "adapter"
            original_scandir = adapters.os.scandir
            swapped = False

            def swap_inside_scan(path: str | os.PathLike[str]) -> object:
                nonlocal swapped
                if Path(path) == nested and not swapped:
                    nested.rename(backup)
                    self.create_directory_alias(nested, external)
                    swapped = True
                return original_scandir(path)

            try:
                with mock.patch.object(adapters.os, "scandir", side_effect=swap_inside_scan):
                    with self.assertRaisesRegex(ValueError, "reparse point|changed"):
                        adapters.generate_adapter(root, "hermes", output)
            finally:
                if os.path.lexists(nested) and swapped:
                    self.remove_directory_alias(nested)
                if backup.exists():
                    backup.rename(nested)

            self.assertFalse(output.exists())
            self.assertEqual(external_before, tree_digest(external))

    def test_pack_render_failure_preserves_previous_output(self) -> None:
        from scripts.build_packs import build_pack

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            build_pack(root, pack, output_root)
            before = tree_digest(output)
            before_siblings = sorted(path.name for path in output_root.iterdir())
            (skill / "unsupported.bin").write_bytes(b"unsupported\n")

            with self.assertRaisesRegex(ValueError, "unsupported skill resource"):
                build_pack(root, pack, output_root)

            self.assertEqual(before, tree_digest(output))
            self.assertEqual(
                before_siblings,
                sorted(path.name for path in output_root.iterdir()),
            )

    def test_standard_adapter_render_failure_preserves_previous_output(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            before_siblings = sorted(path.name for path in output.parent.iterdir())
            (skill / "unsupported.bin").write_bytes(b"unsupported\n")

            with self.assertRaisesRegex(ValueError, "unsupported skill resource"):
                generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertEqual(
                before_siblings,
                sorted(path.name for path in output.parent.iterdir()),
            )

    def test_pack_swap_failure_restores_previous_output(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = packs._rename_owned_directory

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source.name.endswith(".stage"):
                    raise OSError("injected stage swap failure")
                return original_rename(source, target)

            with mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=fail_stage_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    packs.build_pack(root, pack, output_root)

            self.assertEqual(before, tree_digest(output))
            recovery = json.loads(
                (output_root / ".demo-pack.swap-recovery.json").read_text(encoding="utf-8")
            )
            self.assertTrue(Path(recovery["stage"]).is_dir())

    def test_pack_publication_journal_exists_before_stage_rename(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            skill_file.write_text("---\nname: demo\n---\n\n# Changed\n", encoding="utf-8")
            original_rename = packs._rename_owned_directory
            journal_seen = False

            def observe_before_publish(source: Path, target: Path) -> Path:
                nonlocal journal_seen
                if source.name.endswith(".stage"):
                    journal_seen = (output_root / ".demo-pack.swap-recovery.json").is_file()
                    raise OSError("stop at publication boundary")
                return original_rename(source, target)

            with mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=observe_before_publish,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    packs.build_pack(root, pack, output_root)

            self.assertTrue(journal_seen)

    def test_pack_recovery_journal_tracks_prepared_and_output_moved_states(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            recovery_path = output_root / ".demo-pack.swap-recovery.json"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            skill_file.write_text("---\nname: demo\n---\n\n# Changed\n", encoding="utf-8")
            original_rename = packs._rename_owned_directory
            observed_states: list[str] = []

            def observe_transition(source: Path, target: Path) -> Path:
                if source == output or source.name.endswith(".stage"):
                    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
                    observed_states.append(recovery["state"])
                if source.name.endswith(".stage"):
                    raise OSError("stop after output move")
                return original_rename(source, target)

            with mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=observe_transition,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    packs.build_pack(root, pack, output_root)

            self.assertEqual(["prepared", "output-moved"], observed_states)

    def test_pack_prejournal_failure_keeps_output_visible_without_rename(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            before = tree_digest(output)
            skill_file.write_text("---\nname: demo\n---\n\n# Changed\n", encoding="utf-8")
            rename_calls = 0

            def count_rename(source: Path, target: Path) -> Path:
                nonlocal rename_calls
                rename_calls += 1
                return target

            with mock.patch.object(
                packs,
                "_write_swap_recovery",
                side_effect=OSError("injected prejournal failure"),
            ), mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=count_rename,
            ):
                with self.assertRaisesRegex(OSError, "injected prejournal failure"):
                    packs.build_pack(root, pack, output_root)

            self.assertEqual(0, rename_calls)
            self.assertEqual(before, tree_digest(output))
            self.assertEqual(1, len(list(output_root.glob(".demo-pack.*.stage"))))

    def test_pack_first_swap_rename_failure_preserves_previous_output(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = packs._rename_owned_directory

            def fail_old_output_rename(source: Path, target: Path) -> Path:
                if source == output:
                    raise OSError("injected old-output rename failure")
                return original_rename(source, target)

            with mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=fail_old_output_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    packs.build_pack(root, pack, output_root)

            self.assertEqual(before, tree_digest(output))
            recovery = json.loads(
                (output_root / ".demo-pack.swap-recovery.json").read_text(encoding="utf-8")
            )
            self.assertTrue(Path(recovery["stage"]).is_dir())

    def test_pack_concurrent_edit_before_old_output_rename_is_restored_visible(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            generated_skill = output / "skills" / "demo" / "SKILL.md"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# New staged content\n",
                encoding="utf-8",
            )
            original_rename = packs._rename_owned_directory
            injected = False

            def edit_before_rename(source: Path, target: Path) -> Path:
                nonlocal injected
                if source == output and not injected:
                    generated_skill.write_text(
                        generated_skill.read_text(encoding="utf-8")
                        + "\n# concurrent user edit\n",
                        encoding="utf-8",
                    )
                    injected = True
                return original_rename(source, target)

            with mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=edit_before_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery|changed"):
                    packs.build_pack(root, pack, output_root)

            visible = generated_skill.read_text(encoding="utf-8")
            self.assertIn("# Demo", visible)
            self.assertIn("concurrent user edit", visible)
            self.assertNotIn("New staged content", visible)
            self.assertEqual(1, len(list(output_root.glob(".demo-pack.*.stage"))))
            self.assertTrue((output_root / ".demo-pack.swap-recovery.json").is_file())

    def test_pack_cleanup_preserves_concurrent_stage_replacement(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = packs._rename_owned_directory
            original_validate = packs._validate_owned_temp
            foreign_path: Path | None = None

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source.name.endswith(".stage"):
                    raise OSError("injected stage swap failure")
                return original_rename(source, target)

            def replace_before_validation(
                path: Path,
                output_path: Path,
                suffix: str,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal foreign_path
                if suffix == "stage" and foreign_path is None:
                    shutil.rmtree(path)
                    path.mkdir()
                    foreign_path = path / "foreign.txt"
                    foreign_path.write_text("concurrent owner\n", encoding="utf-8")
                original_validate(path, output_path, suffix, *args, **kwargs)

            with mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=fail_stage_rename,
            ), mock.patch.object(
                packs,
                "_validate_owned_temp",
                side_effect=replace_before_validation,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    packs.build_pack(root, pack, output_root)

            self.assertEqual(before, tree_digest(output))
            self.assertIsNotNone(foreign_path)
            assert foreign_path is not None
            self.assertEqual("concurrent owner\n", foreign_path.read_text(encoding="utf-8"))

    def test_pack_failure_cleanup_preserves_snapshot_boundary_replacement(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = packs._rename_owned_directory
            original_snapshot = packs._tree_snapshot
            stage_snapshot_count = 0
            foreign_path: Path | None = None

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source.name.endswith(".stage"):
                    raise OSError("injected stage swap failure")
                return original_rename(source, target)

            def replace_after_snapshot(path: Path):
                nonlocal stage_snapshot_count, foreign_path
                snapshot = original_snapshot(path)
                if path.name.endswith(".stage"):
                    stage_snapshot_count += 1
                    if stage_snapshot_count == 2:
                        shutil.rmtree(path)
                        path.mkdir()
                        foreign_path = path / "foreign.txt"
                        foreign_path.write_text("snapshot-boundary owner\n", encoding="utf-8")
                return snapshot

            with mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=fail_stage_rename,
            ), mock.patch.object(
                packs,
                "_tree_snapshot",
                side_effect=replace_after_snapshot,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    packs.build_pack(root, pack, output_root)

            self.assertEqual(before, tree_digest(output))
            self.assertIsNotNone(foreign_path)
            assert foreign_path is not None
            self.assertEqual(
                "snapshot-boundary owner\n",
                foreign_path.read_text(encoding="utf-8"),
            )
            recovery_path = output_root / ".demo-pack.swap-recovery.json"
            self.assertTrue(recovery_path.is_file())

            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                packs.build_pack(root, pack, output_root)
            self.assertEqual(
                "snapshot-boundary owner\n",
                foreign_path.read_text(encoding="utf-8"),
            )

    def test_pack_publish_no_clobber_preserves_concurrent_output_and_stage(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = packs._rename_owned_directory
            foreign_file = output / "foreign.txt"
            injected = False

            def create_concurrent_output(source: Path, target: Path) -> Path:
                nonlocal injected
                if source.name.endswith(".stage") and target == output and not injected:
                    output.mkdir()
                    foreign_file.write_text("concurrent output\n", encoding="utf-8")
                    injected = True
                return original_rename(source, target)

            with mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=create_concurrent_output,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    packs.build_pack(root, pack, output_root)

            self.assertEqual("concurrent output\n", foreign_file.read_text(encoding="utf-8"))
            recovery_path = output_root / ".demo-pack.swap-recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertTrue(Path(recovery["stage"]).is_dir())
            self.assertTrue(Path(recovery["rollback"]).is_dir())

            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                packs.build_pack(root, pack, output_root)
            self.assertEqual("concurrent output\n", foreign_file.read_text(encoding="utf-8"))

    def test_pack_success_preserves_hash_bound_completion_without_duplicate_retry(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            packs.build_pack(root, pack, output_root)

            completion_paths = list(
                output_root.glob(".demo-pack.*.swap-completion.json")
            )
            self.assertEqual(1, len(completion_paths))
            completion = json.loads(completion_paths[0].read_text(encoding="utf-8"))
            self.assertEqual("pack-output-swap-completion", completion["kind"])
            self.assertEqual("published", completion["status"])
            self.assertTrue(Path(completion["rollback"]).is_dir())
            before_siblings = sorted(path.name for path in output_root.iterdir())

            packs.build_pack(root, pack, output_root)

            self.assertEqual(
                before_siblings,
                sorted(path.name for path in output_root.iterdir()),
            )

    def test_pack_double_swap_failure_persists_and_resumes_recovery(self) -> None:
        import scripts.build_packs as packs

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            packs.build_pack(root, pack, output_root)
            before = tree_digest(output)
            initial_recovery_count = len(
                list(output_root.glob(".demo-pack.*.swap-recovery.json"))
            )
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = packs._rename_owned_directory

            def fail_publish_and_restore(source: Path, target: Path) -> Path:
                if source.name.endswith((".stage", ".rollback")):
                    raise OSError("injected double rename failure")
                return original_rename(source, target)

            with mock.patch.object(
                packs,
                "_rename_owned_directory",
                side_effect=fail_publish_and_restore,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    packs.build_pack(root, pack, output_root)

            recovery_path = output_root / ".demo-pack.swap-recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertEqual(str(output), recovery["output"])
            rollback = Path(recovery["rollback"])
            stage = Path(recovery["stage"])
            self.assertTrue(rollback.is_dir())
            self.assertTrue(stage.is_dir())
            self.assertFalse(output.exists())

            with mock.patch.object(
                packs,
                "_generated_resource",
                side_effect=ValueError("stop after recovery"),
            ):
                with self.assertRaisesRegex(ValueError, "stop after recovery"):
                    packs.build_pack(root, pack, output_root)

            self.assertEqual(before, tree_digest(output))
            self.assertFalse(recovery_path.exists())
            self.assertFalse(rollback.exists())
            self.assertTrue(stage.is_dir())
            self.assertEqual(
                initial_recovery_count + 1,
                len(list(output_root.glob(".demo-pack.*.swap-recovery.json"))),
            )

    def test_standard_adapter_swap_failure_restores_previous_output(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source.name.endswith(".stage"):
                    raise OSError("injected stage swap failure")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_stage_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            recovery = json.loads(
                (output.parent / ".adapter.swap-recovery.json").read_text(encoding="utf-8")
            )
            self.assertTrue(Path(recovery["stage"]).is_dir())

    def test_standard_adapter_publication_journal_exists_before_stage_rename(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text("---\nname: demo\n---\n\n# Changed\n", encoding="utf-8")
            original_rename = adapters._rename_standard_directory
            journal_seen = False

            def observe_before_publish(source: Path, target: Path) -> Path:
                nonlocal journal_seen
                if source.name.endswith(".stage"):
                    journal_seen = (output.parent / ".adapter.swap-recovery.json").is_file()
                    raise OSError("stop at publication boundary")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=observe_before_publish,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertTrue(journal_seen)

    def test_standard_adapter_recovery_journal_tracks_prepared_and_output_moved_states(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            recovery_path = output.parent / ".adapter.swap-recovery.json"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text("---\nname: demo\n---\n\n# Changed\n", encoding="utf-8")
            original_rename = adapters._rename_standard_directory
            observed_states: list[str] = []

            def observe_transition(source: Path, target: Path) -> Path:
                if source == output or source.name.endswith(".stage"):
                    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
                    observed_states.append(recovery["state"])
                if source.name.endswith(".stage"):
                    raise OSError("stop after output move")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=observe_transition,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(["prepared", "output-moved"], observed_states)

    def test_standard_adapter_prejournal_failure_keeps_output_visible_without_rename(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text("---\nname: demo\n---\n\n# Demo\n", encoding="utf-8")
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text("---\nname: demo\n---\n\n# Changed\n", encoding="utf-8")
            rename_calls = 0

            def count_rename(source: Path, target: Path) -> Path:
                nonlocal rename_calls
                rename_calls += 1
                return target

            with mock.patch.object(
                adapters,
                "_write_standard_recovery",
                side_effect=OSError("injected prejournal failure"),
            ), mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=count_rename,
            ):
                with self.assertRaisesRegex(OSError, "injected prejournal failure"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(0, rename_calls)
            self.assertEqual(before, tree_digest(output))
            self.assertEqual(1, len(list(output.parent.glob(".adapter.*.stage"))))

    def test_standard_adapter_first_swap_rename_failure_preserves_previous_output(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory

            def fail_old_output_rename(source: Path, target: Path) -> Path:
                if source == output:
                    raise OSError("injected old-output rename failure")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_old_output_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            recovery = json.loads(
                (output.parent / ".adapter.swap-recovery.json").read_text(encoding="utf-8")
            )
            self.assertTrue(Path(recovery["stage"]).is_dir())

    def test_standard_adapter_concurrent_edit_before_old_output_rename_is_restored_visible(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            generated_skill = output / "skills" / "demo" / "SKILL.md"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# New staged content\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory
            injected = False

            def edit_before_rename(source: Path, target: Path) -> Path:
                nonlocal injected
                if source == output and not injected:
                    generated_skill.write_text(
                        generated_skill.read_text(encoding="utf-8")
                        + "\n# concurrent user edit\n",
                        encoding="utf-8",
                    )
                    injected = True
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=edit_before_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery|changed"):
                    adapters.generate_adapter(root, "hermes", output)

            visible = generated_skill.read_text(encoding="utf-8")
            self.assertIn("# Demo", visible)
            self.assertIn("concurrent user edit", visible)
            self.assertNotIn("New staged content", visible)
            self.assertEqual(1, len(list(output.parent.glob(".adapter.*.stage"))))
            self.assertTrue((output.parent / ".adapter.swap-recovery.json").is_file())

    def test_standard_adapter_cleanup_preserves_concurrent_stage_replacement(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory
            original_validate = adapters._validate_standard_temp
            foreign_path: Path | None = None

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source.name.endswith(".stage"):
                    raise OSError("injected stage swap failure")
                return original_rename(source, target)

            def replace_before_validation(
                path: Path,
                output_path: Path,
                suffix: str,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal foreign_path
                if suffix == "stage" and foreign_path is None:
                    shutil.rmtree(path)
                    path.mkdir()
                    foreign_path = path / "foreign.txt"
                    foreign_path.write_text("concurrent owner\n", encoding="utf-8")
                original_validate(path, output_path, suffix, *args, **kwargs)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_stage_rename,
            ), mock.patch.object(
                adapters,
                "_validate_standard_temp",
                side_effect=replace_before_validation,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertIsNotNone(foreign_path)
            assert foreign_path is not None
            self.assertEqual("concurrent owner\n", foreign_path.read_text(encoding="utf-8"))

    def test_standard_adapter_failure_cleanup_preserves_snapshot_boundary_replacement(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory
            original_snapshot = adapters._standard_tree_snapshot
            stage_snapshot_count = 0
            foreign_path: Path | None = None

            def fail_stage_rename(source: Path, target: Path) -> Path:
                if source.name.endswith(".stage"):
                    raise OSError("injected stage swap failure")
                return original_rename(source, target)

            def replace_after_snapshot(path: Path):
                nonlocal stage_snapshot_count, foreign_path
                snapshot = original_snapshot(path)
                if path.name.endswith(".stage"):
                    stage_snapshot_count += 1
                    if stage_snapshot_count == 2:
                        shutil.rmtree(path)
                        path.mkdir()
                        foreign_path = path / "foreign.txt"
                        foreign_path.write_text("snapshot-boundary owner\n", encoding="utf-8")
                return snapshot

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_stage_rename,
            ), mock.patch.object(
                adapters,
                "_standard_tree_snapshot",
                side_effect=replace_after_snapshot,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertIsNotNone(foreign_path)
            assert foreign_path is not None
            self.assertEqual(
                "snapshot-boundary owner\n",
                foreign_path.read_text(encoding="utf-8"),
            )
            recovery_path = output.parent / ".adapter.swap-recovery.json"
            self.assertTrue(recovery_path.is_file())

            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                adapters.generate_adapter(root, "hermes", output)
            self.assertEqual(
                "snapshot-boundary owner\n",
                foreign_path.read_text(encoding="utf-8"),
            )

    def test_standard_adapter_publish_no_clobber_preserves_concurrent_output_and_stage(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory
            foreign_file = output / "foreign.txt"
            injected = False

            def create_concurrent_output(source: Path, target: Path) -> Path:
                nonlocal injected
                if source.name.endswith(".stage") and target == output and not injected:
                    output.mkdir()
                    foreign_file.write_text("concurrent output\n", encoding="utf-8")
                    injected = True
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=create_concurrent_output,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual("concurrent output\n", foreign_file.read_text(encoding="utf-8"))
            recovery_path = output.parent / ".adapter.swap-recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertTrue(Path(recovery["stage"]).is_dir())
            self.assertTrue(Path(recovery["rollback"]).is_dir())

            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                adapters.generate_adapter(root, "hermes", output)
            self.assertEqual("concurrent output\n", foreign_file.read_text(encoding="utf-8"))

    def test_standard_adapter_success_preserves_hash_bound_completion_without_duplicate_retry(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            adapters.generate_adapter(root, "hermes", output)

            completion_paths = list(
                output.parent.glob(".adapter.*.swap-completion.json")
            )
            self.assertEqual(1, len(completion_paths))
            completion = json.loads(completion_paths[0].read_text(encoding="utf-8"))
            self.assertEqual("adapter-output-swap-completion", completion["kind"])
            self.assertEqual("published", completion["status"])
            self.assertTrue(Path(completion["rollback"]).is_dir())
            before_siblings = sorted(path.name for path in output.parent.iterdir())

            adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(
                before_siblings,
                sorted(path.name for path in output.parent.iterdir()),
            )

    def test_standard_adapter_double_swap_failure_persists_and_resumes_recovery(self) -> None:
        import scripts.generate_adapters as adapters

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            adapters.generate_adapter(root, "hermes", output)
            before = tree_digest(output)
            initial_recovery_count = len(
                list(output.parent.glob(".adapter.*.swap-recovery.json"))
            )
            skill_file.write_text(
                "---\nname: demo\n---\n\n# Changed\n",
                encoding="utf-8",
            )
            original_rename = adapters._rename_standard_directory

            def fail_publish_and_restore(source: Path, target: Path) -> Path:
                if source.name.endswith((".stage", ".rollback")):
                    raise OSError("injected double rename failure")
                return original_rename(source, target)

            with mock.patch.object(
                adapters,
                "_rename_standard_directory",
                side_effect=fail_publish_and_restore,
            ):
                with self.assertRaisesRegex(RuntimeError, "swap recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            recovery_path = output.parent / ".adapter.swap-recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertEqual(str(output), recovery["output"])
            rollback = Path(recovery["rollback"])
            stage = Path(recovery["stage"])
            self.assertTrue(rollback.is_dir())
            self.assertTrue(stage.is_dir())
            self.assertFalse(output.exists())

            with mock.patch.object(
                adapters,
                "_generated_resource",
                side_effect=ValueError("stop after recovery"),
            ):
                with self.assertRaisesRegex(ValueError, "stop after recovery"):
                    adapters.generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertFalse(recovery_path.exists())
            self.assertFalse(rollback.exists())
            self.assertTrue(stage.is_dir())
            self.assertEqual(
                initial_recovery_count + 1,
                len(list(output.parent.glob(".adapter.*.swap-recovery.json"))),
            )

    def test_pack_regeneration_refuses_and_preserves_unmanaged_empty_directory(self) -> None:
        from scripts.build_packs import build_pack

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            output_root = Path(temp) / "packs"
            output = output_root / "demo-pack"
            pack = {
                "id": "demo-pack",
                "description": "Demo pack",
                "skills": ["demo"],
                "depends_on": [],
            }
            build_pack(root, pack, output_root)
            unmanaged = output / "local-empty"
            unmanaged.mkdir()
            before = tree_digest(output)

            with self.assertRaisesRegex(RuntimeError, "unmanaged.*directory"):
                build_pack(root, pack, output_root)

            self.assertEqual(before, tree_digest(output))
            self.assertTrue(unmanaged.is_dir())

    def test_standard_adapter_regeneration_refuses_and_preserves_unmanaged_empty_directory(self) -> None:
        from scripts.generate_adapters import generate_adapter

        with temporary_directory() as temp:
            root = Path(temp) / "kit"
            skill = root / "skills" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "capabilities.yaml").write_text(
                "schema_version: 1\ncapabilities:\n"
                "- id: demo\n  path: skills/demo/SKILL.md\n",
                encoding="utf-8",
            )
            output = Path(temp) / "adapter"
            generate_adapter(root, "hermes", output)
            unmanaged = output / "local-empty"
            unmanaged.mkdir()
            before = tree_digest(output)

            with self.assertRaisesRegex(RuntimeError, "unmanaged.*directory"):
                generate_adapter(root, "hermes", output)

            self.assertEqual(before, tree_digest(output))
            self.assertTrue(unmanaged.is_dir())

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

    def test_adapters_are_deterministic_and_project_merge_preserves_local_skills(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, generate_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            temp_root = Path(temp)
            source_files = [
                path
                for path in (source_root / "skills").rglob("*")
                if path.is_file()
                and path.suffix.casefold() != ".pyc"
                and "__pycache__" not in path.parts
            ]
            for target in ("hermes", "codex"):
                output = temp_root / target
                report = generate_adapter(source_root, target, output)
                self.assertEqual(len(source_files) + 1, len(report["created"]))
                first = tree_digest(output)
                generate_adapter(source_root, target, output)
                self.assertEqual(first, tree_digest(output))
                self.assertTrue((output / "registry.json").exists())
                registry = json.loads((output / "registry.json").read_text(encoding="utf-8"))
                self.assertEqual(50, len(registry["skills"]))
                generated_skill = output / "skills" / "studio-project-intake" / "SKILL.md"
                generated_skill_lines = generated_skill.read_text(encoding="utf-8").splitlines()
                self.assertEqual("---", generated_skill_lines[0])
                self.assertEqual(
                    "# Generated by scripts/generate_adapters.py. Do not edit manually.",
                    generated_skill_lines[1],
                )
                helper = output / "skills" / "studio-project-scaffold" / "scripts" / "project_scaffold.py"
                self.assertTrue(helper.is_file())
                self.assertTrue(
                    helper.read_text(encoding="utf-8").startswith(
                        "# Generated by scripts/generate_adapters.py. Do not edit manually."
                    )
                )
                generated_schema = (
                    output
                    / "skills"
                    / "release-candidate-preflight"
                    / "schemas"
                    / "release-preflight.schema.json"
                )
                schema = json.loads(generated_schema.read_text(encoding="utf-8"))
                self.assertEqual(
                    "Generated by scripts/generate_adapters.py. Do not edit manually.",
                    schema["$comment"],
                )
                for role in ("investigator", "implementer", "verifier"):
                    template = output / "skills" / "studio-project-scaffold" / "templates" / "agents" / f"{role}.toml"
                    self.assertTrue(template.is_file(), template)
                    text = template.read_text(encoding="utf-8")
                    self.assertTrue(
                        text.startswith(
                            "# Generated by scripts/generate_adapters.py. Do not edit manually."
                        )
                    )
                    self.assertIn(
                        "# Generated by scripts/sync_skill_resources.py. Do not edit manually.",
                        text,
                    )
            project = temp_root / "project"
            local_skill = project / ".agents" / "skills" / "project-memory" / "SKILL.md"
            local_skill.parent.mkdir(parents=True)
            local_skill.write_text("local-owned\n", encoding="utf-8")
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )
            self.assertEqual("local-owned\n", local_skill.read_text(encoding="utf-8"))
            generated = project / ".agents" / "skills" / "studio-project-intake" / "SKILL.md"
            self.assertTrue(generated.exists())
            generated_lines = generated.read_text(encoding="utf-8").splitlines()
            self.assertEqual("---", generated_lines[0])
            self.assertEqual(
                "# Generated by scripts/generate_adapters.py. Do not edit manually.",
                generated_lines[1],
            )
            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            self.assertIn("project-memory", registry["skills"])
            self.assertIn("studio-project-intake", registry["skills"])
            helper_relative = ".agents/skills/studio-project-scaffold/scripts/project_scaffold.py"
            self.assertIn(helper_relative, {item["path"] for item in registry["kit_adapter"]["files"]})

    def test_project_adapter_uninstall_tracks_nested_resources_and_preserves_drift(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, uninstall_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )
            helper = project / ".agents" / "skills" / "studio-project-scaffold" / "scripts" / "project_scaffold.py"
            helper.write_text(helper.read_text(encoding="utf-8") + "# local note\n", encoding="utf-8")

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(helper.is_file())
            self.assertEqual("PARTIAL", report["status"])
            self.assertIn(
                ".agents/skills/studio-project-scaffold/scripts/project_scaffold.py",
                report["preserved_drift"],
            )
            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            remaining = {item["path"] for item in registry["kit_adapter"]["files"]}
            self.assertIn(
                ".agents/skills/studio-project-scaffold/scripts/project_scaffold.py",
                remaining,
            )

    def test_project_adapter_preserves_unmanaged_skill_that_mentions_generated_marker(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, report_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            skill_relative = ".agents/skills/studio-project-scaffold/SKILL.md"
            helper_relative = ".agents/skills/studio-project-scaffold/scripts/project_scaffold.py"
            skill = project / skill_relative
            skill.parent.mkdir(parents=True)
            local_text = (
                "---\n"
                "name: studio-project-scaffold\n"
                "---\n"
                "Local notes mention Generated by scripts/generate_adapters.py. "
                "Do not edit manually.\n"
            )
            skill.write_text(local_text, encoding="utf-8")

            report = report_project_adapter(source_root, project)

            self.assertIn(skill_relative, report["preserved"])
            self.assertNotIn(skill_relative, report["proposed"])
            self.assertNotIn(skill_relative, report["updated"])
            apply_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
                approved_plan_digest=report["plan_digest"],
            )

            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            owned = {item["path"] for item in registry["kit_adapter"]["files"]}
            self.assertEqual(local_text, skill.read_text(encoding="utf-8"))
            self.assertNotIn(skill_relative, owned)
            self.assertIn(helper_relative, owned)

    def test_project_adapter_local_skill_coexists_with_newly_owned_helpers_without_takeover(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            skill = project / ".agents" / "skills" / "studio-project-scaffold" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("local-owned scaffold skill\n", encoding="utf-8")

            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )

            skill_relative = ".agents/skills/studio-project-scaffold/SKILL.md"
            helper_relative = ".agents/skills/studio-project-scaffold/scripts/project_scaffold.py"
            helper = project / helper_relative
            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            owned = {item["path"] for item in registry["kit_adapter"]["files"]}
            self.assertEqual("local-owned scaffold skill\n", skill.read_text(encoding="utf-8"))
            self.assertNotIn(skill_relative, owned)
            self.assertIn(helper_relative, owned)

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(skill.is_file())
            self.assertFalse(helper.exists())
            self.assertNotIn(skill_relative, {item["path"] for item in report["remaining_owned"]})

    def test_project_adapter_regenerate_preserves_helper_ownership_after_local_skill_takeover(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            backup_root = project / ".adapter-backup"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=backup_root,
            )
            skill = project / ".agents" / "skills" / "studio-project-scaffold" / "SKILL.md"
            helper = skill.parent / "scripts" / "project_scaffold.py"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    "Generated by scripts/generate_adapters.py. Do not edit manually.",
                    "Local-owned scaffold skill.",
                    1,
                ),
                encoding="utf-8",
            )

            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup-2",
            )

            helper_relative = ".agents/skills/studio-project-scaffold/scripts/project_scaffold.py"
            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            self.assertIn(helper_relative, {item["path"] for item in registry["kit_adapter"]["files"]})

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(skill.is_file())
            self.assertFalse(helper.exists())
            self.assertIn(helper_relative, report["removed"])
            self.assertIn(
                ".agents/skills/studio-project-scaffold/SKILL.md",
                report["preserved_drift"],
            )

    def test_project_adapter_regenerate_retains_stale_owned_resources_until_uninstall(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            source_root = temp_root / "source"
            skill_root = source_root / "skills" / "sample-skill"
            (source_root / "registry").mkdir(parents=True)
            (skill_root / "scripts").mkdir(parents=True)
            (source_root / "registry" / "capabilities.yaml").write_text(
                "schema_version: 1\n"
                "capabilities:\n"
                "- id: sample-skill\n"
                "  path: skills/sample-skill/SKILL.md\n",
                encoding="utf-8",
            )
            (skill_root / "SKILL.md").write_text("---\nname: sample-skill\n---\n", encoding="utf-8")
            stale_source = skill_root / "scripts" / "stale.py"
            stale_source.write_text("print('stale')\n", encoding="utf-8")
            project = temp_root / "project"
            backup_root = project / ".adapter-backup"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=backup_root,
            )
            stale_relative = ".agents/skills/sample-skill/scripts/stale.py"
            stale_target = project / stale_relative
            stale_source.unlink()

            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup-2",
            )

            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            self.assertIn(stale_relative, {item["path"] for item in registry["kit_adapter"]["files"]})
            report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(report)
            self.assert_recovery_journal_truthful(project, report)
            self.assertFalse(stale_target.exists())
            self.assertIn(stale_relative, report["removed"])
            self.assertEqual([], report["preserved_drift"])

    def test_project_adapter_regenerate_retains_stale_owned_path_replaced_by_directory(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            source_root = temp_root / "source"
            skill_root = source_root / "skills" / "sample-skill"
            (source_root / "registry").mkdir(parents=True)
            (skill_root / "scripts").mkdir(parents=True)
            (source_root / "registry" / "capabilities.yaml").write_text(
                "schema_version: 1\n"
                "capabilities:\n"
                "- id: sample-skill\n"
                "  path: skills/sample-skill/SKILL.md\n",
                encoding="utf-8",
            )
            (skill_root / "SKILL.md").write_text("---\nname: sample-skill\n---\n", encoding="utf-8")
            stale_source = skill_root / "scripts" / "stale.py"
            stale_source.write_text("print('stale')\n", encoding="utf-8")
            project = temp_root / "project"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )
            stale_relative = ".agents/skills/sample-skill/scripts/stale.py"
            stale_target = project / stale_relative
            stale_source.unlink()
            stale_target.unlink()
            nested_empty = stale_target / "nested" / "empty"
            nested_empty.mkdir(parents=True)
            nested_content = stale_target / "nested" / "content.bin"
            nested_content.write_bytes(b"local subtree\x00content\n")

            def subtree_snapshot() -> list[tuple[str, str, bytes]]:
                snapshot: list[tuple[str, str, bytes]] = []
                for path in [stale_target, *sorted(stale_target.rglob("*"))]:
                    relative = path.relative_to(stale_target).as_posix() or "."
                    snapshot.append(
                        (relative, "directory", b"")
                        if path.is_dir()
                        else (relative, "file", path.read_bytes())
                    )
                return snapshot

            before_uninstall = subtree_snapshot()

            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup-2",
            )

            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            self.assertIn(stale_relative, {item["path"] for item in registry["kit_adapter"]["files"]})
            report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(report)
            self.assert_recovery_journal_truthful(project, report)
            self.assertEqual(before_uninstall, subtree_snapshot())
            self.assertEqual("PARTIAL", report["status"])
            self.assertIn(stale_relative, report["preserved_drift"])
            self.assertIn(stale_relative, {item["path"] for item in report["remaining_owned"]})

    def test_project_adapter_uninstall_preserves_drifted_stale_owned_resource(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            source_root = temp_root / "source"
            skill_root = source_root / "skills" / "sample-skill"
            (source_root / "registry").mkdir(parents=True)
            (skill_root / "scripts").mkdir(parents=True)
            (source_root / "registry" / "capabilities.yaml").write_text(
                "schema_version: 1\n"
                "capabilities:\n"
                "- id: sample-skill\n"
                "  path: skills/sample-skill/SKILL.md\n",
                encoding="utf-8",
            )
            (skill_root / "SKILL.md").write_text("---\nname: sample-skill\n---\n", encoding="utf-8")
            stale_source = skill_root / "scripts" / "stale.py"
            stale_source.write_text("print('stale')\n", encoding="utf-8")
            project = temp_root / "project"
            backup_root = project / ".adapter-backup"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=backup_root,
            )
            stale_relative = ".agents/skills/sample-skill/scripts/stale.py"
            stale_target = project / stale_relative
            stale_source.unlink()
            stale_target.write_text(
                stale_target.read_text(encoding="utf-8") + "# local note\n",
                encoding="utf-8",
            )

            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup-2",
            )
            report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(report)
            self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(stale_target.is_file())
            self.assertIn(stale_relative, report["preserved_drift"])
            self.assertIn(stale_relative, {item["path"] for item in report["remaining_owned"]})

    def test_project_adapter_uninstall_is_atomic_when_manifest_entry_is_malformed(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        malformed_entries = [
            None,
            {},
            {"path": 123, "sha256": "0" * 64},
            {"path": ".agents/skills/bad/SKILL.md"},
            {"path": ".agents/skills/bad/SKILL.md", "sha256": 123},
            {"path": ".agents/skills/bad/SKILL.md", "sha256": "not-a-sha256"},
            {"path": ".agents/skills/bad/../../escape", "sha256": "0" * 64},
        ]
        with temporary_directory() as temp:
            temp_root = Path(temp)
            for index, malformed in enumerate(malformed_entries):
                with self.subTest(malformed=malformed):
                    project = temp_root / f"project-{index}"
                    owned_relative = ".agents/skills/valid/SKILL.md"
                    owned = project / owned_relative
                    owned.parent.mkdir(parents=True)
                    owned.write_text("owned\n", encoding="utf-8")
                    valid = {
                        "path": owned_relative,
                        "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
                    }
                    registry_path = project / ".agents" / "registry.json"
                    registry = {
                        "schema_version": 1,
                        "skills": ["valid"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [valid, malformed],
                        },
                    }
                    registry_path.write_text(
                        json.dumps(registry, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    before_registry = registry_path.read_bytes()
                    before_owned = owned.read_bytes()

                    report = uninstall_project_adapter(project)

                    self.assert_uninstall_report_disjoint(report)

                    self.assert_recovery_journal_truthful(project, report)

                    self.assertEqual(
                        {"status", "removed", "preserved_drift", "remaining_owned"},
                        set(report),
                    )
                    self.assertEqual("PARTIAL", report["status"])
                    self.assertEqual([], report["removed"])
                    self.assertEqual([valid, malformed], report["remaining_owned"])
                    self.assertEqual(before_owned, owned.read_bytes())
                    self.assertEqual(before_registry, registry_path.read_bytes())

    def test_project_adapter_uninstall_preserves_unknown_adapter_version(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/future/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("future-owned\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry = {
                "schema_version": 1,
                "skills": ["future"],
                "kit_adapter": {
                    "adapter_id": "GameStudio-CodexKIT/per-project/v3",
                    "files": [ownership],
                },
            }
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
            before_registry = registry_path.read_bytes()

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual(
                {"status", "removed", "preserved_drift", "remaining_owned"},
                set(report),
            )
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertTrue(owned.is_file())
            self.assertEqual(before_registry, registry_path.read_bytes())

    def test_project_adapter_uninstall_cleanup_leaves_unmanaged_empty_directories(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/owned/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned\n", encoding="utf-8")
            unmanaged_empty = project / ".agents" / "skills" / "local-empty" / "nested"
            unmanaged_empty.mkdir(parents=True)
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["owned"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [
                                {
                                    "path": owned_relative,
                                    "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
                                }
                            ],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual(
                {"status", "removed", "preserved_drift", "remaining_owned"},
                set(report),
            )
            self.assertEqual("PASS", report["status"])
            self.assertEqual([], report["remaining_owned"])
            self.assertTrue(unmanaged_empty.is_dir())
            self.assertFalse(owned.exists())

    def test_project_adapter_uninstall_skill_membership_requires_complete_removal(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            partial_skill = project / ".agents" / "skills" / "partial"
            full_skill = project / ".agents" / "skills" / "full"
            partial_skill.mkdir(parents=True)
            full_skill.mkdir(parents=True)
            partial_removed = partial_skill / "SKILL.md"
            partial_remaining = partial_skill / "scripts" / "helper.py"
            partial_remaining.parent.mkdir(parents=True)
            full_removed = full_skill / "SKILL.md"
            partial_removed.write_text("owned partial\n", encoding="utf-8")
            partial_remaining.write_text("owned helper\nlocal drift\n", encoding="utf-8")
            full_removed.write_text("owned full\n", encoding="utf-8")
            ownership = [
                {
                    "path": ".agents/skills/partial/SKILL.md",
                    "sha256": hashlib.sha256(partial_removed.read_bytes()).hexdigest(),
                },
                {
                    "path": ".agents/skills/partial/scripts/helper.py",
                    "sha256": hashlib.sha256(b"owned helper\n").hexdigest(),
                },
                {
                    "path": ".agents/skills/full/SKILL.md",
                    "sha256": hashlib.sha256(full_removed.read_bytes()).hexdigest(),
                },
            ]
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["partial", "full"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": ownership,
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual(
                {"status", "removed", "preserved_drift", "remaining_owned"},
                set(report),
            )
            self.assertEqual("PARTIAL", report["status"])
            self.assertNotIn("partial", report)
            self.assertIn("full", report)
            self.assertFalse(partial_removed.exists())
            self.assertTrue(partial_remaining.is_file())
            self.assertFalse(full_removed.exists())

    @unittest.skipUnless(os.name == "nt", "Windows path alias semantics")
    def test_project_adapter_uninstall_rejects_windows_destination_aliases_atomically(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned = project / ".agents" / "skills" / "Mixed" / "SKILL.md"
            owned.parent.mkdir(parents=True)
            owned.write_text("owned alias\n", encoding="utf-8")
            digest = hashlib.sha256(owned.read_bytes()).hexdigest()
            ownership = [
                {"path": ".agents/skills/Mixed/SKILL.md", "sha256": digest},
                {"path": ".agents/skills/mixed/SKILL.md", "sha256": digest},
            ]
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["Mixed"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": ownership,
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            before_owned = owned.read_bytes()

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual(ownership, report["remaining_owned"])
            self.assertEqual(before_owned, owned.read_bytes())
            self.assertEqual(before_registry, registry_path.read_bytes())

    def test_project_adapter_uninstall_preserves_concurrent_hash_replacement(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/race/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned before race\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["race"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            original_replace = Path.replace
            raced = False

            def racing_replace(path: Path, target: Path) -> Path:
                nonlocal raced
                if path == owned and not raced:
                    raced = True
                    path.write_text("concurrent replacement\n", encoding="utf-8")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=racing_replace):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(raced)
            self.assertEqual("concurrent replacement\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertIn(owned_relative, report["preserved_drift"])
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertEqual(before_registry, registry_path.read_bytes())

    def test_project_adapter_uninstall_cleans_owned_quarantine_on_rollback_conflict(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/conflict/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned conflict\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["conflict"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            original_replace = Path.replace
            conflicted = False
            mapped_before_raise = False

            def conflicting_replace(path: Path, target: Path) -> Path:
                nonlocal conflicted, mapped_before_raise
                if path == owned and not conflicted:
                    conflicted = True
                    result = original_replace(path, target)
                    mapped_before_raise = (target.parent / "recovery.json").is_file()
                    path.write_text("concurrent destination\n", encoding="utf-8")
                    raise OSError("simulated post-move failure")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=conflicting_replace):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(conflicted)
            self.assertTrue(mapped_before_raise)
            self.assertEqual("concurrent destination\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertEqual(before_registry, registry_path.read_bytes())
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-quarantine-*")),
            )

    def test_project_adapter_uninstall_keyboard_interrupt_leaves_predeclared_recoverable_journal(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/interrupt/SKILL.md"
            second_relative = ".agents/skills/interrupt/scripts/helper.py"
            owned = project / owned_relative
            second = project / second_relative
            second.parent.mkdir(parents=True)
            owned.write_text("owned interrupt\n", encoding="utf-8")
            second.write_text("owned helper\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            second_ownership = {
                "path": second_relative,
                "sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["interrupt"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership, second_ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            original_replace = Path.replace
            interrupted = False

            def interrupting_replace(path: Path, target: Path) -> Path:
                nonlocal interrupted
                if path == owned and not interrupted:
                    interrupted = True
                    result = original_replace(path, target)
                    raise KeyboardInterrupt("simulated crash after first move")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=interrupting_replace):
                with self.assertRaises(KeyboardInterrupt):
                    uninstall_project_adapter(project)

            self.assertTrue(interrupted)
            self.assertFalse(owned.exists())
            quarantine_roots = list(
                (project / ".agents").glob(".adapter-uninstall-quarantine-*")
            )
            self.assertEqual(1, len(quarantine_roots))
            recovery_path = quarantine_roots[0] / "recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertTrue(recovery["transaction_id"])
            self.assertEqual("prepared", recovery["state"])
            self.assertEqual(2, len(recovery["files"]))
            self.assertEqual(owned_relative, recovery["files"][0]["path"])
            self.assertEqual(ownership["sha256"], recovery["files"][0]["sha256"])
            self.assertEqual(second_relative, recovery["files"][1]["path"])
            self.assertEqual(second_ownership["sha256"], recovery["files"][1]["sha256"])
            quarantined = project / recovery["files"][0]["quarantine_path"]
            second_quarantine = project / recovery["files"][1]["quarantine_path"]
            self.assertTrue(quarantined.is_file())
            self.assertFalse(second_quarantine.exists())
            self.assertEqual("owned helper\n", second.read_text(encoding="utf-8"))

            with mock.patch(
                "scripts.generate_adapters._write_registry_atomically",
                side_effect=OSError("stop after stale recovery"),
            ):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("owned interrupt\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("owned helper\n", second.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([ownership, second_ownership], report["remaining_owned"])
            self.assertEqual(before_registry, registry_path.read_bytes())
            self.assertNotIn("recovery_manifest", report)
            self.assertNotIn("recovery_owned", report)
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-quarantine-*")),
            )

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_project_adapter_uninstall_rejects_junction_stale_quarantine_without_traversal(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            temp_root = Path(temp)
            project = temp_root / "project"
            agents_root = project / ".agents"
            agents_root.mkdir(parents=True)
            registry_path = agents_root / "registry.json"
            registry_path.write_text(
                json.dumps({"schema_version": 1, "skills": []}, indent=2) + "\n",
                encoding="utf-8",
            )
            transaction_id = "externaljunction"
            quarantine_name = f".adapter-uninstall-quarantine-{transaction_id}"
            junction = agents_root / quarantine_name
            external = temp_root / "external-recovery"
            external.mkdir()
            external_owned = external / "00000000.owned"
            external_owned.write_bytes(b"external owned bytes\n")
            external_recovery = external / "recovery.json"
            external_recovery.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "registry_committed",
                        "files": [
                            {
                                "path": ".agents/skills/external/SKILL.md",
                                "quarantine_path": (
                                    f".agents/{quarantine_name}/00000000.owned"
                                ),
                                "sha256": hashlib.sha256(
                                    external_owned.read_bytes()
                                ).hexdigest(),
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_owned = external_owned.read_bytes()
            before_recovery = external_recovery.read_bytes()
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(external)],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                self.skipTest(
                    f"junction creation unavailable: {completed.stderr or completed.stdout}"
                )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(junction.relative_to(project).as_posix(), report["unsafe_recovery"])
            self.assertNotIn("recovery_manifest", report)
            self.assertNotIn("recovery_owned", report)
            self.assertTrue(os.path.lexists(junction))
            self.assertEqual(before_owned, external_owned.read_bytes())
            self.assertEqual(before_recovery, external_recovery.read_bytes())

    def test_project_adapter_uninstall_removes_empty_journal_less_quarantine_root(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            agents_root = project / ".agents"
            agents_root.mkdir(parents=True)
            registry_path = agents_root / "registry.json"
            registry_path.write_text(
                json.dumps({"schema_version": 1, "skills": []}, indent=2) + "\n",
                encoding="utf-8",
            )
            orphan = agents_root / ".adapter-uninstall-quarantine-emptyorphan"
            orphan.mkdir()

            first_report = uninstall_project_adapter(project)
            second_report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(first_report)
            self.assert_recovery_journal_truthful(project, first_report)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            self.assertEqual("PASS", first_report["status"])
            self.assertFalse(os.path.lexists(orphan))
            self.assertNotIn("recovery_manifest", first_report)
            self.assertNotIn("unsafe_recovery", first_report)
            self.assertEqual("PASS", second_report["status"])
            self.assertNotIn("recovery_manifest", second_report)
            self.assertNotIn("unsafe_recovery", second_report)

    def test_project_adapter_uninstall_preserves_nonempty_journal_less_quarantine_root(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            agents_root = project / ".agents"
            agents_root.mkdir(parents=True)
            registry_path = agents_root / "registry.json"
            registry_path.write_text(
                json.dumps({"schema_version": 1, "skills": []}, indent=2) + "\n",
                encoding="utf-8",
            )
            orphan = agents_root / ".adapter-uninstall-quarantine-nonemptyorphan"
            orphan.mkdir()
            unknown = orphan / "unknown.bin"
            unknown.write_bytes(b"unknown recovery bytes\n")
            before = unknown.read_bytes()
            unsafe_relative = orphan.relative_to(project).as_posix()

            first_report = uninstall_project_adapter(project)
            second_report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(first_report)
            self.assert_recovery_journal_truthful(project, first_report)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            for report in (first_report, second_report):
                self.assertEqual("PARTIAL", report["status"])
                self.assertEqual(unsafe_relative, report["unsafe_recovery"])
                self.assertNotIn("recovery_manifest", report)
                self.assertNotIn("recovery_owned", report)
            self.assertTrue(os.path.lexists(orphan))
            self.assertEqual(before, unknown.read_bytes())

    def test_project_adapter_uninstall_stale_journal_preserves_concurrent_destination(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/stale-concurrent/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("concurrent destination\n", encoding="utf-8")
            expected_content = b"owned stale journal\n"
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(expected_content).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["stale-concurrent"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            transaction_id = "staleconcurrent"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir()
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            recovery_path = quarantine_root / "recovery.json"
            recovery_relative = recovery_path.relative_to(project).as_posix()
            quarantine_relative = quarantined.relative_to(project).as_posix()
            recovery_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantine_relative,
                                "sha256": ownership["sha256"],
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("concurrent destination\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(recovery_relative, report["recovery_manifest"])
            self.assertEqual(
                [
                    {
                        "path": owned_relative,
                        "quarantine_path": quarantine_relative,
                        "sha256": ownership["sha256"],
                    }
                ],
                report["recovery_owned"],
            )
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertTrue(quarantined.is_file())
            self.assertEqual(before_registry, registry_path.read_bytes())
            self.assertNotIn("stale-concurrent", report)

    def test_project_adapter_uninstall_stale_journal_without_registry_requires_manual_recovery(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/missing-registry/SKILL.md"
            expected_content = b"owned missing registry\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "missingregistry"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            recovery_path = quarantine_root / "recovery.json"
            quarantine_relative = quarantined.relative_to(project).as_posix()
            recovery_relative = recovery_path.relative_to(project).as_posix()
            recovery_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantine_relative,
                                "sha256": ownership_hash,
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(recovery_relative, report["recovery_manifest"])
            self.assertEqual(
                [
                    {
                        "path": owned_relative,
                        "quarantine_path": quarantine_relative,
                        "sha256": ownership_hash,
                    }
                ],
                report["recovery_owned"],
            )
            self.assertTrue(quarantined.is_file())

    def test_project_adapter_uninstall_registry_failure_restores_quarantined_target(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/registry-failure/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned registry failure\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["registry-failure"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()

            with mock.patch(
                "scripts.generate_adapters._write_registry_atomically",
                side_effect=OSError("simulated registry commit failure"),
            ):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("owned registry failure\n", owned.read_text(encoding="utf-8"))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([ownership], report["remaining_owned"])
            self.assertEqual(before_registry, registry_path.read_bytes())
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-quarantine-*")),
            )

    def test_project_adapter_uninstall_cleanup_failure_preserves_durable_recovery(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/cleanup-failure/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned cleanup\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["cleanup-failure"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()
            original_unlink = Path.unlink
            cleanup_failed = False

            def failing_unlink(path: Path, *args: object, **kwargs: object) -> None:
                nonlocal cleanup_failed
                if (
                    path.parent.name.startswith(".adapter-uninstall-quarantine-")
                    and path.suffix == ".owned"
                ):
                    cleanup_failed = True
                    raise OSError("simulated quarantine cleanup failure")
                original_unlink(path, *args, **kwargs)

            with mock.patch.object(Path, "unlink", new=failing_unlink):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(cleanup_failed)
            self.assertFalse(owned.exists())
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([], report["remaining_owned"])
            self.assertNotEqual(before_registry, registry_path.read_bytes())
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertNotIn("kit_adapter", registry)
            quarantine_roots = list(
                (project / ".agents").glob(".adapter-uninstall-quarantine-*")
            )
            self.assertEqual(1, len(quarantine_roots))
            recovery_path = quarantine_roots[0] / "recovery.json"
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            recovery_relative = recovery_path.relative_to(project).as_posix()
            quarantine_relative = recovery["files"][0]["quarantine_path"]
            self.assertEqual(recovery_relative, report["recovery_manifest"])
            self.assertEqual(
                [
                    {
                        "path": owned_relative,
                        "quarantine_path": quarantine_relative,
                        "sha256": ownership["sha256"],
                    }
                ],
                report["recovery_owned"],
            )
            self.assertEqual("GameStudio-CodexKIT/per-project/v2", recovery["adapter_id"])
            self.assertEqual(1, recovery["schema_version"])
            self.assertEqual(owned_relative, recovery["files"][0]["path"])
            self.assertEqual(ownership["sha256"], recovery["files"][0]["sha256"])
            quarantined = project / quarantine_relative
            self.assertTrue(quarantined.is_file())
            self.assertEqual(ownership["sha256"], hashlib.sha256(quarantined.read_bytes()).hexdigest())

    def test_project_adapter_uninstall_deduplicates_root_and_durable_recovery(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/duplicate-recovery/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned duplicate recovery\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["duplicate-recovery"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_replace = Path.replace
            original_unlink = Path.unlink
            unlink_failed = False

            def deny_canonical_replacement(path: Path, target: Path) -> Path:
                if target.name == "recovery.json" and target.exists():
                    raise PermissionError(13, "simulated recovery replace denial")
                return original_replace(path, target)

            def fail_one_internal_generation_unlink(
                path: Path, *args: object, **kwargs: object
            ) -> None:
                nonlocal unlink_failed
                if (
                    not unlink_failed
                    and path.parent.name.startswith(".adapter-uninstall-quarantine-")
                    and path.name.startswith("recovery.")
                    and path.name != "recovery.json"
                    and path.name.endswith(".json")
                ):
                    unlink_failed = True
                    raise OSError("simulated internal recovery generation unlink failure")
                original_unlink(path, *args, **kwargs)

            with mock.patch.object(
                Path, "replace", new=deny_canonical_replacement
            ), mock.patch.object(
                Path, "unlink", new=fail_one_internal_generation_unlink
            ):
                first_report = uninstall_project_adapter(project)

            self.assertTrue(unlink_failed)
            self.assertEqual("PARTIAL", first_report["status"])
            first_manifest = project / first_report["recovery_manifest"]
            self.assertTrue(first_manifest.is_file())
            quarantine_roots = [
                path
                for path in (project / ".agents").glob(
                    ".adapter-uninstall-quarantine-*"
                )
                if path.is_dir()
            ]
            durable_siblings = list(
                (project / ".agents").glob(
                    ".adapter-uninstall-quarantine-*.recovery.json"
                )
            )
            self.assertEqual(1, len(quarantine_roots))
            self.assertEqual(1, len(durable_siblings))
            self.assertGreaterEqual(
                len(list(quarantine_roots[0].glob("recovery.*.json"))),
                1,
            )

            second_report = uninstall_project_adapter(project)

            self.assertEqual("PASS", second_report["status"])
            self.assertNotIn("recovery_manifest", second_report)
            self.assertNotIn("unsafe_recovery", second_report)
            self.assertEqual(
                [],
                list(
                    (project / ".agents").glob(
                        ".adapter-uninstall-quarantine-*"
                    )
                ),
            )

            third_report = uninstall_project_adapter(project)

            self.assertEqual("PASS", third_report["status"])
            self.assertEqual([], third_report["removed"])
            self.assertNotIn("recovery_manifest", third_report)
            self.assertNotIn("unsafe_recovery", third_report)

    def test_project_adapter_uninstall_reports_newer_invalid_durable_sibling(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/newer-invalid-sibling/SKILL.md"
            expected_content = b"owned newer invalid sibling\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "newerinvalidsibling"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            recovery_path = quarantine_root / "recovery.json"
            quarantine_relative = quarantined.relative_to(project).as_posix()
            base_recovery = {
                "schema_version": 1,
                "transaction_id": transaction_id,
                "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                "state": "prepared",
                "files": [
                    {
                        "path": owned_relative,
                        "quarantine_path": quarantine_relative,
                        "sha256": ownership_hash,
                        "state": "moved",
                    }
                ],
            }
            recovery_path.write_text(
                json.dumps(
                    {
                        **base_recovery,
                        "revision": 2,
                        "generation": 2,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            durable = quarantine_root.with_name(
                f"{quarantine_root.name}.recovery.json"
            )
            durable_payload = {
                **base_recovery,
                "revision": 999,
                "generation": 999,
                "files": [
                    {
                        **base_recovery["files"][0],
                        "state": "removed",
                        "artifact_present": False,
                    }
                ],
            }
            durable_bytes = (
                json.dumps(durable_payload, indent=2) + "\n"
            ).encode("utf-8")
            durable.write_bytes(durable_bytes)

            first_report = uninstall_project_adapter(project)
            second_report = uninstall_project_adapter(project)

            for report in (first_report, second_report):
                self.assertEqual("PARTIAL", report["status"])
                self.assertEqual(
                    recovery_path.relative_to(project).as_posix(),
                    report["recovery_manifest"],
                )
                self.assertEqual(
                    durable.relative_to(project).as_posix(),
                    report["unsafe_recovery"],
                )
                self.assertEqual(
                    [
                        {
                            "path": owned_relative,
                            "quarantine_path": quarantine_relative,
                            "sha256": ownership_hash,
                        }
                    ],
                    report["recovery_owned"],
                )
            self.assertEqual(expected_content, quarantined.read_bytes())
            self.assertEqual(durable_bytes, durable.read_bytes())

    def test_project_adapter_uninstall_reports_malformed_durable_sibling_once(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/malformed-sibling/SKILL.md"
            expected_content = b"owned malformed sibling\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "malformedsibling"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            recovery_path = quarantine_root / "recovery.json"
            recovery_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": 2,
                        "generation": 2,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantined.relative_to(project).as_posix(),
                                "sha256": ownership_hash,
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            durable = quarantine_root.with_name(
                f"{quarantine_root.name}.recovery.json"
            )
            malformed_bytes = b'{"schema_version": 1, "revision":'
            durable.write_bytes(malformed_bytes)

            first_report = uninstall_project_adapter(project)
            second_report = uninstall_project_adapter(project)

            for report in (first_report, second_report):
                self.assertEqual("PARTIAL", report["status"])
                self.assertEqual(
                    recovery_path.relative_to(project).as_posix(),
                    report["recovery_manifest"],
                )
                self.assertEqual(
                    durable.relative_to(project).as_posix(),
                    report["unsafe_recovery"],
                )
                self.assertEqual(
                    [owned_relative],
                    [item["path"] for item in report["recovery_owned"]],
                )
            self.assertEqual(expected_content, quarantined.read_bytes())
            self.assertEqual(malformed_bytes, durable.read_bytes())

    def test_project_adapter_uninstall_root_cleanup_failure_preserves_durable_recovery(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/root-cleanup/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned root cleanup\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["root-cleanup"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_rmdir = Path.rmdir

            def failing_rmdir(path: Path) -> None:
                if path.name.startswith(".adapter-uninstall-quarantine-"):
                    raise OSError("simulated quarantine root cleanup failure")
                original_rmdir(path)

            with mock.patch.object(Path, "rmdir", new=failing_rmdir):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertFalse(owned.exists())
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([owned_relative], report["removed"])
            self.assertEqual([], report["preserved_drift"])
            self.assertEqual([], report["remaining_owned"])
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertNotIn("kit_adapter", registry)
            recovery_paths = list(
                (project / ".agents").glob(
                    ".adapter-uninstall-quarantine-*.recovery.json"
                )
            )
            self.assertEqual(1, len(recovery_paths))
            recovery_relative = recovery_paths[0].relative_to(project).as_posix()
            recovery = json.loads(recovery_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(recovery_relative, report["recovery_manifest"])
            self.assertEqual([], report["recovery_owned"])
            self.assertEqual(owned_relative, recovery["files"][0]["path"])
            self.assertEqual(ownership["sha256"], recovery["files"][0]["sha256"])
            self.assertEqual("removed", recovery["files"][0]["state"])
            quarantined = project / recovery["files"][0]["quarantine_path"]
            self.assertFalse(os.path.lexists(quarantined))

            second_report = uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            self.assertEqual("PASS", second_report["status"])
            self.assertEqual([], second_report["removed"])
            self.assertNotIn("recovery_manifest", second_report)
            self.assertFalse(recovery_paths[0].exists())
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-quarantine-*")),
            )

    def test_project_adapter_uninstall_survives_windows_recovery_replace_denial(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/replace-denial/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned replace denial\n", encoding="utf-8")
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["replace-denial"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [
                                {
                                    "path": owned_relative,
                                    "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
                                }
                            ],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_replace = Path.replace
            denied = False

            def deny_existing_recovery_replace(path: Path, target: Path) -> Path:
                nonlocal denied
                if target.name == "recovery.json" and target.exists():
                    denied = True
                    raise PermissionError(13, "simulated Windows recovery replace denial")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=deny_existing_recovery_replace):
                report = uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(denied)
            self.assertEqual("PASS", report["status"])
            self.assertEqual([owned_relative], report["removed"])
            self.assertFalse(owned.exists())
            self.assertNotIn("recovery_manifest", report)

    def test_project_adapter_uninstall_replace_denial_interruption_keeps_old_journal(self) -> None:
        from scripts import generate_adapters as adapters

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/interrupted-generation/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned interrupted generation\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["interrupted-generation"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_replace = Path.replace
            interrupted = False

            def interrupt_generation_publish(path: Path, target: Path) -> Path:
                nonlocal interrupted
                if target.name == "recovery.json" and target.exists():
                    raise PermissionError(13, "simulated recovery replace denial")
                if (
                    target.name != "recovery.json"
                    and target.name.startswith("recovery.")
                    and target.name.endswith(".json")
                ):
                    interrupted = True
                    target.write_bytes(b'{"partial":')
                    raise OSError("simulated interrupted generation publication")
                return original_replace(path, target)

            with mock.patch.object(Path, "replace", new=interrupt_generation_publish):
                first_report = adapters.uninstall_project_adapter(project)

            self.assertTrue(interrupted)
            quarantine_root = next(
                (project / ".agents").glob(".adapter-uninstall-quarantine-*")
            )
            canonical = quarantine_root / "recovery.json"
            canonical_payload = json.loads(canonical.read_text(encoding="utf-8"))
            self.assertEqual("prepared", canonical_payload["state"])
            self.assertEqual("PARTIAL", first_report["status"])
            self.assertEqual(
                canonical.relative_to(project).as_posix(),
                first_report["recovery_manifest"],
            )

            second_report = adapters.uninstall_project_adapter(project)

            self.assertEqual("PARTIAL", second_report["status"])
            self.assertEqual(
                canonical.relative_to(project).as_posix(),
                second_report["recovery_manifest"],
            )
            self.assertEqual(
                [owned_relative],
                [item["path"] for item in second_report["recovery_owned"]],
            )
            self.assertIn("unsafe_recovery", second_report)
            self.assertEqual(canonical_payload, json.loads(canonical.read_text(encoding="utf-8")))

    def test_project_adapter_uninstall_selects_newer_recovery_generation(self) -> None:
        from scripts import generate_adapters as adapters

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/newer-generation/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned newer generation\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["newer-generation"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_replace = Path.replace
            original_write = adapters._write_registry_atomically

            def deny_canonical_replace(path: Path, target: Path) -> Path:
                if target.name == "recovery.json" and target.exists():
                    raise PermissionError(13, "simulated recovery replace denial")
                return original_replace(path, target)

            def drift_after_commit(path: Path, registry: dict[str, object]) -> None:
                original_write(path, registry)
                quarantine_root = next(
                    (project / ".agents").glob(".adapter-uninstall-quarantine-*")
                )
                next(quarantine_root.glob("*.owned")).write_bytes(b"drifted generation\n")

            with mock.patch.object(Path, "replace", new=deny_canonical_replace), mock.patch.object(
                adapters,
                "_write_registry_atomically",
                side_effect=drift_after_commit,
            ):
                first_report = adapters.uninstall_project_adapter(project)

            selected = project / first_report["recovery_manifest"]
            selected_payload = json.loads(selected.read_text(encoding="utf-8"))
            self.assertRegex(selected.name, r"^recovery\.\d{8}\.json$")
            self.assertGreater(selected_payload["revision"], 0)
            self.assertEqual("drifted", selected_payload["files"][0]["state"])

            second_report = adapters.uninstall_project_adapter(project)

            self.assertEqual(first_report["recovery_manifest"], second_report["recovery_manifest"])
            self.assertEqual([owned_relative], second_report["preserved_drift"])

    def test_project_adapter_uninstall_invalid_newer_generation_keeps_valid_visibility(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/invalid-generation/SKILL.md"
            expected_content = b"owned invalid generation\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "invalidgeneration"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            canonical = quarantine_root / "recovery.json"
            canonical.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": 0,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantined.relative_to(project).as_posix(),
                                "sha256": ownership_hash,
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            invalid = quarantine_root / "recovery.99999999.json"
            invalid_bytes = b'{"schema_version": 1, "revision": 99999999'
            invalid.write_bytes(invalid_bytes)

            report = uninstall_project_adapter(project)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(canonical.relative_to(project).as_posix(), report["recovery_manifest"])
            self.assertEqual(invalid.relative_to(project).as_posix(), report["unsafe_recovery"])
            self.assertEqual(
                [owned_relative],
                [item["path"] for item in report["recovery_owned"]],
            )
            self.assertEqual(expected_content, quarantined.read_bytes())
            self.assertEqual(invalid_bytes, invalid.read_bytes())

    def test_project_adapter_uninstall_structurally_invalid_older_generation_stays_unsafe(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/invalid-older-generation/SKILL.md"
            expected_content = b"owned invalid older generation\n"
            ownership_hash = hashlib.sha256(expected_content).hexdigest()
            transaction_id = "invalidoldergeneration"
            quarantine_root = project / ".agents" / (
                f".adapter-uninstall-quarantine-{transaction_id}"
            )
            quarantine_root.mkdir(parents=True)
            quarantined = quarantine_root / "00000000.owned"
            quarantined.write_bytes(expected_content)
            canonical = quarantine_root / "recovery.json"
            canonical.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": 1,
                        "generation": 1,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [
                            {
                                "path": owned_relative,
                                "quarantine_path": quarantined.relative_to(project).as_posix(),
                                "sha256": ownership_hash,
                                "state": "moved",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            invalid = quarantine_root / "recovery.00000000.json"
            invalid_bytes = (
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": 0,
                        "generation": 0,
                        "transaction_id": transaction_id,
                        "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                        "state": "prepared",
                        "files": [{"path": owned_relative}],
                    },
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")
            invalid.write_bytes(invalid_bytes)

            report = uninstall_project_adapter(project)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual(canonical.relative_to(project).as_posix(), report["recovery_manifest"])
            self.assertEqual(invalid.relative_to(project).as_posix(), report["unsafe_recovery"])
            self.assertEqual(expected_content, quarantined.read_bytes())
            self.assertEqual(invalid_bytes, invalid.read_bytes())

    def test_recovery_journal_writer_has_no_in_place_overwrite_fallback(self) -> None:
        import inspect
        from scripts import generate_adapters as adapters

        source = inspect.getsource(adapters._write_quarantine_recovery_manifest)

        self.assertNotIn('open("r+"', source)
        self.assertNotIn(".truncate()", source)

    def test_project_adapter_uninstall_records_missing_quarantine_after_registry_commit(self) -> None:
        from scripts import generate_adapters as adapters

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/missing-quarantine/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned missing quarantine\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["missing-quarantine"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            original_write = adapters._write_registry_atomically

            def delete_quarantine_after_commit(
                path: Path, registry: dict[str, object]
            ) -> None:
                original_write(path, registry)
                quarantine_root = next(
                    (project / ".agents").glob(".adapter-uninstall-quarantine-*")
                )
                next(quarantine_root.glob("*.owned")).unlink()

            with mock.patch.object(
                adapters,
                "_write_registry_atomically",
                side_effect=delete_quarantine_after_commit,
            ):
                report = adapters.uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([owned_relative], report["preserved_drift"])
            recovery_path = project / report["recovery_manifest"]
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            self.assertEqual("missing", recovery["files"][0]["state"])
            self.assertFalse(
                os.path.lexists(project / recovery["files"][0]["quarantine_path"])
            )

            second_report = adapters.uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            self.assertEqual("PARTIAL", second_report["status"])
            self.assertEqual([], second_report["removed"])
            self.assertEqual([owned_relative], second_report["preserved_drift"])
            self.assertEqual(report["recovery_manifest"], second_report["recovery_manifest"])
            self.assertTrue(recovery_path.is_file())

    def test_project_adapter_uninstall_records_drifted_quarantine_after_registry_commit(self) -> None:
        from scripts import generate_adapters as adapters

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/drifted-quarantine/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned drifted quarantine\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["drifted-quarantine"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            drifted_bytes = b"concurrent quarantine replacement\n"
            original_write = adapters._write_registry_atomically

            def drift_quarantine_after_commit(
                path: Path, registry: dict[str, object]
            ) -> None:
                original_write(path, registry)
                quarantine_root = next(
                    (project / ".agents").glob(".adapter-uninstall-quarantine-*")
                )
                next(quarantine_root.glob("*.owned")).write_bytes(drifted_bytes)

            with mock.patch.object(
                adapters,
                "_write_registry_atomically",
                side_effect=drift_quarantine_after_commit,
            ):
                report = adapters.uninstall_project_adapter(project)
                self.assert_uninstall_report_disjoint(report)
                self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertEqual([owned_relative], report["preserved_drift"])
            recovery_path = project / report["recovery_manifest"]
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            record = recovery["files"][0]
            self.assertEqual("drifted", record["state"])
            self.assertEqual(
                hashlib.sha256(drifted_bytes).hexdigest(),
                record["observed_sha256"],
            )
            quarantined = project / record["quarantine_path"]
            self.assertEqual(drifted_bytes, quarantined.read_bytes())

            second_report = adapters.uninstall_project_adapter(project)
            self.assert_uninstall_report_disjoint(second_report)
            self.assert_recovery_journal_truthful(project, second_report)

            self.assertEqual("PARTIAL", second_report["status"])
            self.assertEqual([], second_report["removed"])
            self.assertEqual([owned_relative], second_report["preserved_drift"])
            self.assertEqual(report["recovery_manifest"], second_report["recovery_manifest"])
            self.assertEqual(drifted_bytes, quarantined.read_bytes())

    def test_project_adapter_uninstall_success_omits_recovery_fields_and_residue(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/success/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            owned.write_text("owned success\n", encoding="utf-8")
            ownership = {
                "path": owned_relative,
                "sha256": hashlib.sha256(owned.read_bytes()).hexdigest(),
            }
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["success"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertEqual("PASS", report["status"])
            self.assertEqual([owned_relative], report["removed"])
            self.assertNotIn("recovery_manifest", report)
            self.assertNotIn("recovery_owned", report)
            self.assertFalse(owned.exists())
            self.assertEqual(
                [],
                list((project / ".agents").glob(".adapter-uninstall-*")),
            )

    def test_project_adapter_uninstall_preserves_broken_owned_link(self) -> None:
        from scripts.generate_adapters import uninstall_project_adapter

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            owned_relative = ".agents/skills/linked/SKILL.md"
            owned = project / owned_relative
            owned.parent.mkdir(parents=True)
            try:
                os.symlink("missing-target", owned)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            ownership = {"path": owned_relative, "sha256": "0" * 64}
            registry_path = project / ".agents" / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills": ["linked"],
                        "kit_adapter": {
                            "adapter_id": "GameStudio-CodexKIT/per-project/v2",
                            "files": [ownership],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = uninstall_project_adapter(project)

            self.assert_uninstall_report_disjoint(report)

            self.assert_recovery_journal_truthful(project, report)

            self.assertTrue(os.path.lexists(owned))
            self.assertEqual("PARTIAL", report["status"])
            self.assertEqual([], report["removed"])
            self.assertIn(owned_relative, report["preserved_drift"])
            self.assertEqual([ownership], report["remaining_owned"])

    def test_project_adapter_plans_overlay_before_writing_any_output(self) -> None:
        from scripts.generate_adapters import report_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            profile_path = project / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text("schema_version: 99\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                report_project_adapter(source_root, project)

            self.assertFalse((project / ".agents" / "skills").exists())
            self.assertFalse((project / ".codex").exists())
            self.assertFalse((project / ".agents" / "registry.json").exists())

    def test_project_adapter_report_includes_overlay_collisions_and_roles(self) -> None:
        from scripts.agent_overlay import MARKER
        from scripts.generate_adapters import report_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            local_agent = project / ".codex" / "agents" / "investigator.toml"
            local_agent.parent.mkdir(parents=True)
            local_agent.write_text(
                f'name = "local-investigator"\ndescription = "mentions {MARKER}"\n',
                encoding="utf-8",
            )
            activation = project / ".codex" / "agents.generated.toml"
            activation.write_text(
                f'[agents.local]\ndescription = "mentions {MARKER}"\n',
                encoding="utf-8",
            )

            report = report_project_adapter(source_root, project)

            self.assertEqual(
                [
                    {
                        "path": ".codex/agents.generated.toml",
                        "kind": "unmanaged-activation",
                    },
                    {
                        "path": ".codex/agents/investigator.toml",
                        "kind": "unmanaged-agent",
                        "role_id": "investigator",
                    },
                ],
                report["collisions"],
            )
            self.assertEqual([], report["activated_roles"])

    def test_project_adapter_delegates_agent_overlay_planning(self) -> None:
        import scripts.generate_adapters as adapters
        from scripts.agent_overlay import plan_agent_overlay

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            with mock.patch.object(
                adapters,
                "plan_agent_overlay",
                wraps=plan_agent_overlay,
            ) as planner:
                adapters.report_project_adapter(source_root, project)

            planner.assert_called_once_with(
                project,
                template_root=(
                    source_root / "skills" / "studio-project-scaffold" / "templates" / "agents"
                ),
                profile_path=project / ".agents" / "project-profile.yaml",
                known_skills=mock.ANY,
            )

    def test_project_adapter_materializes_agent_roles_and_preserves_local_agents(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, uninstall_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            local_agent = project / ".codex" / "agents" / "project-specialist.toml"
            local_agent.parent.mkdir(parents=True)
            local_agent.write_text("name = 'project-specialist'\n", encoding="utf-8")

            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )

            generated_agents = {
                role: project / ".codex" / "agents" / f"{role}.toml"
                for role in ("investigator", "implementer", "verifier")
            }
            for generated in generated_agents.values():
                self.assertTrue(generated.is_file(), generated)
                self.assertIn("Generated by scripts/generate_adapters.py", generated.read_text(encoding="utf-8"))
            activation = project / ".codex" / "agents.generated.toml"
            self.assertTrue(activation.is_file())
            self.assertEqual("name = 'project-specialist'\n", local_agent.read_text(encoding="utf-8"))

            generated_agents["verifier"].write_text(
                generated_agents["verifier"].read_text(encoding="utf-8") + "# local note\n",
                encoding="utf-8",
            )
            uninstall_project_adapter(project)

            self.assertFalse(generated_agents["investigator"].exists())
            self.assertFalse(generated_agents["implementer"].exists())
            self.assertTrue(generated_agents["verifier"].exists())
            self.assertTrue(local_agent.exists())
            registry = json.loads((project / ".agents" / "registry.json").read_text(encoding="utf-8"))
            remaining = {item["path"] for item in registry["kit_adapter"]["files"]}
            self.assertIn(".codex/agents/verifier.toml", remaining)

    def test_project_adapter_materializes_profile_specialist(self) -> None:
        import tomllib
        import yaml

        from scripts.generate_adapters import apply_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            profile_path = project / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 1,
                        "workspace": {
                            "name": "sample-game",
                            "root_git": False,
                            "default_concurrency": 2,
                        },
                        "repositories": [
                            {
                                "id": "server",
                                "path": "server",
                                "git_root": True,
                                "subsystems": ["server", "lua"],
                                "owner_skill": "studio-project-intake",
                                "validation": [],
                            }
                        ],
                        "exclusions": [],
                        "agents": {
                            "specialists": [
                                {
                                    "id": "server-specialist",
                                    "repository": "server",
                                    "reasoning_effort": "xhigh",
                                    "constraints": [
                                        "preserve frame budget",
                                        "preserve protocol compatibility",
                                    ],
                                }
                            ]
                        },
                        "cross_project_contracts": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            report = apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )

            specialist = project / ".codex" / "agents" / "server-specialist.toml"
            self.assertTrue(specialist.is_file())
            specialist_text = specialist.read_text(encoding="utf-8")
            self.assertIn("model_reasoning_effort = 'xhigh'", specialist_text)
            self.assertIn("preserve frame budget", specialist_text)
            activation = (project / ".codex" / "agents.generated.toml").read_text(encoding="utf-8")
            self.assertIn("[agents.server-specialist]", activation)
            self.assertIn("server-specialist", report["activated_roles"])

            codex_root = project / ".codex"
            for agent_path in sorted((codex_root / "agents").glob("*.toml")):
                agent = tomllib.loads(agent_path.read_text(encoding="utf-8-sig"))
                self.assertEqual(agent_path.stem, agent["name"])
                for field in ("name", "description", "developer_instructions"):
                    self.assertIsInstance(agent.get(field), str, (agent_path, field))
                    self.assertTrue(agent[field].strip(), (agent_path, field))

            activation_data = tomllib.loads(activation)
            for role_id, role in activation_data["agents"].items():
                config_file = role["config_file"]
                self.assertIsInstance(config_file, str)
                self.assertTrue(config_file.strip())
                resolved = (codex_root / config_file).resolve()
                self.assertTrue(resolved.is_relative_to(codex_root.resolve()))
                self.assertTrue(resolved.is_file(), (role_id, resolved))

    def test_project_adapter_refuses_reparse_points_in_skill_destinations(self) -> None:
        import scripts.generate_adapters as adapters

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            reparse_target = project / ".agents" / "skills" / "studio-project-intake"
            reparse_target.mkdir(parents=True)
            original_check = adapters._is_reparse_point

            def reports_reparse(path: Path) -> bool:
                return path == reparse_target or original_check(path)

            with mock.patch.object(adapters, "_is_reparse_point", side_effect=reports_reparse):
                with self.assertRaisesRegex(ValueError, "symlink or reparse point"):
                    adapters.report_project_adapter(source_root, project)

    def test_project_adapter_uninstall_rejects_registry_path_traversal(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, uninstall_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )
            protected = project / "important.txt"
            protected.write_text("keep me\n", encoding="utf-8")
            registry_path = project / ".agents" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            malicious = {
                "path": ".agents/skills/fake/../../../important.txt",
                "sha256": hashlib.sha256(protected.read_bytes()).hexdigest(),
            }
            registry["kit_adapter"]["files"].append(malicious)
            registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

            uninstall_project_adapter(project)

            self.assertTrue(protected.is_file())
            remaining = json.loads(registry_path.read_text(encoding="utf-8"))["kit_adapter"]["files"]
            self.assertIn(malicious, remaining)

    def test_project_adapter_report_only_lists_changes_without_creating_root(self) -> None:
        from scripts.generate_adapters import report_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "missing-project"

            report = report_project_adapter(source_root, project)

            self.assertEqual("REPORT_ONLY", report["status"])
            self.assertEqual(str(project.resolve()), report["root"])
            self.assertEqual(sorted(report["proposed"]), report["proposed"])
            self.assertIn(".agents/registry.json", report["proposed"])
            self.assertEqual("report-only", report["mutation_report"]["mode"])
            self.assertFalse(project.exists())

    def test_project_adapter_apply_rejects_blank_reviewer_before_mutation(self) -> None:
        from scripts.generate_adapters import apply_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "missing-project"

            with self.assertRaisesRegex(ValueError, "reviewer"):
                apply_project_adapter(
                    source_root,
                    project,
                    reviewer="   ",
                    backup_root=project / ".adapter-backup",
                    approved_plan_digest="unused",
                )

            self.assertFalse(project.exists())

    def test_project_adapter_apply_uses_manifest_and_restore_returns_preapply_state(self) -> None:
        from scripts.generate_adapters import apply_project_adapter
        from scripts.safe_mutation import restore_mutation

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            registry_path = project / ".agents" / "registry.json"
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                json.dumps({"schema_version": 1, "skills": ["local"]}, indent=2) + "\n",
                encoding="utf-8",
            )
            before_registry = registry_path.read_bytes()

            result = apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="QA Lead",
                backup_root=project / ".adapter-backup",
            )

            manifest = Path(result["manifest"])
            self.assertEqual("PASS", result["status"])
            self.assertEqual("QA Lead", result["reviewer"])
            self.assertTrue(manifest.is_file())
            self.assertEqual(str(manifest), result["restore_argv"][-1])
            self.assertEqual("restore", result["restore_argv"][-3])
            self.assertTrue((project / ".agents" / "skills" / "studio-project-intake" / "SKILL.md").is_file())

            restore_mutation(manifest, project)

            self.assertEqual(before_registry, registry_path.read_bytes())
            for relative in result["created"]:
                self.assertFalse((project / relative).exists(), relative)

    def test_project_adapter_never_overwrites_codex_config(self) -> None:
        from scripts.generate_adapters import apply_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            config = project / ".codex" / "config.toml"
            config.parent.mkdir(parents=True)
            config.write_text("model = 'local-choice'\n", encoding="utf-8")

            result = apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="QA Lead",
                backup_root=project / ".adapter-backup",
            )

            self.assertEqual("model = 'local-choice'\n", config.read_text(encoding="utf-8"))
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
            self.assertNotIn(".codex/config.toml", {item["path"] for item in manifest["operations"]})

    def test_project_adapter_cli_defaults_to_report_only(self) -> None:
        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "missing-project"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(source_root / "scripts" / "generate_adapters.py"),
                    str(source_root),
                    "--target",
                    "per-project",
                    "--output",
                    str(project),
                ],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("REPORT_ONLY", json.loads(completed.stdout)["status"])
            self.assertFalse(project.exists())

    def test_project_adapter_cli_apply_requires_reviewer_and_backup_root(self) -> None:
        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            base = [
                sys.executable,
                "-B",
                str(source_root / "scripts" / "generate_adapters.py"),
                str(source_root),
                "--target",
                "per-project",
                "--output",
                str(project),
                "--apply",
            ]
            missing_both = subprocess.run(base, cwd=source_root, check=False, capture_output=True, text=True)
            missing_backup = subprocess.run(
                [*base, "--reviewer", "QA Lead"],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )
            missing_reviewer = subprocess.run(
                [*base, "--backup-root", str(project / ".adapter-backup")],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, missing_both.returncode)
            self.assertIn("--reviewer", missing_both.stderr)
            self.assertNotEqual(0, missing_backup.returncode)
            self.assertIn("--backup-root", missing_backup.stderr)
            self.assertNotEqual(0, missing_reviewer.returncode)
            self.assertIn("--reviewer", missing_reviewer.stderr)
            self.assertFalse(project.exists())

    def test_project_adapter_validation_failure_leaves_project_unchanged(self) -> None:
        from scripts.generate_adapters import apply_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            profile = project / ".agents" / "project-profile.yaml"
            profile.parent.mkdir(parents=True)
            profile.write_text("schema_version: 99\n", encoding="utf-8")
            sentinel = project / "sentinel.txt"
            sentinel.write_text("keep\n", encoding="utf-8")
            before = tree_digest(project)

            with self.assertRaises(ValueError):
                apply_project_adapter(
                    source_root,
                    project,
                    reviewer="QA Lead",
                    backup_root=project / ".adapter-backup",
                    approved_plan_digest="0" * 64,
                )

            self.assertEqual(before, tree_digest(project))
            self.assertFalse((project / ".adapter-backup").exists())

    def test_project_adapter_rejects_target_race_after_digest_validation(self) -> None:
        from scripts import generate_adapters, safe_mutation

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            report = generate_adapters.report_project_adapter(source_root, project)
            registry = project / ".agents" / "registry.json"
            real_apply = safe_mutation.apply_mutation

            def race_before_safe_apply(
                root: Path,
                operations: list[dict[str, str]],
                backup_root: Path,
                **kwargs: object,
            ) -> Path:
                registry.parent.mkdir(parents=True, exist_ok=True)
                registry.write_text("raced-after-validation\n", encoding="utf-8")
                return real_apply(root, operations, backup_root, **kwargs)

            with mock.patch.object(
                generate_adapters,
                "apply_mutation",
                side_effect=race_before_safe_apply,
            ):
                with self.assertRaisesRegex(ValueError, "approved mutation precondition"):
                    generate_adapters.apply_project_adapter(
                        source_root,
                        project,
                        reviewer="QA Lead",
                        backup_root=project / ".adapter-backup",
                        approved_plan_digest=report["plan_digest"],
                    )

            self.assertEqual("raced-after-validation\n", registry.read_text(encoding="utf-8"))
            self.assertFalse((project / ".adapter-backup").exists())
            self.assertFalse((project / ".codex").exists())
            self.assertFalse((project / ".agents" / "skills").exists())

    def test_project_adapter_report_digest_is_stable_and_ignores_unrelated_files(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, report_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            first = report_project_adapter(source_root, project)
            second = report_project_adapter(source_root, project)
            self.assertEqual(first["plan_digest"], second["plan_digest"])

            project.mkdir()
            (project / "notes.txt").write_text("unrelated\n", encoding="utf-8")
            result = apply_project_adapter(
                source_root,
                project,
                reviewer="QA Lead",
                backup_root=project / ".adapter-backup",
                approved_plan_digest=first["plan_digest"],
            )

            self.assertEqual("PASS", result["status"])
            self.assertEqual(first["plan_digest"], result["plan_digest"])
            self.assertEqual("unrelated\n", (project / "notes.txt").read_text(encoding="utf-8"))

    def test_project_adapter_apply_rejects_wrong_digest_without_mutation(self) -> None:
        from scripts.generate_adapters import apply_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "missing-project"

            with self.assertRaisesRegex(ValueError, "plan digest"):
                apply_project_adapter(
                    source_root,
                    project,
                    reviewer="QA Lead",
                    backup_root=project / ".adapter-backup",
                    approved_plan_digest="0" * 64,
                )

            self.assertFalse(project.exists())

    def test_project_adapter_apply_detects_managed_target_change_after_report(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, report_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            registry = project / ".agents" / "registry.json"
            registry.parent.mkdir(parents=True)
            registry.write_text('{"schema_version": 1, "skills": []}\n', encoding="utf-8")
            report = report_project_adapter(source_root, project)
            registry.write_text('{"schema_version": 1, "skills": ["changed"]}\n', encoding="utf-8")
            changed = registry.read_bytes()

            with self.assertRaisesRegex(ValueError, "changed since report"):
                apply_project_adapter(
                    source_root,
                    project,
                    reviewer="QA Lead",
                    backup_root=project / ".adapter-backup",
                    approved_plan_digest=report["plan_digest"],
                )

            self.assertEqual(changed, registry.read_bytes())
            self.assertFalse((project / ".adapter-backup").exists())
            self.assertFalse((project / ".codex").exists())

    def test_project_adapter_apply_detects_source_change_after_report(self) -> None:
        import scripts.generate_adapters as adapters

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "missing-project"
            report = adapters.report_project_adapter(source_root, project)
            original_generated_resource = adapters._generated_resource

            with mock.patch.object(
                adapters,
                "_generated_resource",
                side_effect=lambda source: original_generated_resource(source) + "\n# changed source\n",
            ):
                with self.assertRaisesRegex(ValueError, "changed since report"):
                    adapters.apply_project_adapter(
                        source_root,
                        project,
                        reviewer="QA Lead",
                        backup_root=project / ".adapter-backup",
                        approved_plan_digest=report["plan_digest"],
                    )

            self.assertFalse(project.exists())

    def test_project_adapter_apply_detects_profile_change_after_report(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, report_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            report = report_project_adapter(source_root, project)
            profile = project / ".agents" / "project-profile.yaml"
            profile.parent.mkdir(parents=True)
            profile.write_text(
                "schema_version: 1\nworkspace:\n  name: sample\n  root_git: false\n  default_concurrency: 2\nrepositories:\n  - id: server\n    path: server\n    git_root: true\n    subsystems: [server]\n    owner_skill: studio-project-intake\n    validation: []\nexclusions: []\nagents:\n  specialists:\n    - id: server-specialist\n      repository: server\n      reasoning_effort: high\n      constraints: []\ncross_project_contracts: []\n",
                encoding="utf-8",
            )
            before = tree_digest(project)

            with self.assertRaisesRegex(ValueError, "changed since report"):
                apply_project_adapter(
                    source_root,
                    project,
                    reviewer="QA Lead",
                    backup_root=project / ".adapter-backup",
                    approved_plan_digest=report["plan_digest"],
                )

            self.assertEqual(before, tree_digest(project))
            self.assertFalse((project / ".adapter-backup").exists())

    def test_project_adapter_rejects_overlapping_backup_roots_before_mutation(self) -> None:
        from scripts.generate_adapters import apply_project_adapter, report_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        for relative in (
            ".codex",
            ".agents",
            ".agents/registry.json",
            ".agents/registry.json/backups",
        ):
            with self.subTest(backup_root=relative), temporary_directory() as temp:
                project = Path(temp) / "missing-project"
                report = report_project_adapter(source_root, project)

                with self.assertRaisesRegex(ValueError, "backup root overlaps"):
                    apply_project_adapter(
                        source_root,
                        project,
                        reviewer="QA Lead",
                        backup_root=project / relative,
                        approved_plan_digest=report["plan_digest"],
                    )

                self.assertFalse(project.exists())

    def test_project_adapter_cli_apply_requires_plan_digest_and_uninstall_requires_apply_approval(self) -> None:
        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            script = str(source_root / "scripts" / "generate_adapters.py")
            apply_missing_digest = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    script,
                    str(source_root),
                    "--target",
                    "per-project",
                    "--output",
                    str(project),
                    "--apply",
                    "--reviewer",
                    "QA Lead",
                    "--backup-root",
                    str(project / ".adapter-backup"),
                ],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )
            uninstall_with_review = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    script,
                    str(source_root),
                    "--target",
                    "per-project",
                    "--output",
                    str(project),
                    "--uninstall",
                    "--reviewer",
                    "QA Lead",
                ],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, apply_missing_digest.returncode)
            self.assertIn("--plan-digest", apply_missing_digest.stderr)
            self.assertNotEqual(0, uninstall_with_review.returncode)
            self.assertIn("require --apply", uninstall_with_review.stderr)
            self.assertFalse(project.exists())

    def test_project_adapter_cli_uninstall_requires_explicit_apply_approval(self) -> None:
        source_root = Path(__file__).resolve().parents[2]
        from scripts.generate_adapters import _uninstall_plan_digest

        with temporary_directory() as temp:
            project = Path(temp) / "project"
            apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="QA Lead",
                backup_root=project / ".adapter-backup",
            )
            generated = project / ".agents" / "skills" / "studio-project-intake" / "SKILL.md"
            self.assertTrue(generated.is_file())
            script = str(source_root / "scripts" / "generate_adapters.py")
            report = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    script,
                    str(source_root),
                    "--target",
                    "per-project",
                    "--output",
                    str(project),
                    "--uninstall",
                ],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, report.returncode, report.stdout + report.stderr)
            report_payload = json.loads(report.stdout)
            self.assertEqual("REPORT_ONLY", report_payload["status"])
            self.assertEqual(_uninstall_plan_digest(project), report_payload["plan_digest"])
            self.assertTrue(generated.is_file())

            rejected = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    script,
                    str(source_root),
                    "--target",
                    "per-project",
                    "--output",
                    str(project),
                    "--uninstall",
                    "--reviewer",
                    "QA Lead",
                ],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("require --apply", rejected.stderr)
            self.assertTrue(generated.is_file())

            approved = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    script,
                    str(source_root),
                    "--target",
                    "per-project",
                    "--output",
                    str(project),
                    "--uninstall",
                    "--apply",
                    "--reviewer",
                    "QA Lead",
                    "--backup-root",
                    str(project.parent / "uninstall-backup"),
                    "--plan-digest",
                    _uninstall_plan_digest(project),
                ],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, approved.returncode, approved.stdout + approved.stderr)
            self.assertFalse(generated.exists())

    def test_project_adapter_preserves_unmanaged_specialist_collision(self) -> None:
        import tomllib
        import yaml

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            project = Path(temp) / "project"
            profile_path = project / ".agents" / "project-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 1,
                        "workspace": {
                            "name": "sample-game",
                            "root_git": False,
                            "default_concurrency": 2,
                        },
                        "repositories": [{
                            "id": "server",
                            "path": "server",
                            "git_root": True,
                            "subsystems": ["server"],
                            "owner_skill": "studio-project-intake",
                            "validation": [],
                        }],
                        "exclusions": [],
                        "agents": {"specialists": [{
                            "id": "server-specialist",
                            "repository": "server",
                            "reasoning_effort": "high",
                            "constraints": [],
                        }]},
                        "cross_project_contracts": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            specialist = project / ".codex" / "agents" / "server-specialist.toml"
            specialist.parent.mkdir(parents=True)
            unmanaged = (
                b"name = 'local-specialist'\r\n"
                b"description = 'local owner'\r\n"
                b"# invalid utf-8 follows: \xff\r\n"
            )
            specialist.write_bytes(unmanaged)

            report = apply_reviewed_project_adapter(
                source_root,
                project,
                reviewer="Packaging QA",
                backup_root=project / ".adapter-backup",
            )

            self.assertEqual(unmanaged, specialist.read_bytes())
            relative = ".codex/agents/server-specialist.toml"
            self.assertIn(relative, report["preserved"])
            self.assertIn(
                {
                    "path": relative,
                    "kind": "unmanaged-agent",
                    "role_id": "server-specialist",
                },
                report["collisions"],
            )
            activation = tomllib.loads(
                (project / ".codex" / "agents.generated.toml").read_text(encoding="utf-8")
            )
            self.assertNotIn("server-specialist", activation["agents"])

    def test_adapter_reports_and_trees_are_deterministic(self) -> None:
        from scripts.generate_adapters import generate_adapter, report_project_adapter

        source_root = Path(__file__).resolve().parents[2]
        with temporary_directory() as temp:
            temp_root = Path(temp)
            for target in ("hermes", "codex"):
                output = temp_root / target
                first_report = generate_adapter(source_root, target, output)
                first_report_json = json.dumps(first_report, sort_keys=True, separators=(",", ":"))
                first_digest = tree_digest(output)
                second_report = generate_adapter(source_root, target, output)
                second_report_json = json.dumps(second_report, sort_keys=True, separators=(",", ":"))
                self.assertEqual(first_report_json, second_report_json, target)
                self.assertEqual(first_digest, tree_digest(output), target)

            project = temp_root / "project"
            before_project_digest = tree_digest(project)
            first_project = report_project_adapter(source_root, project)
            second_project = report_project_adapter(source_root, project)
            self.assertEqual(before_project_digest, tree_digest(project))
            self.assertFalse(project.exists())
            self.assertEqual(
                json.dumps(first_project, sort_keys=True, separators=(",", ":")),
                json.dumps(second_project, sort_keys=True, separators=(",", ":")),
            )

    def test_standard_adapters_are_generated_on_demand_and_ignored(self) -> None:
        from scripts.generate_adapters import generate_adapter

        source_root = Path(__file__).resolve().parents[2]
        ignore_entries = {
            line.strip()
            for line in (source_root / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn("adapters/", ignore_entries)
        source_file_count = len(
            [
                path
                for path in (source_root / "skills").rglob("*")
                if path.is_file()
                and path.suffix.casefold() != ".pyc"
                and "__pycache__" not in path.parts
            ]
        )
        with temporary_directory() as temp:
            for target in ("hermes", "codex"):
                adapter = Path(temp) / target
                generate_adapter(source_root, target, adapter)
                files = [path for path in adapter.rglob("*") if path.is_file()]
                self.assertEqual(source_file_count + 1, len(files), target)
                registry = json.loads((adapter / "registry.json").read_text(encoding="utf-8"))
                self.assertEqual(50, len(registry["skills"]), target)
                first_digest = tree_digest(adapter)
                generate_adapter(source_root, target, adapter)
                self.assertEqual(first_digest, tree_digest(adapter), target)


if __name__ == "__main__":
    unittest.main()
