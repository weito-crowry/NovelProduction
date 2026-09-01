from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, cast

from novel_core.errors import ValidationError
from novel_core.style_analysis.aggregate_service import AggregateService
from novel_core.style_analysis.corpus_models import (
    AggregateRecord,
    ProfileRecord,
    ProfileVersionRecord,
    StyleRuleRecord,
)
from novel_core.style_analysis.metrics import BASIC_METRIC_DEFINITIONS
from novel_core.style_analysis.profile_calculations import (
    _canonical_json,
    _finite_number,
    _positive_int,
    _rule_selector,
    _validate_selector,
    _with_staleness,
)


@dataclass(frozen=True, slots=True)
class ProfileGenerationPolicy:
    version: int = 1
    min_document_measurements: int = 5
    min_scene_measurements: int = 10
    min_term_sample_count: int = 5


@dataclass(frozen=True, slots=True)
class ProfileBuildResult:
    profile: ProfileRecord
    version: ProfileVersionRecord
    rules: tuple[StyleRuleRecord, ...]
    warnings: tuple[str, ...]


class ProfileService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        generation_policy: ProfileGenerationPolicy | None = None,
    ) -> None:
        self._connection = connection
        self.policy = generation_policy or ProfileGenerationPolicy()
        self.aggregates = AggregateService(connection)

    def create_manual(
        self,
        *,
        name: str,
        description: str = "",
        rules: Sequence[Mapping[str, object]],
    ) -> ProfileBuildResult:
        validated = self._validate_rules(rules, source_kind="manual")
        with self._write_transaction():
            result = self._insert_profile(
                name=name,
                description=description,
                source_corpus_id=None,
                version_no=1,
                parent_version_id=None,
                policy_version=None,
                rules=validated,
                sources=(),
            )
            return result

    def create_from_corpus(
        self,
        *,
        corpus_id: int,
        name: str,
        description: str = "",
        aggregate_groups: Sequence[Mapping[str, object]],
    ) -> ProfileBuildResult:
        if self.aggregates.corpora.get(corpus_id) is None:
            raise ValidationError("CORPUS_NOT_FOUND")
        warnings: list[str] = []
        generated: list[dict[str, object]] = []
        sources: list[tuple[int, int, str]] = []
        for index, group in enumerate(aggregate_groups):
            try:
                preferred_id = _positive_int(group.get("preferred_aggregate_id"))
                min_id = _positive_int(group.get("min_aggregate_id"))
                max_id = _positive_int(group.get("max_aggregate_id"))
                preferred = self._require_aggregate(preferred_id)
                minimum = self._require_aggregate(min_id)
                maximum = self._require_aggregate(max_id)
                self._validate_aggregate_group(corpus_id, preferred, minimum, maximum)
                measurement_count = preferred.source_measurement_count
                minimum_count = (
                    self.policy.min_scene_measurements
                    if preferred.measurement_target_type == "scene"
                    else self.policy.min_document_measurements
                )
                if measurement_count < minimum_count:
                    warnings.append(
                        f"PROFILE_RULE_SKIPPED:{index}:INSUFFICIENT_MEASUREMENTS"
                    )
                    continue
                if (
                    preferred.metric_name.startswith("term.")
                    and preferred.sample_count < self.policy.min_term_sample_count
                ):
                    warnings.append(
                        f"PROFILE_RULE_SKIPPED:{index}:INSUFFICIENT_TERM_SAMPLES"
                    )
                    continue
                selector = _rule_selector(preferred)
                target_scope = (
                    "scene"
                    if preferred.measurement_target_type == "scene"
                    else "document"
                )
                generated.append(
                    {
                        "target_scope": target_scope,
                        "scope_selector": selector,
                        "metric_name": preferred.metric_name,
                        "metric_version": preferred.metric_version,
                        "preferred_value": preferred.value_real,
                        "min_value": minimum.value_real,
                        "max_value": maximum.value_real,
                        "weight": 1.0,
                        "enabled": True,
                        "severity_policy": "standard",
                    }
                )
                rule_index = len(generated) - 1
                sources.extend(
                    (
                        (rule_index, preferred.id, "preferred"),
                        (rule_index, min_id, "min"),
                        (rule_index, max_id, "max"),
                    )
                )
                if any(item.stale for item in (preferred, minimum, maximum)):
                    warnings.append(f"PROFILE_STALE_AGGREGATE:{index}")
            except ValidationError:
                raise
        validated = self._validate_rules(generated, source_kind="corpus")
        with self._write_transaction():
            result = self._insert_profile(
                name=name,
                description=description,
                source_corpus_id=corpus_id,
                version_no=1,
                parent_version_id=None,
                policy_version=self.policy.version,
                rules=validated,
                sources=tuple(sources),
            )
            return ProfileBuildResult(
                result.profile,
                result.version,
                result.rules,
                tuple(sorted(set(warnings))),
            )

    def create_version(
        self,
        profile_id: int,
        *,
        parent_version_no: int,
        rules: Sequence[Mapping[str, object]],
    ) -> ProfileBuildResult:
        profile = self.get_profile(profile_id)
        if profile is None:
            raise ValidationError("PROFILE_NOT_FOUND")
        parent = self.get_version(profile_id, parent_version_no)
        if parent is None:
            raise ValidationError("PROFILE_PARENT_VERSION_NOT_FOUND")
        validated = self._validate_rules(rules, source_kind="manual")
        max_row = self._connection.execute(
            "SELECT COALESCE(MAX(version_no), 0) FROM style_profile_versions "
            "WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        version_no = int(max_row[0]) + 1
        with self._write_transaction():
            result = self._insert_version(
                profile=profile,
                version_no=version_no,
                parent_version_id=parent.id,
                policy_version=None,
                rules=validated,
                sources=(),
            )
            return result

    @contextmanager
    def _write_transaction(self) -> Iterator[None]:
        savepoint = "profile_write"
        owns_transaction = not self._connection.in_transaction
        if owns_transaction:
            self._connection.execute("BEGIN IMMEDIATE")
        else:
            self._connection.execute(f"SAVEPOINT {savepoint}")
        try:
            yield
            if owns_transaction:
                self._connection.commit()
            else:
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            if owns_transaction:
                self._connection.rollback()
            else:
                self._connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self._connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise

    def list_profiles(self) -> tuple[ProfileRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, name, description, source_corpus_id, status, "
            "active_version_id, created_at, updated_at FROM style_profiles ORDER BY id"
        ).fetchall()
        return tuple(ProfileRecord(*row) for row in rows)

    def get_profile(self, profile_id: int) -> ProfileRecord | None:
        row = self._connection.execute(
            "SELECT id, name, description, source_corpus_id, status, "
            "active_version_id, created_at, updated_at "
            "FROM style_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        return None if row is None else ProfileRecord(*row)

    def update_profile(
        self,
        profile_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> ProfileRecord:
        if self.get_profile(profile_id) is None:
            raise ValidationError("PROFILE_NOT_FOUND")
        if name is not None and not name:
            raise ValidationError("PROFILE_NAME_REQUIRED")
        self._connection.execute(
            "UPDATE style_profiles SET name = COALESCE(?, name), "
            "description = COALESCE(?, description), updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (name, description, profile_id),
        )
        result = self.get_profile(profile_id)
        assert result is not None
        return result

    def list_versions(self, profile_id: int) -> tuple[ProfileVersionRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, profile_id, version_no, parent_version_id, "
            "profile_generation_policy_version, created_at "
            "FROM style_profile_versions WHERE profile_id = ? ORDER BY version_no",
            (profile_id,),
        ).fetchall()
        return tuple(ProfileVersionRecord(*row) for row in rows)

    def get_version(
        self, profile_id: int, version_no: int
    ) -> ProfileVersionRecord | None:
        row = self._connection.execute(
            "SELECT id, profile_id, version_no, parent_version_id, "
            "profile_generation_policy_version, created_at "
            "FROM style_profile_versions WHERE profile_id = ? AND version_no = ?",
            (profile_id, version_no),
        ).fetchone()
        return None if row is None else ProfileVersionRecord(*row)

    def list_rules(self, profile_version_id: int) -> tuple[StyleRuleRecord, ...]:
        rows = self._connection.execute(
            "SELECT id, profile_version_id, target_scope, scope_selector_json, "
            "metric_name, metric_version, preferred_value, min_value, max_value, "
            "weight, enabled, severity_policy, source_kind, created_at "
            "FROM style_rules WHERE profile_version_id = ? ORDER BY id",
            (profile_version_id,),
        ).fetchall()
        return tuple(
            StyleRuleRecord(
                id=cast(int, row[0]),
                profile_version_id=cast(int, row[1]),
                target_scope=cast(Any, row[2]),
                scope_selector_json=cast(str, row[3]),
                metric_name=cast(str, row[4]),
                metric_version=cast(int, row[5]),
                preferred_value=cast(float | None, row[6]),
                min_value=cast(float | None, row[7]),
                max_value=cast(float | None, row[8]),
                weight=float(row[9]),
                enabled=bool(row[10]),
                severity_policy=cast(Any, row[11]),
                source_kind=cast(Any, row[12]),
                created_at=cast(str, row[13]),
            )
            for row in rows
        )

    def aggregate_sources(self, rule_id: int) -> tuple[tuple[int, str], ...]:
        rows = self._connection.execute(
            "SELECT aggregate_id, role FROM style_rule_aggregate_sources "
            "WHERE rule_id = ? ORDER BY role",
            (rule_id,),
        ).fetchall()
        return tuple((int(row[0]), str(row[1])) for row in rows)

    def activate(self, profile_id: int, version_no: int) -> ProfileRecord:
        profile = self.get_profile(profile_id)
        version = self.get_version(profile_id, version_no)
        if profile is None:
            raise ValidationError("PROFILE_NOT_FOUND")
        if version is None:
            raise ValidationError("PROFILE_VERSION_NOT_FOUND")
        self._connection.execute(
            "UPDATE style_profiles SET status = 'active', active_version_id = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (version.id, profile_id),
        )
        result = self.get_profile(profile_id)
        assert result is not None
        return result

    def archive(self, profile_id: int) -> ProfileRecord:
        if self.get_profile(profile_id) is None:
            raise ValidationError("PROFILE_NOT_FOUND")
        self._connection.execute(
            "UPDATE style_profiles SET status = 'archived', "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (profile_id,),
        )
        result = self.get_profile(profile_id)
        assert result is not None
        return result

    def _insert_profile(
        self,
        *,
        name: str,
        description: str,
        source_corpus_id: int | None,
        version_no: int,
        parent_version_id: int | None,
        policy_version: int | None,
        rules: Sequence[Mapping[str, object]],
        sources: Sequence[tuple[int, int, str]],
    ) -> ProfileBuildResult:
        if not name:
            raise ValidationError("PROFILE_NAME_REQUIRED")
        cursor = self._connection.execute(
            "INSERT INTO style_profiles (name, description, source_corpus_id, status) "
            "VALUES (?, ?, ?, 'draft')",
            (name, description, source_corpus_id),
        )
        assert cursor.lastrowid is not None
        profile = self.get_profile(int(cursor.lastrowid))
        assert profile is not None
        return self._insert_version(
            profile=profile,
            version_no=version_no,
            parent_version_id=parent_version_id,
            policy_version=policy_version,
            rules=rules,
            sources=sources,
        )

    def _insert_version(
        self,
        *,
        profile: ProfileRecord,
        version_no: int,
        parent_version_id: int | None,
        policy_version: int | None,
        rules: Sequence[Mapping[str, object]],
        sources: Sequence[tuple[int, int, str]],
    ) -> ProfileBuildResult:
        cursor = self._connection.execute(
            "INSERT INTO style_profile_versions "
            "(profile_id, version_no, parent_version_id, "
            "profile_generation_policy_version) "
            "VALUES (?, ?, ?, ?)",
            (profile.id, version_no, parent_version_id, policy_version),
        )
        assert cursor.lastrowid is not None
        version = self.get_version(profile.id, version_no)
        assert version is not None
        rule_records: list[StyleRuleRecord] = []
        source_index = 0
        for rule in rules:
            record = self._insert_rule(version.id, rule)
            rule_records.append(record)
            for source in sources:
                if source[0] == source_index:
                    self._connection.execute(
                        "INSERT INTO style_rule_aggregate_sources "
                        "(rule_id, aggregate_id, role) VALUES (?, ?, ?)",
                        (record.id, source[1], source[2]),
                    )
            source_index += 1
        return ProfileBuildResult(profile, version, tuple(rule_records), ())

    def _insert_rule(
        self, version_id: int, rule: Mapping[str, object]
    ) -> StyleRuleRecord:
        cursor = self._connection.execute(
            "INSERT INTO style_rules "
            "(profile_version_id, target_scope, scope_selector_json, metric_name, "
            "metric_version, preferred_value, min_value, max_value, weight, enabled, "
            "severity_policy, source_kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version_id,
                rule["target_scope"],
                _canonical_json(rule["scope_selector"]),
                rule["metric_name"],
                rule["metric_version"],
                rule.get("preferred_value"),
                rule.get("min_value"),
                rule.get("max_value"),
                rule["weight"],
                int(cast(bool, rule["enabled"])),
                rule["severity_policy"],
                rule["source_kind"],
            ),
        )
        assert cursor.lastrowid is not None
        row = self._connection.execute(
            "SELECT id, profile_version_id, target_scope, scope_selector_json, "
            "metric_name, metric_version, preferred_value, min_value, max_value, "
            "weight, enabled, severity_policy, source_kind, created_at "
            "FROM style_rules WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        assert row is not None
        return StyleRuleRecord(
            id=cast(int, row[0]),
            profile_version_id=cast(int, row[1]),
            target_scope=cast(Any, row[2]),
            scope_selector_json=cast(str, row[3]),
            metric_name=cast(str, row[4]),
            metric_version=cast(int, row[5]),
            preferred_value=cast(float | None, row[6]),
            min_value=cast(float | None, row[7]),
            max_value=cast(float | None, row[8]),
            weight=float(row[9]),
            enabled=bool(row[10]),
            severity_policy=cast(Any, row[11]),
            source_kind=cast(Any, row[12]),
            created_at=cast(str, row[13]),
        )

    def _validate_rules(
        self, rules: Sequence[Mapping[str, object]], *, source_kind: str
    ) -> tuple[dict[str, object], ...]:
        seen: set[tuple[str, str, str, int]] = set()
        validated: list[dict[str, object]] = []
        for raw in rules:
            target_scope = raw.get("target_scope")
            metric_name = raw.get("metric_name")
            metric_version = raw.get("metric_version")
            if target_scope not in {"document", "scene", "character"}:
                raise ValidationError("PROFILE_RULE_SCOPE_INVALID")
            if not isinstance(metric_name, str) or not isinstance(metric_version, int):
                raise ValidationError("PROFILE_RULE_METRIC_INVALID")
            definition = BASIC_METRIC_DEFINITIONS.get(metric_name)
            if definition is None or definition.version != metric_version:
                raise ValidationError("METRIC_NOT_FOUND")
            if target_scope not in definition.scope_types:
                raise ValidationError("PROFILE_RULE_SCOPE_UNSUPPORTED")
            selector = _validate_selector(target_scope, raw.get("scope_selector"))
            key = (target_scope, _canonical_json(selector), metric_name, metric_version)
            enabled = raw.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValidationError("PROFILE_RULE_ENABLED_INVALID")
            preferred = _finite_number(raw.get("preferred_value"), allow_none=True)
            minimum = _finite_number(raw.get("min_value"), allow_none=True)
            maximum = _finite_number(raw.get("max_value"), allow_none=True)
            weight = _finite_number(raw.get("weight", 1.0))
            assert weight is not None
            if not 0.0 <= weight <= 5.0:
                raise ValidationError("PROFILE_RULE_WEIGHT_INVALID")
            if enabled and (minimum is None or maximum is None):
                raise ValidationError("PROFILE_RULE_RANGE_REQUIRED")
            if enabled and minimum is not None and maximum is not None:
                if minimum > maximum:
                    raise ValidationError("PROFILE_RULE_RANGE_INVALID")
                if preferred is not None and not minimum <= preferred <= maximum:
                    raise ValidationError("PROFILE_RULE_PREFERRED_OUT_OF_RANGE")
                if minimum == maximum and definition.zero_width_tolerance <= 0:
                    raise ValidationError("PROFILE_RULE_ZERO_WIDTH_INVALID")
            severity = raw.get("severity_policy", "standard")
            if severity != "standard":
                raise ValidationError("PROFILE_RULE_SEVERITY_INVALID")
            if key in seen and enabled:
                raise ValidationError("PROFILE_RULE_DUPLICATE")
            if enabled:
                seen.add(key)
            validated.append(
                {
                    "target_scope": target_scope,
                    "scope_selector": selector,
                    "metric_name": metric_name,
                    "metric_version": metric_version,
                    "preferred_value": preferred,
                    "min_value": minimum,
                    "max_value": maximum,
                    "weight": weight,
                    "enabled": enabled,
                    "severity_policy": severity,
                    "source_kind": source_kind,
                }
            )
        return tuple(validated)

    def _require_aggregate(self, aggregate_id: int) -> AggregateRecord:
        aggregate = self.aggregates.aggregates.get(aggregate_id)
        if aggregate is None:
            raise ValidationError("AGGREGATE_NOT_FOUND")
        return _with_staleness(self.aggregates.aggregates, aggregate)

    @staticmethod
    def _validate_aggregate_group(
        corpus_id: int,
        preferred: AggregateRecord,
        minimum: AggregateRecord,
        maximum: AggregateRecord,
    ) -> None:
        if preferred.statistic != "median":
            raise ValidationError("PROFILE_PREFERRED_STATISTIC_INVALID")
        if minimum.statistic != "p25" or maximum.statistic != "p75":
            raise ValidationError("PROFILE_RANGE_STATISTIC_INVALID")
        fields = (
            "container_type",
            "container_id",
            "measurement_target_type",
            "filter_json",
            "metric_name",
            "metric_version",
            "aggregate_policy_version",
        )
        if (
            any(
                getattr(preferred, field) != getattr(item, field)
                for item in (minimum, maximum)
                for field in fields
            )
            or preferred.container_type != "corpus"
            or preferred.container_id != corpus_id
        ):
            raise ValidationError("PROFILE_AGGREGATE_MISMATCH")
