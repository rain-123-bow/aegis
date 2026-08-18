from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROJECT_ROOT / "skills"
GLOBAL_SKILL_PATH = SKILLS_ROOT / "aegis_global_quality_law" / "SKILL.md"
ROLE_SKILL_PATHS = {
    "TEST_PLAN_AUTHOR": SKILLS_ROOT / "aegis_test_plan_author" / "SKILL.md",
    "TEST_PLAN_REVIEWER": SKILLS_ROOT / "aegis_test_plan_reviewer" / "SKILL.md",
    "TEST_EXECUTOR": SKILLS_ROOT / "aegis_test_executor" / "SKILL.md",
    "TEST_RESULT_REVIEWER": SKILLS_ROOT / "aegis_test_result_reviewer" / "SKILL.md",
    "TEST_REPORT_WRITER": SKILLS_ROOT / "aegis_test_report_writer" / "SKILL.md",
    "FINAL_REVIEWER": SKILLS_ROOT / "aegis_final_reviewer" / "SKILL.md",
}
ROLE_TITLES = {
    "TEST_PLAN_AUTHOR": "Aegis Test Plan Author",
    "TEST_PLAN_REVIEWER": "Aegis Test Plan Reviewer",
    "TEST_EXECUTOR": "Aegis Test Executor",
    "TEST_RESULT_REVIEWER": "Aegis Test Result Reviewer",
    "TEST_REPORT_WRITER": "Aegis Test Report Writer",
    "FINAL_REVIEWER": "Aegis Final Reviewer",
}


class SkillBindingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedSkill:
    name: str
    version: str
    sha256: str
    path: Path
    content: str

    def binding(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class RoleSkillBundle:
    role_key: str
    title: str
    global_skill: LoadedSkill
    role_skill: LoadedSkill

    @property
    def bindings(self) -> list[dict[str, object]]:
        return [self.global_skill.binding(), self.role_skill.binding()]

    def compose(self, coordinator_boundary: str) -> str:
        return "\n\n".join(
            [
                f"# {self.title}\n\n{coordinator_boundary.strip()}",
                self.global_skill.content.strip(),
                self.role_skill.content.strip(),
            ]
        )


def load_role_skill_bundle(
    role_key: str,
    agent_config: Mapping[str, object] | None = None,
) -> RoleSkillBundle:
    if role_key not in ROLE_SKILL_PATHS:
        raise SkillBindingError(f"unsupported Aegis role: {role_key}")
    configured_path = (agent_config or {}).get("role_skill_path")
    if configured_path is None:
        role_path = ROLE_SKILL_PATHS[role_key]
    elif isinstance(configured_path, str) and configured_path:
        role_path = (PROJECT_ROOT / configured_path).resolve()
    else:
        raise SkillBindingError("role_skill_path must be a non-empty string")
    return RoleSkillBundle(
        role_key=role_key,
        title=ROLE_TITLES[role_key],
        global_skill=_load_skill(GLOBAL_SKILL_PATH),
        role_skill=_load_skill(role_path),
    )


def all_role_skill_bindings(
    configs: Mapping[str, Mapping[str, object]],
) -> dict[str, list[dict[str, object]]]:
    return {
        role_key: load_role_skill_bundle(role_key, config).bindings
        for role_key, config in configs.items()
    }


def _load_skill(path: Path) -> LoadedSkill:
    resolved = path.resolve()
    try:
        resolved.relative_to(SKILLS_ROOT.resolve())
    except ValueError as error:
        raise SkillBindingError(f"skill path escapes project skills root: {resolved}") from error
    try:
        content = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SkillBindingError(f"cannot read skill: {resolved}: {error}") from error
    metadata = _frontmatter(content, resolved)
    name = metadata.get("name")
    version = metadata.get("version", "1")
    if not name:
        raise SkillBindingError(f"skill has no name: {resolved}")
    if not version:
        raise SkillBindingError(f"skill has no version: {resolved}")
    return LoadedSkill(
        name=name,
        version=version,
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        path=resolved,
        content=content,
    )


def _frontmatter(content: str, path: Path) -> dict[str, str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillBindingError(f"skill has no frontmatter: {path}")
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return metadata
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()
    raise SkillBindingError(f"skill frontmatter is not closed: {path}")
