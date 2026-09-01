from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from novel_core.style_analysis.aggregate_service import (
    AggregateRecomputeResult,
    AggregateService,
)
from novel_core.style_analysis.corpus_models import (
    AggregateRecord,
    AggregateSpec,
    CorpusRecord,
    CorpusWorkMembershipRecord,
    ProfileRecord,
    ProfileVersionRecord,
    StyleRuleRecord,
)
from novel_core.style_analysis.profile_service import ProfileBuildResult, ProfileService

from novel_api.style_analysis.job_service import DatabaseConnection


class StyleAnalysisCorpusProfileMixin:
    _aggregate_service: AggregateService
    _connection: DatabaseConnection
    _profile_service: ProfileService

    def list_corpora(self) -> tuple[CorpusRecord, ...]:
        return self._aggregate_service.corpora.list()

    def get_corpus(self, corpus_id: int) -> CorpusRecord | None:
        return self._aggregate_service.corpora.get(corpus_id)

    def create_corpus(self, name: str, description: str = "") -> CorpusRecord:
        result = self._aggregate_service.corpora.create(name, description)
        self._connection.commit()
        return result

    def update_corpus(
        self, corpus_id: int, *, name: str | None = None, description: str | None = None
    ) -> CorpusRecord:
        result = self._aggregate_service.corpora.update(
            corpus_id, name=name, description=description
        )
        self._connection.commit()
        return result

    def delete_corpus(self, corpus_id: int) -> bool:
        result = self._aggregate_service.corpora.delete(corpus_id)
        self._connection.commit()
        return result

    def add_corpus_work(
        self, corpus_id: int, work_id: int, *, include_all_episodes: bool
    ) -> CorpusWorkMembershipRecord:
        result = self._aggregate_service.corpora.add_work(
            corpus_id, work_id, include_all_episodes=include_all_episodes
        )
        self._connection.commit()
        return result

    def remove_corpus_work(self, corpus_id: int, work_id: int) -> bool:
        result = self._aggregate_service.corpora.remove_work(corpus_id, work_id)
        self._connection.commit()
        return result

    def set_corpus_episode(self, corpus_id: int, episode_id: int, mode: str) -> object:
        result = self._aggregate_service.corpora.set_episode(
            corpus_id, episode_id, cast(Any, mode)
        )
        self._connection.commit()
        return result

    def remove_corpus_episode(self, corpus_id: int, episode_id: int) -> bool:
        result = self._aggregate_service.corpora.remove_episode(corpus_id, episode_id)
        self._connection.commit()
        return result

    def list_effective_corpus_episodes(self, corpus_id: int) -> tuple[int, ...]:
        return self._aggregate_service.corpora.list_effective_episode_ids(corpus_id)

    def list_corpus_work_memberships(
        self, corpus_id: int
    ) -> tuple[CorpusWorkMembershipRecord, ...]:
        return self._aggregate_service.corpora.list_work_memberships(corpus_id)

    def list_aggregates(
        self,
        *,
        container_type: str,
        container_id: int,
        measurement_target_type: str | None = None,
    ) -> tuple[AggregateRecord, ...]:
        return self._aggregate_service.list_with_staleness(
            container_type=cast(Any, container_type),
            container_id=container_id,
            measurement_target_type=cast(Any, measurement_target_type)
            if measurement_target_type is not None
            else None,
        )

    def compare_corpora(
        self,
        corpus_ids: Sequence[int],
        *,
        metric_name: str | None = None,
        metric_version: int | None = None,
        measurement_target_type: str | None = None,
        filter_json: str | None = None,
    ) -> list[dict[str, object]]:
        if not 2 <= len(corpus_ids) <= 5:
            raise ValueError("CORPUS_COMPARE_COUNT_INVALID")
        if filter_json is not None:
            try:
                filter_json = json.dumps(
                    json.loads(filter_json),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            except json.JSONDecodeError as exc:
                raise ValueError("CORPUS_COMPARE_FILTER_INVALID") from exc
        grouped: list[dict[tuple[str, int, str, str], dict[str, AggregateRecord]]] = []
        for corpus_id in corpus_ids:
            if self.get_corpus(corpus_id) is None:
                raise ValueError("CORPUS_NOT_FOUND")
            statistic_rows = self.list_aggregates(
                container_type="corpus", container_id=corpus_id
            )
            by_spec: dict[tuple[str, int, str, str], dict[str, AggregateRecord]] = {}
            for row in statistic_rows:
                spec_key: tuple[str, int, str, str] = (
                    row.metric_name,
                    row.metric_version,
                    str(row.measurement_target_type),
                    row.filter_json,
                )
                if metric_name is not None and row.metric_name != metric_name:
                    continue
                if metric_version is not None and row.metric_version != metric_version:
                    continue
                if (
                    measurement_target_type is not None
                    and row.measurement_target_type != measurement_target_type
                ):
                    continue
                if filter_json is not None and row.filter_json != filter_json:
                    continue
                by_spec.setdefault(spec_key, {})[row.statistic] = row
            grouped.append(by_spec)
        common = set(grouped[0]).intersection(*(set(item) for item in grouped[1:]))
        comparisons: list[dict[str, object]] = []
        for spec_key in sorted(common):
            values: list[dict[str, object]] = []
            for corpus_id, by_spec in zip(corpus_ids, grouped, strict=True):
                stats_by_name = by_spec[spec_key]
                median = stats_by_name.get("median")
                p25 = stats_by_name.get("p25")
                p75 = stats_by_name.get("p75")
                if median is None or p25 is None or p75 is None:
                    continue
                warnings = sorted(
                    {
                        warning
                        for row in stats_by_name.values()
                        for warning in json.loads(row.warning_json)
                    }
                )
                values.append(
                    {
                        "corpus_id": corpus_id,
                        "median": median.value_real,
                        "p25": p25.value_real,
                        "p75": p75.value_real,
                        "source_measurement_count": median.source_measurement_count,
                        "sample_count": median.sample_count,
                        "work_count": median.work_count,
                        "skipped_target_count": median.skipped_target_count,
                        "stale": any(row.stale for row in stats_by_name.values()),
                        "warnings": warnings,
                    }
                )
            if len(values) == len(corpus_ids):
                comparisons.append(
                    {
                        "metric_name": spec_key[0],
                        "metric_version": spec_key[1],
                        "measurement_target_type": spec_key[2],
                        "filter_json": spec_key[3],
                        "corpora": values,
                    }
                )
        if not comparisons:
            raise ValueError("CORPUS_COMPARE_AXIS_NOT_FOUND")
        return comparisons

    def recompute_aggregates(
        self,
        *,
        container_type: str,
        container_id: int,
        measurement_target_type: str,
        filter_json: str,
        metric_names: tuple[str, ...],
    ) -> AggregateRecomputeResult:
        return self._aggregate_service.recompute(
            (
                AggregateSpec(
                    cast(Any, container_type),
                    container_id,
                    cast(Any, measurement_target_type),
                    filter_json,
                    metric_names[0] if metric_names else "",
                    1,
                ),
            ),
            metric_names,
        )

    def list_profiles(self) -> tuple[ProfileRecord, ...]:
        return self._profile_service.list_profiles()

    def get_profile(self, profile_id: int) -> ProfileRecord | None:
        return self._profile_service.get_profile(profile_id)

    def create_profile_from_corpus(
        self,
        *,
        corpus_id: int,
        name: str,
        description: str,
        rules: Sequence[Mapping[str, object]],
    ) -> ProfileBuildResult:
        return self._profile_service.create_from_corpus(
            corpus_id=corpus_id,
            name=name,
            description=description,
            aggregate_groups=rules,
        )

    def create_manual_profile(
        self,
        *,
        name: str,
        description: str,
        rules: Sequence[Mapping[str, object]],
    ) -> ProfileBuildResult:
        return self._profile_service.create_manual(
            name=name, description=description, rules=rules
        )

    def create_profile_version(
        self,
        profile_id: int,
        *,
        parent_version_no: int,
        rules: Sequence[Mapping[str, object]],
    ) -> ProfileBuildResult:
        return self._profile_service.create_version(
            profile_id, parent_version_no=parent_version_no, rules=rules
        )

    def update_profile(
        self,
        profile_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> ProfileRecord:
        result = self._profile_service.update_profile(
            profile_id, name=name, description=description
        )
        self._connection.commit()
        return result

    def list_profile_versions(
        self, profile_id: int
    ) -> tuple[ProfileVersionRecord, ...]:
        return self._profile_service.list_versions(profile_id)

    def get_profile_version(
        self, profile_id: int, version_no: int
    ) -> ProfileVersionRecord | None:
        return self._profile_service.get_version(profile_id, version_no)

    def list_profile_rules(self, version_id: int) -> tuple[StyleRuleRecord, ...]:
        return self._profile_service.list_rules(version_id)

    def profile_aggregate_sources(self, rule_id: int) -> tuple[tuple[int, str], ...]:
        return self._profile_service.aggregate_sources(rule_id)

    def activate_profile(self, profile_id: int, version_no: int) -> ProfileRecord:
        result = self._profile_service.activate(profile_id, version_no)
        self._connection.commit()
        return result

    def archive_profile(self, profile_id: int) -> ProfileRecord:
        result = self._profile_service.archive(profile_id)
        self._connection.commit()
        return result
