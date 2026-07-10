"""Session-resource loading and signature helpers."""

from __future__ import annotations

from tau_coding.context import discover_project_context_with_diagnostics
from tau_coding.prompt_templates import PromptTemplate, load_prompt_templates_with_diagnostics
from tau_coding.reload import ReloadCategorySummary
from tau_coding.resources import ResourceDiagnostic, TauResourcePaths
from tau_coding.session_models import SessionResources
from tau_coding.skills import Skill, load_skills_with_diagnostics
from tau_coding.system_prompt import ProjectContextFile


def _category_summary(
    before: tuple[tuple[object, ...], ...],
    after: tuple[tuple[object, ...], ...],
) -> ReloadCategorySummary:
    return ReloadCategorySummary(
        before=len(before),
        after=len(after),
        changed=before != after,
    )


def _skill_signatures(skills: tuple[Skill, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (skill.name, str(skill.path), skill.description, skill.content) for skill in skills
    )


def _prompt_template_signatures(
    prompt_templates: tuple[PromptTemplate, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (template.name, str(template.path), template.description, template.content)
        for template in prompt_templates
    )


def _context_file_signatures(
    context_files: tuple[ProjectContextFile, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple((context_file.path, context_file.content) for context_file in context_files)


def _diagnostic_signatures(
    diagnostics: tuple[ResourceDiagnostic, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            diagnostic.kind,
            diagnostic.message,
            str(diagnostic.path) if diagnostic.path is not None else None,
            diagnostic.name,
            diagnostic.severity,
        )
        for diagnostic in diagnostics
    )


def _system_prompt_resource_signatures(
    *,
    skills: tuple[Skill, ...],
    context_files: tuple[ProjectContextFile, ...],
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    prompt_skills = tuple(
        (skill.name, str(skill.path), skill.description)
        for skill in sorted(skills, key=lambda item: item.name)
    )
    return (prompt_skills, _context_file_signatures(context_files))


def _load_session_resources(
    resource_paths: TauResourcePaths,
    explicit_context_files: tuple[ProjectContextFile, ...],
) -> SessionResources:
    loaded_skills, skill_diagnostics = load_skills_with_diagnostics(resource_paths)
    loaded_prompt_templates, prompt_diagnostics = load_prompt_templates_with_diagnostics(
        resource_paths
    )
    discovered_context, context_diagnostics = discover_project_context_with_diagnostics(
        resource_paths
    )
    return SessionResources(
        skills=tuple(loaded_skills),
        prompt_templates=tuple(loaded_prompt_templates),
        context_files=_merge_context_files(explicit_context_files, discovered_context),
        diagnostics=tuple([*skill_diagnostics, *prompt_diagnostics, *context_diagnostics]),
    )


def _merge_context_files(
    explicit: tuple[ProjectContextFile, ...],
    discovered: tuple[ProjectContextFile, ...],
) -> tuple[ProjectContextFile, ...]:
    merged: list[ProjectContextFile] = []
    seen: set[str] = set()
    for context_file in (*explicit, *discovered):
        if context_file.path in seen:
            continue
        seen.add(context_file.path)
        merged.append(context_file)
    return tuple(merged)
