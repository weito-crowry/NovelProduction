import { describe, expect, it } from "vitest";
import {
  buildAggregateGroups,
  buildManualRule,
  metricNamesForScope,
  mergeStyleDocumentEntries,
  type ManualRuleEditorState,
} from "./styleAnalysisUi";

describe("style analysis UI helpers", () => {
  it("keeps aggregate groups separate when aggregate policy versions differ", () => {
    const groups = buildAggregateGroups([
      {
        id: 1,
        metric_name: "sentence.len.p50",
        metric_version: 1,
        statistic: "median",
        aggregate_policy_version: 1,
        value_real: 10,
        source_measurement_count: 5,
        sample_count: 5,
        stale: false,
        warning_json: "[]",
      },
      {
        id: 2,
        metric_name: "sentence.len.p50",
        metric_version: 1,
        statistic: "p25",
        aggregate_policy_version: 2,
        value_real: 5,
        source_measurement_count: 5,
        sample_count: 5,
        stale: false,
        warning_json: "[]",
      },
    ]);

    expect(groups).toHaveLength(2);
  });

  it("builds a manual rule from editable scope and decimal range values", () => {
    const state: ManualRuleEditorState = {
      targetScope: "scene",
      selector: { function: ["daily"] },
      metricName: "sentence.len.p50",
      metricVersion: 1,
      preferredValue: "10.5",
      minValue: "3.5",
      maxValue: "15.75",
      weight: "1.25",
      enabled: true,
    };

    expect(buildManualRule(state)).toMatchObject({
      target_scope: "scene",
      scope_selector: { function: ["daily"] },
      preferred_value: 10.5,
      min_value: 3.5,
      max_value: 15.75,
      weight: 1.25,
    });
  });

  it("merges captured project documents into the lint/document selector", () => {
    const entries = mergeStyleDocumentEntries(
      [
        {
          reference_episode_id: 9,
          reference_work_id: 7,
          title: "Reference",
          order_index: 1,
          style_document_id: 10,
          current_text_revision_id: 2,
          current_structure_revision_id: 3,
          current_structure_kind: "automatic",
          analysis_status: { basic: { state: "current" } },
        },
      ],
      [
        {
          documentId: 21,
          episodeId: 2,
          title: "Project draft",
          currentTextRevisionId: 8,
          currentStructureRevisionId: 9,
          currentStructureKind: "manual",
        },
      ],
    );

    expect(entries.map((entry) => entry.documentId)).toEqual([10, 21]);
    expect(entries[1]).toMatchObject({ kind: "project_draft", episodeId: 2 });
  });

  it("merges server-listed project documents without session storage", () => {
    const entries = mergeStyleDocumentEntries(
      [],
      [],
      [{
        document_id: 21,
        kind: "project_episode_draft",
        current_text_revision_id: 8,
        current_structure_revision_id: 9,
        current_structure_kind: "automatic",
        analysis_status: { basic: { state: "current" } },
      }],
    );

    expect(entries).toEqual([expect.objectContaining({
      documentId: 21,
      episodeId: null,
      kind: "project_draft",
      currentTextRevisionId: 8,
    })]);
  });

  it("exposes the registry metrics only for compatible rule scopes", () => {
    const characterMetrics = metricNamesForScope("character");
    expect(characterMetrics).toContain("speaker.utterance_count");
    expect(characterMetrics).not.toContain("sentence.len.p50");
    expect(metricNamesForScope("scene")).toContain("semantic.exposition.char_ratio");
  });
});
