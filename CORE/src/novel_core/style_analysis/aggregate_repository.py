from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from typing import cast

from novel_core.style_analysis.corpus_models import (
    AggregateRecord,
    ContainerType,
    MeasurementRecord,
    MeasurementTargetType,
    Statistic,
)


class MeasurementRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(
        self,
        *,
        analysis_run_id: int,
        structure_revision_id: int,
        target_type: str,
        target_id: int,
        metric_name: str,
        metric_version: int,
        value: int | float,
        value_type: str,
        sample_count: int,
    ) -> int:
        value_real: float | None = None
        value_int: int | None = None
        if value_type == "int":
            value_int = int(value)
        else:
            value_real = float(value)
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO style_measurements "
            "(analysis_run_id, structure_revision_id, target_type, target_id, "
            "metric_name, metric_version, value_real, value_int, sample_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                analysis_run_id,
                structure_revision_id,
                target_type,
                target_id,
                metric_name,
                metric_version,
                value_real,
                value_int,
                sample_count,
            ),
        )
        if cursor.rowcount == 1 and cursor.lastrowid is not None:
            return int(cursor.lastrowid)
        row = self._connection.execute(
            "SELECT id FROM style_measurements WHERE analysis_run_id = ? "
            "AND target_type = ? AND target_id = ? AND metric_name = ? "
            "AND metric_version = ?",
            (analysis_run_id, target_type, target_id, metric_name, metric_version),
        ).fetchone()
        if row is None:
            raise sqlite3.IntegrityError("measurement insert did not persist")
        return int(row[0])

    def list_for_run(self, analysis_run_id: int) -> tuple[MeasurementRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, analysis_run_id, structure_revision_id, target_type, "
            "target_id, "
            "metric_name, metric_version, "
            "CASE WHEN value_int IS NULL THEN value_real ELSE value_int END, "
            "sample_count, created_at FROM style_measurements "
            "WHERE analysis_run_id = ? ORDER BY id",
            (analysis_run_id,),
        ).fetchall()
        return tuple(MeasurementRecord(*row) for row in rows)


class AggregateRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert(
        self,
        *,
        container_type: ContainerType,
        container_id: int,
        measurement_target_type: MeasurementTargetType,
        filter_json: str,
        metric_name: str,
        metric_version: int,
        statistic: Statistic,
        aggregate_policy_version: int,
        value_real: float,
        source_measurement_count: int,
        sample_count: int,
        work_count: int,
        skipped_target_count: int,
        filter_state_fingerprint: str | None,
        input_fingerprint: str,
        warning_json: str,
    ) -> AggregateRecord:
        cursor = self._connection.execute(
            "INSERT INTO style_aggregates "
            "(container_type, container_id, measurement_target_type, filter_json, "
            "metric_name, metric_version, statistic, aggregate_policy_version, "
            "value_real, source_measurement_count, sample_count, work_count, "
            "skipped_target_count, filter_state_fingerprint, input_fingerprint, "
            "warning_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                container_type,
                container_id,
                measurement_target_type,
                filter_json,
                metric_name,
                metric_version,
                statistic,
                aggregate_policy_version,
                value_real,
                source_measurement_count,
                sample_count,
                work_count,
                skipped_target_count,
                filter_state_fingerprint,
                input_fingerprint,
                warning_json,
            ),
        )
        assert cursor.lastrowid is not None
        aggregate = self.get(int(cursor.lastrowid))
        assert aggregate is not None
        return aggregate

    def link_measurements(
        self, aggregate_id: int, measurement_ids: Sequence[int]
    ) -> None:
        self._connection.executemany(
            "INSERT INTO style_aggregate_measurements (aggregate_id, measurement_id) "
            "VALUES (?, ?)",
            ((aggregate_id, measurement_id) for measurement_id in measurement_ids),
        )

    def get(self, aggregate_id: int) -> AggregateRecord | None:
        row = self._connection.execute(
            "SELECT id, container_type, container_id, measurement_target_type, "
            "filter_json, metric_name, metric_version, statistic, "
            "aggregate_policy_version, value_real, source_measurement_count, "
            "sample_count, work_count, skipped_target_count, "
            "filter_state_fingerprint, input_fingerprint, warning_json, created_at "
            "FROM style_aggregates WHERE id = ?",
            (aggregate_id,),
        ).fetchone()
        if row is None:
            return None
        return AggregateRecord(
            id=cast(int, row[0]),
            container_type=cast(ContainerType, row[1]),
            container_id=cast(int, row[2]),
            measurement_target_type=cast(MeasurementTargetType, row[3]),
            filter_json=cast(str, row[4]),
            metric_name=cast(str, row[5]),
            metric_version=cast(int, row[6]),
            statistic=cast(Statistic, row[7]),
            aggregate_policy_version=cast(int, row[8]),
            value_real=float(row[9]),
            source_measurement_count=cast(int, row[10]),
            sample_count=cast(int, row[11]),
            work_count=cast(int, row[12]),
            skipped_target_count=cast(int, row[13]),
            filter_state_fingerprint=cast(str | None, row[14]),
            input_fingerprint=cast(str, row[15]),
            warning_json=cast(str, row[16]),
            created_at=cast(str, row[17]),
        )

    def list(
        self,
        *,
        container_type: ContainerType,
        container_id: int,
        measurement_target_type: MeasurementTargetType | None = None,
    ) -> tuple[AggregateRecord, ...]:
        clauses = ["container_type = ?", "container_id = ?"]
        parameters: list[object] = [container_type, container_id]
        if measurement_target_type is not None:
            clauses.append("measurement_target_type = ?")
            parameters.append(measurement_target_type)
        rows = self._connection.execute(
            "SELECT id FROM style_aggregates WHERE "
            + " AND ".join(clauses)
            + " ORDER BY id",
            tuple(parameters),
        ).fetchall()
        return tuple(
            aggregate
            for row in rows
            if (aggregate := self.get(int(row[0]))) is not None
        )

    def measurement_ids(self, aggregate_id: int) -> tuple[int, ...]:
        rows = self._connection.execute(
            "SELECT measurement_id FROM style_aggregate_measurements "
            "WHERE aggregate_id = ? ORDER BY measurement_id",
            (aggregate_id,),
        ).fetchall()
        return tuple(int(row[0]) for row in rows)


def json_object(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
