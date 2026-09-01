from __future__ import annotations

import json
from typing import Any

from novel_core.document import parse_document_json, render_plain_text_projection
from novel_core.errors import DocumentSchemaError, DocumentStorageError, ValidationError
from novel_core.repositories.draft_repository import DraftRepository
from novel_core.style_analysis.lint_repository import FindingRecord, LintRunRecord
from novel_core.style_analysis.lint_service import LintResult, StyleLintService
from novel_core.style_analysis.text_service import StyleTextService


class StyleAnalysisLintMixin:
    _connection: Any
    _lint: StyleLintService
    analysis_status: Any

    def capture_project_draft(
        self, *, episode_id: int, draft_id: int
    ) -> dict[str, object]:
        owns_transaction = not self._connection.in_transaction
        try:
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            episode = self._connection.execute(
                "SELECT work_id FROM episodes WHERE id = ?", (episode_id,)
            ).fetchone()
            if episode is None:
                raise ValidationError("EPISODE_NOT_FOUND")
            draft = DraftRepository(self._connection).get_by_id(draft_id)
            if draft is None:
                raise ValidationError("DRAFT_NOT_FOUND")
            if draft.work_id != int(episode[0]) or draft.episode_id != episode_id:
                raise ValidationError("PROJECT_DRAFT_EPISODE_MISMATCH")
            try:
                document = parse_document_json(draft.document_json)
            except DocumentSchemaError as exc:
                raise DocumentStorageError() from exc
            projection = render_plain_text_projection(document)
            row = self._connection.execute(
                "SELECT id FROM style_documents "
                "WHERE kind = 'project_episode_draft' "
                "AND project_work_id = ? AND project_episode_id = ?",
                (draft.work_id, episode_id),
            ).fetchone()
            if row is None:
                cursor = self._connection.execute(
                    "INSERT INTO style_documents "
                    "(kind, project_work_id, project_episode_id) VALUES "
                    "('project_episode_draft', ?, ?)",
                    (draft.work_id, episode_id),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("project style document insert failed")
                document_id = int(cursor.lastrowid)
            else:
                document_id = int(row[0])
            revision = StyleTextService(self._connection).insert_project_draft_revision(
                document_id=document_id,
                project_draft_id=draft_id,
                raw_text=projection.raw_text,
                structure_hints_raw=list(projection.scene_break_offsets_raw),
            )
            if owns_transaction:
                self._connection.commit()
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            raise
        return self.project_document_summary(document_id, revision.id, draft_id)

    def project_document_summary(
        self,
        document_id: int,
        revision_id: int | None = None,
        draft_id: int | None = None,
    ) -> dict[str, object]:
        row = self._connection.execute(
            "SELECT id, kind, current_text_revision_id, "
            "current_structure_revision_id FROM style_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("STYLE_DOCUMENT_NOT_FOUND")
        structure_kind = None
        if row[3] is not None:
            structure = self._connection.execute(
                "SELECT source_kind FROM style_structure_revisions WHERE id = ?",
                (row[3],),
            ).fetchone()
            structure_kind = None if structure is None else structure[0]
        return {
            "document_id": int(row[0]),
            "kind": row[1],
            "current_text_revision_id": row[2],
            "current_structure_revision_id": row[3],
            "current_structure_kind": structure_kind,
            "captured_text_revision_id": revision_id,
            "draft_id": draft_id,
            "analysis_status": self.analysis_status(row[0], row[2], row[3]),
        }

    def run_style_lint(self, **kwargs: Any) -> LintResult:
        result = self._lint.run(**kwargs)
        self._connection.commit()
        return result

    def list_lint_runs(
        self, document_id: int | None = None
    ) -> tuple[dict[str, object], ...]:
        return tuple(
            self._lint_run_response(run) for run in self._lint.list_runs(document_id)
        )

    def get_lint_run(self, lint_run_id: int) -> dict[str, object] | None:
        run = self._lint.get_run(lint_run_id)
        return None if run is None else self._lint_run_response(run)

    def list_lint_findings(self, lint_run_id: int) -> tuple[dict[str, object], ...]:
        return tuple(
            self._finding_response(item)
            for item in self._lint.list_findings(lint_run_id)
        )

    def review_lint_finding(
        self, finding_id: int, status: str, note: str | None
    ) -> dict[str, object]:
        finding = self._lint.review_finding(finding_id, status, note)
        self._connection.commit()
        return self._finding_response(finding)

    def _lint_run_response(self, run: LintRunRecord) -> dict[str, object]:
        return {
            "id": run.id,
            "document_id": run.document_id,
            "text_revision_id": run.text_revision_id,
            "structure_revision_id": run.structure_revision_id,
            "profile_id": run.profile_id,
            "profile_version_id": run.profile_version_id,
            "scene_id": run.scene_id,
            "basic_metric_run_id": run.basic_metric_run_id,
            "semantic_metric_run_id": run.semantic_metric_run_id,
            "input_fingerprint": run.input_fingerprint,
            "status": run.status,
            "warnings": json.loads(run.warning_json),
            "enabled_rule_count": run.enabled_rule_count,
            "applicable_rule_count": run.applicable_rule_count,
            "missing_rule_count": run.missing_rule_count,
            "coverage_ratio": run.coverage_ratio,
            "stale": self._lint.is_stale(run),
            "created_at": run.created_at,
            "finished_at": run.finished_at,
        }

    @staticmethod
    def _finding_response(finding: FindingRecord) -> dict[str, object]:
        return {
            "id": finding.id,
            "lint_run_id": finding.lint_run_id,
            "rule_id": finding.rule_id,
            "target_type": finding.target_type,
            "target_id": finding.target_id,
            "metric_name": finding.metric_name,
            "observed_value": finding.observed_value,
            "expected_min": finding.expected_min,
            "expected_max": finding.expected_max,
            "preferred_value": finding.preferred_value,
            "deviation": finding.deviation,
            "severity": finding.severity,
            "sort_score": finding.sort_score,
            "explanation_code": finding.explanation_code,
            "evidence": json.loads(finding.evidence_json),
            "review_status": finding.review_status,
            "review_note": finding.review_note,
            "created_at": finding.created_at,
        }
