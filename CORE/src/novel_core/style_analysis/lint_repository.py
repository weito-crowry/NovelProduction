from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LintRunRecord:
    id: int
    document_id: int
    text_revision_id: int
    structure_revision_id: int
    profile_id: int
    profile_version_id: int
    scene_id: int | None
    basic_metric_run_id: int | None
    semantic_metric_run_id: int | None
    input_fingerprint: str
    status: str
    warning_json: str
    enabled_rule_count: int
    applicable_rule_count: int
    missing_rule_count: int
    created_at: str
    finished_at: str | None

    @property
    def coverage_ratio(self) -> float:
        if self.applicable_rule_count == 0:
            return 0.0
        return (self.applicable_rule_count - self.missing_rule_count) / (
            self.applicable_rule_count
        )


@dataclass(frozen=True, slots=True)
class FindingRecord:
    id: int
    lint_run_id: int
    rule_id: int
    target_type: str
    target_id: int
    metric_name: str
    observed_value: float
    expected_min: float
    expected_max: float
    preferred_value: float | None
    deviation: float
    severity: str
    sort_score: float
    explanation_code: str
    evidence_json: str
    created_at: str
    review_status: str | None = None
    review_note: str | None = None


class LintRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert_run(self, values: tuple[object, ...]) -> int:
        cursor = self._connection.execute(
            "INSERT INTO style_lint_runs "
            "(document_id, text_revision_id, structure_revision_id, profile_id, "
            "profile_version_id, scene_id, basic_metric_run_id, "
            "semantic_metric_run_id, input_fingerprint, status, warning_json, "
            "enabled_rule_count, applicable_rule_count, missing_rule_count, "
            "finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("lint run insert did not return an id")
        return int(cursor.lastrowid)

    def insert_finding(self, values: tuple[object, ...]) -> int:
        cursor = self._connection.execute(
            "INSERT INTO style_findings "
            "(lint_run_id, rule_id, target_type, target_id, metric_name, "
            "observed_value, expected_min, expected_max, preferred_value, "
            "deviation, severity, sort_score, explanation_code, evidence_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("finding insert did not return an id")
        return int(cursor.lastrowid)

    def finish_run(self, lint_run_id: int, status: str) -> None:
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("LINT_RUN_STATUS_INVALID")
        self._connection.execute(
            "UPDATE style_lint_runs SET status = ?, "
            "finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP) WHERE id = ?",
            (status, lint_run_id),
        )

    def add_review(self, finding_id: int, status: str, note: str | None) -> int:
        cursor = self._connection.execute(
            "INSERT INTO style_finding_reviews (finding_id, status, note) "
            "VALUES (?, ?, ?)",
            (finding_id, status, note),
        )
        if cursor.lastrowid is None:
            raise sqlite3.IntegrityError("finding review insert did not return an id")
        return int(cursor.lastrowid)

    def get_run(self, lint_run_id: int) -> LintRunRecord | None:
        row = self._connection.execute(
            "SELECT id, document_id, text_revision_id, structure_revision_id, "
            "profile_id, profile_version_id, scene_id, basic_metric_run_id, "
            "semantic_metric_run_id, input_fingerprint, status, warning_json, "
            "enabled_rule_count, applicable_rule_count, missing_rule_count, "
            "created_at, finished_at FROM style_lint_runs WHERE id = ?",
            (lint_run_id,),
        ).fetchone()
        return None if row is None else LintRunRecord(*row)

    def list_runs(self, document_id: int | None = None) -> tuple[LintRunRecord, ...]:
        if document_id is None:
            rows = self._connection.execute(
                "SELECT id FROM style_lint_runs ORDER BY created_at DESC, id DESC"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT id FROM style_lint_runs WHERE document_id = ? "
                "ORDER BY created_at DESC, id DESC",
                (document_id,),
            ).fetchall()
        return tuple(
            run for row in rows if (run := self.get_run(int(row[0]))) is not None
        )

    def get_finding(self, finding_id: int) -> FindingRecord | None:
        row = self._connection.execute(
            "SELECT id, lint_run_id, rule_id, target_type, target_id, metric_name, "
            "observed_value, expected_min, expected_max, preferred_value, "
            "deviation, severity, sort_score, explanation_code, evidence_json, "
            "created_at FROM style_findings WHERE id = ?",
            (finding_id,),
        ).fetchone()
        if row is None:
            return None
        review = self._connection.execute(
            "SELECT status, note FROM style_finding_reviews "
            "WHERE finding_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (finding_id,),
        ).fetchone()
        if review is None:
            review = self._inherited_review(
                lint_run_id=int(row[1]),
                rule_id=int(row[2]),
                target_type=str(row[3]),
                target_id=int(row[4]),
                evidence_json=str(row[14]),
            )
        return FindingRecord(
            id=int(row[0]),
            lint_run_id=int(row[1]),
            rule_id=int(row[2]),
            target_type=str(row[3]),
            target_id=int(row[4]),
            metric_name=str(row[5]),
            observed_value=float(row[6]),
            expected_min=float(row[7]),
            expected_max=float(row[8]),
            preferred_value=None if row[9] is None else float(row[9]),
            deviation=float(row[10]),
            severity=str(row[11]),
            sort_score=float(row[12]),
            explanation_code=str(row[13]),
            evidence_json=str(row[14]),
            created_at=str(row[15]),
            review_status=None if review is None else str(review[0]),
            review_note=None if review is None else review[1],
        )

    def _inherited_review(
        self,
        *,
        lint_run_id: int,
        rule_id: int,
        target_type: str,
        target_id: int,
        evidence_json: str,
    ) -> tuple[str, object] | None:
        run = self._connection.execute(
            "SELECT document_id, text_revision_id, structure_revision_id, "
            "profile_version_id FROM style_lint_runs WHERE id = ?",
            (lint_run_id,),
        ).fetchone()
        if run is None:
            return None
        current_evidence = _canonical_json(evidence_json)
        if current_evidence is None:
            return None
        rows = self._connection.execute(
            "SELECT f.id, f.evidence_json "
            "FROM style_findings AS f "
            "JOIN style_lint_runs AS previous_run "
            "ON previous_run.id = f.lint_run_id "
            "WHERE f.lint_run_id <> ? AND previous_run.document_id = ? "
            "AND previous_run.text_revision_id = ? "
            "AND previous_run.structure_revision_id = ? "
            "AND previous_run.profile_version_id = ? AND f.rule_id = ? "
            "AND f.target_type = ? AND f.target_id = ? "
            "ORDER BY previous_run.created_at DESC, previous_run.id DESC, "
            "f.created_at DESC, f.id DESC",
            (
                lint_run_id,
                int(run[0]),
                int(run[1]),
                int(run[2]),
                int(run[3]),
                rule_id,
                target_type,
                target_id,
            ),
        ).fetchall()
        for previous_finding_id, previous_evidence in rows:
            if _canonical_json(str(previous_evidence)) == current_evidence:
                review = self._connection.execute(
                    "SELECT status, note FROM style_finding_reviews "
                    "WHERE finding_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (int(previous_finding_id),),
                ).fetchone()
                return None if review is None else (str(review[0]), review[1])
        return None

    def list_findings(self, lint_run_id: int) -> tuple[FindingRecord, ...]:
        rows = self._connection.execute(
            "SELECT f.id FROM style_findings AS f "
            "LEFT JOIN style_scenes AS s ON s.id = f.target_id "
            "WHERE f.lint_run_id = ? "
            "ORDER BY CASE f.severity WHEN 'strong_warning' THEN 0 "
            "WHEN 'warning' THEN 1 ELSE 2 END, f.sort_score DESC, "
            "CASE WHEN f.target_type = 'scene' THEN "
            "COALESCE(s.order_index, f.target_id) "
            "ELSE f.target_id END, f.id",
            (lint_run_id,),
        ).fetchall()
        return tuple(
            finding
            for row in rows
            if (finding := self.get_finding(int(row[0]))) is not None
        )


def json_text(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_json(value: str) -> str | None:
    try:
        return json_text(json.loads(value))
    except (TypeError, json.JSONDecodeError, ValueError):
        return None
