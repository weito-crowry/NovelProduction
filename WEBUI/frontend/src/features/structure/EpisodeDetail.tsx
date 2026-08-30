import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { projectQueryKeys } from "../../api/queryKeys";
import type {
  ContextParticipant,
  EpisodeContext,
  EpisodeOutline,
  EpisodeReferenceType,
  EpisodeView,
  OutlineParticipant,
  ProtectedInformationGuard,
} from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextInput } from "../../components/ui/Field";
import { CreateSceneForm } from "./NarrativeCreateForms";
import { EpisodeEditor } from "./NarrativeEditors";
import {
  addEpisodeReference,
  fetchEpisodeView,
  removeEpisodeReference,
} from "./structureApi";

const tabs = ["Details", "Scenes", "References", "Outline", "Context", "Draft history"] as const;
type EpisodeTab = (typeof tabs)[number];
const referenceTypes: EpisodeReferenceType[] = ["character", "world_fact", "timeline_event", "information"];

export function EpisodeDetail({
  projectId,
  episodeId,
}: {
  projectId: string;
  episodeId: number;
}) {
  const [activeTab, setActiveTab] = useState<EpisodeTab>("Details");
  const [showCreateScene, setShowCreateScene] = useState(false);
  const episodeQuery = useQuery({
    queryKey: projectQueryKeys.episodeView(projectId, episodeId),
    queryFn: () => fetchEpisodeView(projectId, episodeId),
  });

  if (episodeQuery.isPending) return <p role="status">Loading episode…</p>;
  if (episodeQuery.isError || !episodeQuery.data) return <p role="alert">Unable to load the episode.</p>;
  const view = episodeQuery.data;

  return (
    <>
      <Link className="back-link" to={`/projects/${encodeURIComponent(projectId)}/structure`}>Back to structure</Link>
      <div className="detail-heading">
        <div><p className="eyebrow">Episode {view.episode.position}</p><h1>{view.episode.title}</h1></div>
        <span className="version-note">Version {view.episode.version}</span>
      </div>
      <nav className="detail-tabs" aria-label="Episode detail sections">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            className={activeTab === tab ? "detail-tab active" : "detail-tab"}
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </nav>
      <EpisodeEditor
        key={view.episode.id}
        projectId={projectId}
        episode={view.episode}
        hidden={activeTab !== "Details"}
      />
      {activeTab === "Scenes" && (
        <ScenesSection
          projectId={projectId}
          view={view}
          onAddScene={() => setShowCreateScene(true)}
        />
      )}
      {activeTab === "References" && <ReferencesSection projectId={projectId} view={view} />}
      {activeTab === "Outline" && <OutlineSection outline={view.outline} />}
      {activeTab === "Context" && <ContextSection context={view.context} />}
      {activeTab === "Draft history" && <DraftHistorySection projectId={projectId} view={view} />}
      {showCreateScene && (
        <CreateSceneForm
          projectId={projectId}
          episodeId={episodeId}
          onClose={() => setShowCreateScene(false)}
        />
      )}
    </>
  );
}

