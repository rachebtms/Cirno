"""Apply bounded, grounded learning from the same call that makes a checkpoint.

No model calls, tool execution, background tasks or prompt-prefix mutations live
here. Evidence and receipts survive failures; document edits share foreground
file transactions and retain Skill history.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cirno_memory.repository import MemoryRepository
from cirno_memory.scopes import scope_identity
from cirno_core.memory.consolidation_contract import LearningPlan
from cirno_core.memory.consolidation_evidence import LearningEvidenceError, resolve_message, source_refs
from cirno_core.memory.consolidation_receipts import index_receipt, receipt_path, write_receipt
from cirno_core.session.roles import conversation_role
from cirno_core.session.history_visibility import is_hidden_history_message
from cirno_core.skills.history import snapshot_skill
from cirno_core.skills.metadata import parse_skill_metadata, valid_skill_metadata
from cirno_core.skills.validation import validate_skill
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_core.utils.file_transactions import file_write_transaction


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class ConsolidationLearning:
    def __init__(
        self,
        home: Path,
        messages: list[dict[str, Any]],
        *,
        session_key: str,
        project_id: str | None,
        context_chars: int,
        max_updates: int,
    ):
        self.home, self.messages = home.resolve(), messages
        self.session_key, self.project_id = session_key, project_id
        self.max_updates = max_updates
        self.repo = MemoryRepository(self.home)
        self.documents: dict[str, str] = {}
        self.known: dict[str, dict[str, Any]] = {}
        self.context_chars = context_chars
        self.inputs: dict[str, dict[str, Any]] = {}
        self.completed = False

    def context(self) -> str:
        """Bound only additional reference material, never truncate task evidence."""
        remaining = self.context_chars
        sections = []
        # Only a personal Router may update shared identity/user profiles.
        paths = []
        if not self.project_id and conversation_role(self.session_key).name == "router":
            paths += [
                self.home / name for name in ("SOUL.md", "WORKER.md", "USER.md", "memory/MEMORY.md")
            ]
        # Match references without concatenating a long transcript or copying image data URLs.
        texts = []
        for message in self.messages:
            content = message.get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                texts.extend(
                    block["text"]
                    for block in content
                    if isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                )
        skills = self.home / "skills"
        if skills.exists():
            paths += [
                p
                for p in sorted(skills.glob("*/SKILL.md"))
                if any(p.parent.name in text for text in texts)
            ]
        for path in paths:
            if path.is_symlink() or not path.resolve().is_relative_to(self.home):
                continue
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            relative = path.relative_to(self.home).as_posix()
            block = json.dumps({"path": relative, "content": text}, ensure_ascii=False)
            if len(block) > remaining:
                continue  # Never offer a partially read file for replacement.
            self.documents[relative] = text
            sections.append(block)
            remaining -= len(block)
        pending = self.repo.consolidation_inputs(
            self.session_key,
            self.project_id,
            limit=self.max_updates,
            max_chars=max(0, remaining // 2),
            include_user=not self.project_id
            and conversation_role(self.session_key).name == "router",
        )
        for record in pending:
            block = json.dumps(
                {
                    "memory_id": record["id"],
                    "revision": record["revision"],
                    "pending": True,
                    "content": record["content"],
                },
                ensure_ascii=False,
            )
            if len(block) <= remaining:
                self.inputs[record["id"]] = record
                sections.append(block)
                remaining -= len(block)
        records = self.repo.search(
            session_key=self.session_key, project_id=self.project_id, layer="knowledge", limit=20
        )["memories"]
        for record in records:
            content = self.repo.body_content(record)
            block = json.dumps(
                {
                    "memory_id": record["id"],
                    "kind": record["kind"],
                    "session_key": record.get("session_key"),
                    "content": content,
                },
                ensure_ascii=False,
            )
            if len(block) > remaining:
                continue
            self.known[record["id"]] = record
            sections.append(block)
            remaining -= len(block)
        return "\n".join(sections) or "(no additional reference material)"

    def _evidence(self, refs, *, user_only=False) -> None:
        for ref in refs:
            if ref.memory_id is not None:
                if user_only or ref.memory_id not in self.inputs:
                    raise ValueError("Learning evidence memory is outside the supplied inputs")
                current = self.repo.read(
                    ref.memory_id, session_key=self.session_key, project_id=self.project_id
                )
                if current["revision"] != self.inputs[ref.memory_id]["revision"]:
                    raise ValueError("Learning evidence changed during consolidation")
                if ref.quote not in self.inputs[ref.memory_id]["content"]:
                    raise LearningEvidenceError("Learning evidence quote does not match its memory")
                continue
            message = self.messages[resolve_message(self.messages, ref, user_only=user_only)]
            if user_only and (
                message.get("role") != "user"
                or is_hidden_history_message(message)
                or message.get("runtime_context") is not None
            ):
                raise ValueError("Shared identity/user updates require explicit user evidence")

    def _document(self, edit) -> Path:
        path = self.home / edit.path
        if path.is_symlink() or not path.resolve().is_relative_to(self.home):
            raise ValueError("Learning document escapes Home")
        relative = path.relative_to(self.home).as_posix()
        is_skill = (
            len(Path(relative).parts) == 3
            and Path(relative).parts[0] == "skills"
            and path.name == "SKILL.md"
        )
        if not is_skill and relative not in self.documents:
            raise ValueError("Shared document was not writable in this consolidation scope")
        self._evidence(edit.evidence, user_only=not is_skill)
        if is_skill:
            metadata = parse_skill_metadata(edit.content)
            if not metadata or not valid_skill_metadata(metadata, path.parent.name):
                raise ValueError("Learning Skill needs valid matching YAML metadata")
            if relative not in self.documents:
                if path.exists() and path.read_text(encoding="utf-8") != edit.content:
                    raise ValueError("Learning cannot replace a Skill it has not read")
                independent = [
                    self.known[i]
                    for i in edit.related_memory_ids
                    if i in self.known
                    and self.known[i].get("session_key")
                    and self.known[i]["session_key"] != self.session_key
                    and self.known[i]["kind"] == "lesson"
                ]
                if not independent:
                    raise ValueError(
                        "New autonomous Skill needs a verified lesson from another task"
                    )
                for previous in independent:
                    current = self.repo.read(
                        previous["id"], session_key=self.session_key, project_id=self.project_id
                    )
                    if current["revision"] != previous["revision"] or current["status"] != "active":
                        raise ValueError("Skill recurrence evidence changed during consolidation")
        return path

    def apply(self, plan: LearningPlan, evidence: dict[str, Any], summary: str) -> None:
        """Validate before mutation, then persist auditable, idempotent changes."""
        path = receipt_path(self.repo, evidence["id"])
        with file_write_transaction([path]):
            if path.exists():
                previous = json.loads(path.read_text(encoding="utf-8"))
                if previous["status"] == "completed":
                    if previous["plan"] != plan.model_dump() or previous["summary"] != summary:
                        raise ValueError("Archived consolidation already has a different completed plan")
                    index_receipt(self.repo, previous)
                    self.completed = True
                    return
            record = {
                "source": evidence["id"],
                "session_key": self.session_key,
                "project_id": self.project_id,
                "documents": self.documents,
                "inputs": self.inputs,
                "known": self.known,
                "max_updates": self.max_updates,
                "context_chars": self.context_chars,
                "summary": summary,
                "plan": plan.model_dump(),
                "status": "pending",
            }
            write_receipt(self.repo, record)
            try:
                self._apply(plan, evidence)
            except Exception as exc:
                record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                if isinstance(exc, LearningEvidenceError):
                    record["regenerate_output"] = True
                write_receipt(self.repo, record)
                raise
            record["status"] = "completed"
            write_receipt(self.repo, record)
            self.completed = True

    def _finding_source(self, finding, evidence):
        parents = [self.inputs[ref.memory_id] for ref in finding.evidence if ref.memory_id]
        if any(scope_identity(parent) != scope_identity(evidence) for parent in parents):
            if (
                any(ref.message is not None for ref in finding.evidence)
                or len({scope_identity(p) for p in parents}) != 1
            ):
                raise ValueError("Learning cannot mix private task evidence into shared knowledge")
            return parents[0]
        return evidence

    def _finding_id(self, finding, evidence) -> str:
        return (
            "learn-"
            + digest(
                json.dumps(
                    [
                        scope_identity(self._finding_source(finding, evidence)),
                        finding.kind,
                        finding.content,
                    ],
                    ensure_ascii=False,
                )
            )[:48]
        )

    def _apply(self, plan: LearningPlan, evidence: dict[str, Any]) -> None:
        if plan.size > self.max_updates:
            raise ValueError("Consolidation learning exceeds the configured update budget")
        if any(review.memory_id not in self.inputs for review in plan.reviewed_inputs):
            raise ValueError("Consolidation reviewed an input that was not supplied")
        targets: dict[str, list[str]] = {}
        for finding in plan.memories:
            self._evidence(finding.evidence)
            parent = self._finding_source(finding, evidence)
            if finding.supersedes:
                if finding.supersedes not in self.known:
                    raise ValueError("A correction must reference a supplied visible memory")
                current = self.repo.read(
                    finding.supersedes, session_key=self.session_key, project_id=self.project_id
                )
                if current["revision"] != self.known[finding.supersedes]["revision"]:
                    raise ValueError("Correction target changed during consolidation")
                if scope_identity(current) != scope_identity(parent):
                    raise ValueError("A correction cannot supersede another visibility scope")
        paths = [self._document(edit) for edit in plan.documents]
        if len(set(paths)) != len(paths):
            raise ValueError("Consolidation contains duplicate document edits")
        memory_paths = [
            self.repo.root / "entries" / (self._finding_id(finding, evidence) + ".md")
            for finding in plan.memories
        ]
        with file_write_transaction([*paths, *memory_paths]):
            for path, edit in zip(paths, plan.documents):
                current = path.read_text(encoding="utf-8") if path.exists() else ""
                original = self.documents.get(edit.path, "")
                if current not in (original, edit.content):
                    raise ValueError(f"{edit.path} changed during consolidation; no overwrite")
                if path.name == "SKILL.md" and path.exists():
                    validation = validate_skill(path.parent, document_content=edit.content)
                    if not validation["valid"]:
                        raise ValueError("; ".join(validation["errors"]))
            for finding in plan.memories:
                parent = self._finding_source(finding, evidence)
                identity = self._finding_id(finding, evidence)
                try:
                    saved = self.repo.read(
                        identity, session_key=self.session_key, project_id=self.project_id
                    )
                except KeyError:
                    saved = self.repo.save(
                        finding.content,
                        source="memory:" + parent["id"],
                        session_key=self.session_key,
                        project_id=self.project_id,
                        kind=finding.kind,
                        layer="knowledge",
                        based_on=parent["id"],
                        memory_id=identity,
                        enqueue=False,
                        expected_parent_revision=parent["revision"],
                        source_refs=source_refs(self.messages, finding.evidence),
                    )
                self.repo.link(
                    saved["id"],
                    parent["id"],
                    "derived_from",
                    "Consolidated from original evidence",
                    session_key=self.session_key,
                    project_id=self.project_id,
                )
                for ref in finding.evidence:
                    if ref.memory_id:
                        self.repo.link(
                            saved["id"],
                            ref.memory_id,
                            "derived_from",
                            "Exact input evidence",
                            session_key=self.session_key,
                            project_id=self.project_id,
                            expected_target_revision=self.inputs[ref.memory_id]["revision"],
                        )
                        targets.setdefault(ref.memory_id, []).append(saved["id"])
                if finding.supersedes:
                    self.repo.link(
                        saved["id"],
                        finding.supersedes,
                        "supersedes",
                        "Evidence-backed user correction",
                        session_key=self.session_key,
                        project_id=self.project_id,
                        expected_target_revision=self.known[finding.supersedes]["revision"],
                    )
            for path, edit in zip(paths, plan.documents):
                if path.name == "SKILL.md":
                    snapshot_skill(path.parent, self.home)
                atomic_write_text(path, edit.content)
                if path.name == "SKILL.md":
                    snapshot_skill(path.parent, self.home)
            if any(path.name != "SKILL.md" for path in paths):
                self.repo.sync_profiles()
        self.repo.settle_consolidation(
            "consolidation:" + evidence["id"],
            [
                {**self.inputs[review.memory_id], "review_reason": review.reason}
                for review in plan.reviewed_inputs
            ],
            targets,
            session_key=self.session_key,
            project_id=self.project_id,
        )
