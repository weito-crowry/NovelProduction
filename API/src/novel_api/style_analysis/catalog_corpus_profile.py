from __future__ import annotations

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