function ScenesSection({
  projectId,
  view,
  onAddScene,
}: {
  projectId: string;
  view: EpisodeView;
  onAddScene: () => void;
}) {
  return (
    <Card>
      <div className="section-heading"><h2>Scenes</h2><Button type="button" onClick={onAddScene}>Add scene</Button></div>
      {view.scenes.length === 0 ? <p>No scenes yet.</p> : (
        <div className="record-list">
          {view.scenes.map((scene) => (
            <Link key={scene.id} className="record-list-item" to={`/projects/${encodeURIComponent(projectId)}/structure/scenes/${scene.id}`}>
              <span>{scene.position}. {scene.title}</span><small>v{scene.version}</small>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}

function ReferencesSection({ projectId, view }: { projectId: string; view: EpisodeView }) {
  const queryClient = useQueryClient();
  const [referenceType, setReferenceType] = useState<EpisodeReferenceType>("character");
  const [targetId, setTargetId] = useState("");
  const [role, setRole] = useState("participant");
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => addEpisodeReference(projectId, view.episode.id, {
      reference_type: referenceType,
      target_id: Number(targetId),
      ...(referenceType === "character" ? { role: role.trim() || "participant" } : {}),
    }),
    retry: false,
    onSuccess: async () => {
      setTargetId("");
      setError(null);
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeView(projectId, view.episode.id) });
    },
  });
  const removeMutation = useMutation({
    mutationFn: ({ type, id }: { type: string; id: number }) => removeEpisodeReference(projectId, view.episode.id, type, id),
    retry: false,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeView(projectId, view.episode.id) });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^[1-9]\d*$/.test(targetId)) {
      setError("Target ID must be a positive integer.");
      return;
    }
    setError(null);
    mutation.mutate();
  }

  return (
    <Card>
      <h2>References</h2>
      <form className="reference-form" onSubmit={submit}>
        <div className="field-group"><FieldLabel htmlFor="reference-type">Reference type</FieldLabel><select id="reference-type" className="field-control" value={referenceType} onChange={(event) => setReferenceType(event.target.value as EpisodeReferenceType)}>{referenceTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></div>
        <div className="field-group"><FieldLabel htmlFor="reference-target-id">Target ID</FieldLabel><TextInput id="reference-target-id" inputMode="numeric" value={targetId} onChange={(event) => setTargetId(event.target.value)} /></div>
        {referenceType === "character" && <div className="field-group"><FieldLabel htmlFor="reference-role">Role</FieldLabel><TextInput id="reference-role" value={role} onChange={(event) => setRole(event.target.value)} /></div>}
        <Button type="submit" disabled={mutation.isPending}>Add reference</Button>
      </form>
      {(error || mutation.isError) && <p role="alert">{error ?? apiMessage(mutation.error)}</p>}
      {view.episode_references.length === 0 ? <p>No references yet.</p> : (
        <div className="record-list">
          {view.episode_references.map((reference) => (
            <div className="record-list-item" key={reference.id}>
              <span>{reference.reference_type} #{reference.target_id}{reference.role ? ` — ${reference.role}` : ""}</span>
              <Button type="button" variant="danger" onClick={() => removeMutation.mutate({ type: reference.reference_type, id: reference.target_id })}>Remove reference</Button>
            </div>
          ))}
        </div>
      )}
      {removeMutation.isError && <p role="alert">{apiMessage(removeMutation.error)}</p>}
    </Card>
  );
}

function OutlineSection({ outline }: { outline: EpisodeOutline }) {
  return (
    <Card>
      <h2>Outline</h2>
      <h3>Episode</h3><RecordSummary record={outline.episode} fields={["title", "summary", "purpose", "position"]} />
      <h3>Scenes</h3><RecordList records={outline.scenes} fields={["position", "title", "summary", "purpose"]} empty="No scenes." />
      <h3>Participants</h3><ParticipantList participants={outline.participants} empty="No participants." />
      <h3>World facts</h3><RecordList records={outline.references.world_facts} fields={["title", "category", "statement", "importance"]} empty="No world facts." />
      <h3>Timeline events</h3><RecordList records={outline.references.timeline_events} fields={["title", "date_display", "description", "importance"]} empty="No timeline events." />
      <h3>Information</h3><RecordList records={outline.references.information} fields={["statement", "truth_status", "importance"]} empty="No information." />
      <h3>Protected information guards</h3><GuardList guards={outline.protected_information_guards} empty="No protected information guards." />
    </Card>
  );
}

function ContextSection({ context }: { context: EpisodeContext }) {
  return (
    <Card>
      <h2>Context</h2>
      <h3>Participants</h3><ContextParticipantList participants={context.participants} empty="No participants." />
      <h3>World facts</h3><RecordList records={context.world_facts} fields={["title", "category", "statement", "importance"]} empty="No world facts." />
      <h3>Timeline events</h3><RecordList records={context.timeline_events} fields={["title", "date_display", "description", "importance"]} empty="No timeline events." />
      <h3>Reader context</h3><ReaderContextDisplay context={context} />
      <h3>Protected information guards</h3><GuardList guards={context.protected_information_guards} empty="No protected information guards." />
      <h3>Recent context</h3><RecentContextDisplay context={context} />
      <h3>Foreshadowing notes</h3><JsonBlock value={context.foreshadowing_notes} />
      <h3>Context metadata</h3><JsonBlock value={context.context_meta} />
    </Card>
  );
}

function DraftHistorySection({ projectId, view }: { projectId: string; view: EpisodeView }) {
  return (
    <Card>
      <h2>Draft history</h2>
      {view.latest_draft ? (
        <section className="draft-latest"><h3>Latest draft — revision {view.latest_draft.revision}</h3><p>{view.latest_draft.created_at} · {view.latest_draft.source_agent ?? "unknown source"}</p><p>{view.latest_draft.change_summary || "No change summary"}</p><Link to={`/projects/${encodeURIComponent(projectId)}/manuscript/${view.episode.id}`}>Open manuscript</Link></section>
      ) : <p>No draft is available.</p>}
      <h3>Recent revisions</h3>
      {view.recent_draft_history.length === 0 ? <p>No draft history.</p> : <div className="record-list">{view.recent_draft_history.map((draft) => <div className="record-list-item" key={draft.id}><span>Revision {draft.revision} · {draft.created_at} · {draft.source_agent ?? "unknown source"}</span><small>{draft.change_summary || "No change summary"}</small><small>{draft.parent_draft_id === null ? "No parent draft" : `Parent draft #${draft.parent_draft_id}`}</small></div>)}</div>}
      <p className="helper-text">Draft history is read-only in D2.</p>
    </Card>
  );
}

function RecordSummary({ record, fields }: { record: object; fields: string[] }) {
  return <dl className="record-summary">{fields.map((field) => <div key={field}><dt>{field}</dt><dd>{formatValue((record as Record<string, unknown>)[field])}</dd></div>)}</dl>;
}

function RecordList({ records, fields, empty }: { records: object[]; fields: string[]; empty: string }) {
  if (!records.length) return <p>{empty}</p>;
  return <div className="record-list">{records.map((record, index) => <div className="record-list-item" key={recordId(record, index)}><RecordSummary record={record} fields={fields} /></div>)}</div>;
}

function ParticipantList({ participants, empty }: { participants: OutlineParticipant[]; empty: string }) {
  if (!participants.length) return <p>{empty}</p>;
  return <div className="record-list">{participants.map((participant) => <div className="record-list-item" key={participant.profile.id}><strong>{participant.profile.display_name}</strong><span>{participant.role}</span><small>{participant.profile.character_key}</small></div>)}</div>;
}

function ContextParticipantList({ participants, empty }: { participants: ContextParticipant[]; empty: string }) {
  if (!participants.length) return <p>{empty}</p>;
  return <div className="record-list">{participants.map((participant) => <div className="record-list-item" key={participant.profile.id}>
    <strong>{participant.profile.display_name}</strong>
    <h4>Effective state</h4>
    {participant.effective_state ? <RecordSummary record={participant.effective_state} fields={["physical_state", "emotional_state", "beliefs", "location_world_fact_id"]} /> : <p>No effective state.</p>}
    <h4>Effective relationships</h4>
    <RecordList records={participant.effective_relationships} fields={["relationship_id", "related_character_id", "relationship_type", "description", "canon_status"]} empty="No effective relationships." />
    <h4>Known information</h4>
    <RecordList records={participant.known_information} fields={["information_item_id", "knowledge_state", "source_episode_id", "statement", "truth_status", "canon_status"]} empty="No known information." />
  </div>)}</div>;
}

function GuardList({ guards, empty }: { guards: ProtectedInformationGuard[]; empty: string }) {
  if (!guards.length) return <p>{empty}</p>;
  return <div className="record-list">{guards.map((guard) => <div className="record-list-item" key={`${guard.information_item_id}-${guard.character_id ?? "reader"}`}><strong>Information #{guard.information_item_id}</strong><span>{guard.reason}</span><span>{guard.guard_text}</span>{guard.reveal_boundary && <small>Reveal episode {guard.reveal_boundary.episode_id}</small>}</div>)}</div>;
}

function ReaderContextDisplay({ context }: { context: EpisodeContext }) {
  return <div className="record-list"><div className="record-list-item"><strong>Known before episode</strong><span>{context.reader_context.known_before_episode.length} information items</span><RecordList records={context.reader_context.known_before_episode} fields={["statement", "truth_status"]} empty="None." /></div><div className="record-list-item"><strong>Reveal this episode</strong><span>{context.reader_context.reveal_this_episode.length} information items</span><RecordList records={context.reader_context.reveal_this_episode} fields={["statement", "truth_status"]} empty="None." /></div></div>;
}

function RecentContextDisplay({ context }: { context: EpisodeContext }) {
  return <div className="record-list"><RecordList records={context.recent_context.previous_episode_summaries} fields={["episode_id", "title", "summary"]} empty="No previous episode summaries." /><div className="record-list-item"><strong>Previous draft context HTML</strong><pre>{context.recent_context.previous_draft_context_html}</pre></div></div>;
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function recordId(record: object, index: number): string {
  const id = (record as { id?: unknown }).id;
  return typeof id === "number" ? String(id) : String(index);
}

function apiMessage(error: unknown): string {
  return isApiError(error) ? error.message : "Unable to update episode references.";
}
