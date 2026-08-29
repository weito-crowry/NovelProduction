import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { projectQueryKeys } from "../../api/queryKeys";
import { AppShell } from "../../components/layout/AppShell";
import { DirtyNavigationGuard } from "../../components/layout/DirtyNavigationGuard";
import { ConflictDialog } from "../conflicts/ConflictDialog";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextArea, TextInput } from "../../components/ui/Field";
import type {
  TimelineEventCreate,
  TimelineEventRecord,
  TimelineEventUpdate,
  TimelineMove,
  TimelineParticipantInput,
  TimelineRelationCreate,
} from "../../api/types";
import {
  createTimelineEvent,
  createTimelineRelation,
  fetchTimelineEvent,
  fetchTimelineEvents,
  fetchTimelineRange,
  fetchTimelineRelations,
  moveTimelineEvent,
  searchTimelineEvents,
  updateTimelineEvent,
} from "./timelineApi";

const PAGE_SIZE = 50;
type TimelineMode = "Browse" | "Search" | "Range";
interface EventFormValues {
  title: string;
  description: string;
  category: string;
  location_world_fact_id: string;
  cause_summary: string;
  consequence_summary: string;
  importance: string;
  participants: TimelineParticipantInput[];
}
interface CreateEventValues extends EventFormValues {
  event_key: string;
  event_date: string;
}

export function TimelinePage() {
  const { projectId, eventId } = useParams();
  const project = projectId ?? "";
  const selectedId = eventId === undefined ? null : Number(eventId);
  const [mode, setMode] = useState<TimelineMode>("Browse");
  const [searchText, setSearchText] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [activeRange, setActiveRange] = useState({ start: "", end: "" });
  const [offset, setOffset] = useState(0);
  const [records, setRecords] = useState<TimelineEventRecord[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const previousProject = useRef(project);
  const browseQuery = useQuery({
    queryKey: projectQueryKeys.timelineEvents(project, PAGE_SIZE, offset),
    queryFn: () => fetchTimelineEvents(project, PAGE_SIZE, offset),
    enabled: selectedId === null && mode === "Browse",
  });
  const searchQuery = useQuery({
    queryKey: projectQueryKeys.timelineEventSearch(
      project,
      activeSearch,
      PAGE_SIZE,
    ),
    queryFn: () => searchTimelineEvents(project, activeSearch, PAGE_SIZE),
    enabled: selectedId === null && mode === "Search" && activeSearch !== "",
  });
  const rangeQuery = useQuery({
    queryKey: projectQueryKeys.timelineRange(
      project,
      activeRange.start,
      activeRange.end,
      PAGE_SIZE,
    ),
    queryFn: () =>
      fetchTimelineRange(
        project,
        activeRange.start,
        activeRange.end,
        PAGE_SIZE,
      ),
    enabled:
      selectedId === null &&
      mode === "Range" &&
      activeRange.start !== "" &&
      activeRange.end !== "",
  });
  const result =
    mode === "Browse"
      ? browseQuery.data
      : mode === "Search"
        ? searchQuery.data
        : rangeQuery.data;
  useEffect(() => {
    if (previousProject.current === project) return;
    previousProject.current = project;
    setMode("Browse");
    setSearchText("");
    setActiveSearch("");
    setRangeStart("");
    setRangeEnd("");
    setActiveRange({ start: "", end: "" });
    setOffset(0);
    setRecords([]);
    setShowCreate(false);
  }, [project]);
  useEffect(() => {
    if (result === undefined) return;
    setRecords((current) =>
      mode === "Browse" && offset > 0 ? [...current, ...result] : result,
    );
  }, [mode, offset, result]);
  function changeMode(next: TimelineMode) {
    setMode(next);
    setOffset(0);
    setRecords([]);
    if (next !== "Search") {
      setSearchText("");
      setActiveSearch("");
    }
    if (next !== "Range") {
      setRangeStart("");
      setRangeEnd("");
      setActiveRange({ start: "", end: "" });
    }
  }
  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setRecords([]);
    setActiveSearch(searchText.trim());
  }
  function submitRange(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setRecords([]);
    setActiveRange({ start: rangeStart, end: rangeEnd });
  }
  const browseError =
    browseQuery.isError || searchQuery.isError || rangeQuery.isError;
  return (
    <AppShell projectId={project}>
      <div
        className={
          selectedId === null
            ? "entity-layout"
            : "entity-layout entity-detail-route"
        }
      >
        <section className="entity-list-pane">
          <div className="page-heading">
            <div>
              <p className="eyebrow">Timeline</p>
              <h1>Timeline</h1>
            </div>
            <Button
              type="button"
              onClick={() => setShowCreate((current) => !current)}
            >
              Add timeline event
            </Button>
          </div>
          {selectedId === null && (
            <>
              <fieldset className="mode-switcher">
                <legend>Timeline view</legend>
                {(["Browse", "Search", "Range"] as TimelineMode[]).map(
                  (item) => (
                    <label key={item}>
                      <input
                        type="radio"
                        name="timeline-mode"
                        checked={mode === item}
                        onChange={() => changeMode(item)}
                      />
                      {item}
                    </label>
                  ),
                )}
              </fieldset>
              {mode === "Search" && (
                <form className="entity-search" onSubmit={submitSearch}>
                  <FieldLabel htmlFor="timeline-search">
                    Search timeline events
                  </FieldLabel>
                  <div className="search-row">
                    <TextInput
                      id="timeline-search"
                      role="searchbox"
                      aria-label="Search timeline events"
                      value={searchText}
                      onChange={(event) => setSearchText(event.target.value)}
                    />
                    <Button type="submit">Search</Button>
                  </div>
                </form>
              )}
              {mode === "Range" && (
                <form className="range-form" onSubmit={submitRange}>
                  <div className="field-group">
                    <FieldLabel htmlFor="range-start">Range start</FieldLabel>
                    <TextInput
                      id="range-start"
                      type="date"
                      value={rangeStart}
                      onChange={(event) => setRangeStart(event.target.value)}
                      required
                    />
                  </div>
                  <div className="field-group">
                    <FieldLabel htmlFor="range-end">Range end</FieldLabel>
                    <TextInput
                      id="range-end"
                      type="date"
                      value={rangeEnd}
                      onChange={(event) => setRangeEnd(event.target.value)}
                      required
                    />
                  </div>
                  <Button type="submit">Load range</Button>
                </form>
              )}
              {showCreate && (
                <TimelineCreateForm
                  projectId={project}
                  onCreated={() => setShowCreate(false)}
                />
              )}
              {browseError && (
                <p role="alert">Unable to load timeline events.</p>
              )}
              {records.length === 0 &&
                ((mode === "Browse" && browseQuery.isPending) ||
                  (mode === "Search" && searchQuery.isPending) ||
                  (mode === "Range" && rangeQuery.isPending)) && (
                  <p role="status">Loading timeline events…</p>
                )}
              <div className="record-list">
                {records.map((record) => (
                  <Link
                    key={record.id}
                    className="record-list-item"
                    to={`/projects/${encodeURIComponent(project)}/timeline/${record.id}`}
                  >
                    <span>
                      <strong>{record.title}</strong>
                      <small>
                        {record.date_display} · {record.category}
                      </small>
                    </span>
                    <small>v{record.version}</small>
                  </Link>
                ))}
              </div>
              {mode === "Browse" && result?.length === PAGE_SIZE && (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setOffset((current) => current + PAGE_SIZE)}
                >
                  Load more
                </Button>
              )}
            </>
          )}
        </section>
        <section className="entity-detail-pane">
          {selectedId === null ? (
            <Card>
              <p className="eyebrow">Timeline</p>
              <h2>Select an event</h2>
              <p>Choose an event to view, edit, move, or relate it.</p>
            </Card>
          ) : (
            <TimelineEventEditor
              key={`${project}-${selectedId}`}
              projectId={project}
              eventId={selectedId}
            />
          )}
        </section>
      </div>
    </AppShell>
  );
}

function TimelineCreateForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [values, setValues] = useState<CreateEventValues>(emptyCreateEvent());
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (input: TimelineEventCreate) =>
      createTimelineEvent(projectId, input),
    retry: false,
  });
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const input = buildCreateEvent(values);
      const created = await mutation.mutateAsync(input);
      await invalidateTimelineFamilies(projectId, queryClient);
      onCreated();
      navigate(
        `/projects/${encodeURIComponent(projectId)}/timeline/${created.id}`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to create the timeline event.",
      );
    }
  }
  return (
    <Card>
      <h2>Create timeline event</h2>
      <form onSubmit={(event) => void submit(event)}>
        <TimelineFields
          values={values}
          setValues={(next) => setValues(next as CreateEventValues)}
          prefix="create-timeline"
          includeParticipants
          includeMeta
        />
        <div className="form-actions">
          <Button type="submit" disabled={mutation.isPending}>
            Create timeline event
          </Button>
        </div>
      </form>
      {error && <p role="alert">{error}</p>}
    </Card>
  );
}

function TimelineEventEditor({
  projectId,
  eventId,
}: {
  projectId: string;
  eventId: number;
}) {
  const queryClient = useQueryClient();
  const eventQuery = useQuery({
    queryKey: projectQueryKeys.timelineEvent(projectId, eventId),
    queryFn: () => fetchTimelineEvent(projectId, eventId),
    staleTime: 10_000,
  });
  const [baseline, setBaseline] = useState<TimelineEventRecord | null>(null);
  const [values, setValues] = useState<EventFormValues | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [latest, setLatest] = useState<TimelineEventRecord | null>(null);
  const [conflictError, setConflictError] = useState<string | null>(null);
  useEffect(() => {
    if (eventQuery.data && baseline === null) {
      setBaseline(eventQuery.data);
      setValues(toEventForm(eventQuery.data));
    }
  }, [baseline, eventQuery.data]);
  const dirty = useMemo(
    () =>
      values !== null && baseline !== null && hasEventChanges(values, baseline),
    [baseline, values],
  );
  if (eventQuery.isError)
    return <p role="alert">Unable to load the timeline event.</p>;
  if (eventQuery.isPending || baseline === null || values === null)
    return <p role="status">Loading timeline event…</p>;
  const currentBaseline = baseline;
  const currentValues = values;
  async function save() {
    setError(null);
    setSaved(false);
    try {
      const input = buildEventUpdate(currentValues, currentBaseline);
      if (input === null) return;
      const updated = await updateTimelineEvent(projectId, eventId, input);
      await invalidateTimelineFamilies(projectId, queryClient);
      queryClient.setQueryData(
        projectQueryKeys.timelineEvent(projectId, eventId),
        updated,
      );
      setBaseline(updated);
      setValues(toEventForm(updated));
      setSaved(true);
    } catch (caught) {
      if (!(
        isApiError(caught) &&
        caught.status === 409 &&
        caught.code === "VERSION_CONFLICT"
      )) {
        setError(
          caught instanceof Error
            ? caught.message
            : "Unable to save the timeline event.",
        );
        return;
      }
      await handleConflict(
        caught,
        projectId,
        eventId,
        queryClient,
        (resource) => {
          if (resource) {
            setLatest(resource);
            queryClient.setQueryData(
              projectQueryKeys.timelineEvent(projectId, eventId),
              resource,
            );
          } else
            setConflictError(
              "The latest timeline event could not be loaded. Your local edits were kept.",
            );
        },
      );
    }
  }
  async function loadLatest() {
    try {
      const current = await fetchTimelineEvent(projectId, eventId);
      queryClient.setQueryData(
        projectQueryKeys.timelineEvent(projectId, eventId),
        current,
      );
      setBaseline(current);
      setValues(toEventForm(current));
      setLatest(null);
      setConflictError(null);
    } catch {
      setConflictError(
        "The latest timeline event could not be loaded. Your local edits were kept.",
      );
    }
  }
  return (
    <>
      <Link
        className="back-link"
        to={`/projects/${encodeURIComponent(projectId)}/timeline`}
      >
        Back to timeline
      </Link>
      <Card>
        <div className="detail-heading">
          <div>
            <p className="eyebrow">Timeline event</p>
            <h2>{baseline.title}</h2>
          </div>
          <span className="version-note">Version {baseline.version}</span>
        </div>
        <p className="read-only-meta">
          Event key: {baseline.event_key || "(none)"} · Date:{" "}
          {baseline.date_display || "(undated)"} · Time start:{" "}
          {baseline.time_start || "(none)"} · Time end:{" "}
          {baseline.time_end || "(none)"} · Precision: {baseline.date_precision}{" "}
          · Canon: {baseline.canon_status}
        </p>
        <TimelineFields
          values={values}
          setValues={setValues}
          prefix="edit-timeline"
          includeParticipants={true}
          includeMeta={false}
        />
        <p className="read-only-meta">
          Date changes use the separate Move action.
        </p>
        {error && <p role="alert">{error}</p>}
        <div className="form-actions">
          <Button type="button" onClick={() => void save()} disabled={!dirty}>
            Save changes
          </Button>
          {dirty && <span className="dirty-indicator">Unsaved changes</span>}
          {!dirty && saved && <span className="saved-indicator">Saved</span>}
        </div>
      </Card>
      <MoveEventPanel
        projectId={projectId}
        eventId={eventId}
        baseline={baseline}
        onMoved={(updated) => {
          setBaseline(updated);
          setValues(toEventForm(updated));
        }}
      />
      <TimelineRelationsPanel projectId={projectId} eventId={eventId} />
      <DirtyNavigationGuard dirty={dirty} />
      {latest && (
        <ConflictDialog
          local={values}
          latest={latest}
          entityLabel="timeline event"
          onDiscard={() => void loadLatest()}
          onKeep={() => {
            setLatest(null);
            setConflictError(null);
          }}
          errorMessage={conflictError}
        />
      )}
      {conflictError && !latest && <p role="alert">{conflictError}</p>}
    </>
  );
}

function MoveEventPanel({
  projectId,
  eventId,
  baseline,
  onMoved,
}: {
  projectId: string;
  eventId: number;
  baseline: TimelineEventRecord;
  onMoved: (event: TimelineEventRecord) => void;
}) {
  const queryClient = useQueryClient();
  const [newDate, setNewDate] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (input: TimelineMove) =>
      moveTimelineEvent(projectId, eventId, input),
    retry: false,
  });
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!newDate) {
      setError("Enter a new date.");
      return;
    }
    setError(null);
    try {
      const updated = await mutation.mutateAsync({
        expected_version: baseline.version,
        new_date: newDate,
        ...(reason.trim() ? { reason: reason.trim() } : {}),
      });
      onMoved(updated);
      await invalidateTimelineFamilies(projectId, queryClient);
      setNewDate("");
      setReason("");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to move the timeline event.",
      );
    }
  }
  return (
    <Card>
      <h2>Move event</h2>
      <form className="move-form" onSubmit={(event) => void submit(event)}>
        <div className="field-group">
          <FieldLabel htmlFor="new-date">New date</FieldLabel>
          <TextInput
            id="new-date"
            type="date"
            value={newDate}
            onChange={(event) => setNewDate(event.target.value)}
            required
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor="move-reason">Move reason</FieldLabel>
          <TextInput
            id="move-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={mutation.isPending}>
          Move event
        </Button>
      </form>
      {error && <p role="alert">{error}</p>}
    </Card>
  );
}

function TimelineRelationsPanel({
  projectId,
  eventId,
}: {
  projectId: string;
  eventId: number;
}) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [records, setRecords] = useState<
    Awaited<ReturnType<typeof fetchTimelineRelations>>
  >([]);
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [type, setType] = useState("");
  const [error, setError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: projectQueryKeys.timelineRelations(
      projectId,
      eventId,
      PAGE_SIZE,
      offset,
    ),
    queryFn: () =>
      fetchTimelineRelations(projectId, eventId, PAGE_SIZE, offset),
    retry: false,
  });
  useEffect(() => {
    if (query.data !== undefined)
      setRecords((current) =>
        offset === 0 ? query.data : [...current, ...query.data],
      );
  }, [offset, query.data]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const input = buildRelation({ source, target, type }, eventId);
      const created = await createTimelineRelation(projectId, input);
      setRecords((current) => [...current, created]);
      await queryClient.invalidateQueries({
        queryKey: projectQueryKeys.timelineRelationsFamily(projectId),
      });
      await queryClient.invalidateQueries({
        queryKey: projectQueryKeys.episodeViews(projectId),
      });
      setSource("");
      setTarget("");
      setType("");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to create the timeline relation.",
      );
    }
  }
  return (
    <Card>
      <h2>Relations</h2>
      <form
        className="relationship-create-form"
        onSubmit={(event) => void submit(event)}
      >
        <div className="field-group">
          <FieldLabel htmlFor="relation-source">Source event ID</FieldLabel>
          <TextInput
            id="relation-source"
            inputMode="numeric"
            value={source}
            onChange={(event) => setSource(event.target.value)}
            required
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor="relation-target">Target event ID</FieldLabel>
          <TextInput
            id="relation-target"
            inputMode="numeric"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            required
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor="relation-type">Relation type</FieldLabel>
          <TextInput
            id="relation-type"
            value={type}
            onChange={(event) => setType(event.target.value)}
            required
          />
        </div>
        <Button type="submit">Create relation</Button>
      </form>
      {error && <p role="alert">{error}</p>}
      {query.isError ? (
        <p role="alert">Unable to load relations.</p>
      ) : query.isPending && records.length === 0 ? (
        <p role="status">Loading relations…</p>
      ) : records.length === 0 ? (
        <p>No relations yet.</p>
      ) : (
        <div className="record-list">
          {records.map((record) => (
            <div className="record-list-item" key={record.id}>
              <span>
                {record.source_event_id} → {record.target_event_id}
                <small>{record.relation_type}</small>
              </span>
              <small>v{record.version}</small>
            </div>
          ))}
        </div>
      )}
      {query.data?.length === PAGE_SIZE && (
        <Button
          type="button"
          variant="secondary"
          onClick={() => setOffset((current) => current + PAGE_SIZE)}
        >
          Load more relations
        </Button>
      )}
    </Card>
  );
}

function TimelineFields({
  values,
  setValues,
  prefix,
  includeParticipants,
  includeMeta,
}: {
  values: EventFormValues | CreateEventValues;
  setValues: (value: EventFormValues | CreateEventValues) => void;
  prefix: string;
  includeParticipants: boolean;
  includeMeta: boolean;
}) {
  const update = (field: keyof EventFormValues, value: string) =>
    setValues({ ...values, [field]: value });
  const updateParticipant = (
    index: number,
    field: keyof TimelineParticipantInput,
    value: string,
  ) =>
    setValues({
      ...values,
      participants: values.participants.map((item, itemIndex) =>
        itemIndex === index
          ? {
              ...item,
              [field]: field === "character_id" ? Number(value) || 0 : value,
            }
          : item,
      ),
    });
  return (
    <div className="editor-form">
      <div className="field-group field-span">
        <FieldLabel htmlFor={`${prefix}-title`}>Title</FieldLabel>
        <TextInput
          id={`${prefix}-title`}
          value={values.title}
          onChange={(event) => update("title", event.target.value)}
          required
        />
      </div>
      {includeMeta && (
        <>
          <div className="field-group">
            <FieldLabel htmlFor={`${prefix}-date`}>Event date</FieldLabel>
            <TextInput
              id={`${prefix}-date`}
              value={(values as CreateEventValues).event_date}
              onChange={(event) =>
                setValues({ ...values, event_date: event.target.value })
              }
            />
          </div>
          <div className="field-group">
            <FieldLabel htmlFor={`${prefix}-key`}>Event key</FieldLabel>
            <TextInput
              id={`${prefix}-key`}
              value={(values as CreateEventValues).event_key}
              onChange={(event) =>
                setValues({ ...values, event_key: event.target.value })
              }
            />
          </div>
        </>
      )}
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-category`}>Category</FieldLabel>
        <TextInput
          id={`${prefix}-category`}
          value={values.category}
          onChange={(event) => update("category", event.target.value)}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-location`}>
          Location world fact ID
        </FieldLabel>
        <TextInput
          id={`${prefix}-location`}
          inputMode="numeric"
          value={values.location_world_fact_id}
          onChange={(event) =>
            update("location_world_fact_id", event.target.value)
          }
        />
      </div>
      <div className="field-group field-span">
        <FieldLabel htmlFor={`${prefix}-description`}>Description</FieldLabel>
        <TextArea
          id={`${prefix}-description`}
          value={values.description}
          onChange={(event) => update("description", event.target.value)}
          rows={3}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-cause`}>Cause summary</FieldLabel>
        <TextArea
          id={`${prefix}-cause`}
          value={values.cause_summary}
          onChange={(event) => update("cause_summary", event.target.value)}
          rows={2}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-consequence`}>
          Consequence summary
        </FieldLabel>
        <TextArea
          id={`${prefix}-consequence`}
          value={values.consequence_summary}
          onChange={(event) =>
            update("consequence_summary", event.target.value)
          }
          rows={2}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-importance`}>Importance</FieldLabel>
        <TextInput
          id={`${prefix}-importance`}
          inputMode="numeric"
          value={values.importance}
          onChange={(event) => update("importance", event.target.value)}
        />
      </div>
      {includeParticipants && (
        <div className="field-group field-span">
          <div className="section-heading">
            <h3>Participants</h3>
            <Button
              type="button"
              variant="secondary"
              onClick={() =>
                setValues({
                  ...values,
                  participants: [
                    ...values.participants,
                    { character_id: 0, role: "" },
                  ],
                })
              }
            >
              Add participant
            </Button>
          </div>
          {values.participants.map((participant, index) => (
            <div
              className="participant-row"
              key={`${prefix}-participant-${index}`}
            >
              <div className="field-group">
                <FieldLabel htmlFor={`${prefix}-participant-${index}-id`}>
                  Participant character ID
                </FieldLabel>
                <TextInput
                  id={`${prefix}-participant-${index}-id`}
                  inputMode="numeric"
                  value={participant.character_id || ""}
                  onChange={(event) =>
                    updateParticipant(index, "character_id", event.target.value)
                  }
                  required
                />
              </div>
              <div className="field-group">
                <FieldLabel htmlFor={`${prefix}-participant-${index}-role`}>
                  Participant role
                </FieldLabel>
                <TextInput
                  id={`${prefix}-participant-${index}-role`}
                  value={participant.role}
                  onChange={(event) =>
                    updateParticipant(index, "role", event.target.value)
                  }
                  required
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={() =>
                  setValues({
                    ...values,
                    participants: values.participants.filter(
                      (_, itemIndex) => itemIndex !== index,
                    ),
                  })
                }
              >
                Remove
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function emptyCreateEvent(): CreateEventValues {
  return {
    title: "",
    event_date: "",
    event_key: "",
    description: "",
    category: "general",
    location_world_fact_id: "",
    cause_summary: "",
    consequence_summary: "",
    importance: "0",
    participants: [{ character_id: 0, role: "" }],
  };
}
function toEventForm(record: TimelineEventRecord): EventFormValues {
  return {
    title: record.title,
    description: record.description,
    category: record.category,
    location_world_fact_id:
      record.location_world_fact_id === null
        ? ""
        : String(record.location_world_fact_id),
    cause_summary: record.cause_summary,
    consequence_summary: record.consequence_summary,
    importance: String(record.importance),
    participants: record.participants.map((item) => ({
      character_id: item.character_id,
      role: item.role,
    })),
  };
}
function buildCreateEvent(values: CreateEventValues): TimelineEventCreate {
  const importance = parseNonNegative(values.importance);
  const location = optionalPositive(
    values.location_world_fact_id,
    "Location world fact ID",
  );
  const participants = buildParticipants(values.participants);
  return {
    title: values.title.trim(),
    ...(values.event_date.trim()
      ? { event_date: values.event_date.trim() }
      : {}),
    ...(values.event_key.trim() ? { event_key: values.event_key.trim() } : {}),
    ...(values.description ? { description: values.description } : {}),
    ...(values.category ? { category: values.category } : {}),
    ...(location === null ? {} : { location_world_fact_id: location }),
    ...(values.cause_summary ? { cause_summary: values.cause_summary } : {}),
    ...(values.consequence_summary
      ? { consequence_summary: values.consequence_summary }
      : {}),
    ...(importance === 0 ? {} : { importance }),
    ...(participants.length ? { participants } : {}),
  };
}
function hasEventChanges(
  values: EventFormValues,
  baseline: TimelineEventRecord,
): boolean {
  return (
    values.title !== baseline.title ||
    values.description !== baseline.description ||
    values.category !== baseline.category ||
    values.location_world_fact_id !==
      (baseline.location_world_fact_id === null
        ? ""
        : String(baseline.location_world_fact_id)) ||
    values.cause_summary !== baseline.cause_summary ||
    values.consequence_summary !== baseline.consequence_summary ||
    values.importance !== String(baseline.importance) ||
    JSON.stringify(values.participants) !==
      JSON.stringify(
        baseline.participants.map((item) => ({
          character_id: item.character_id,
          role: item.role,
        })),
      )
  );
}
function buildEventUpdate(
  values: EventFormValues,
  baseline: TimelineEventRecord,
): TimelineEventUpdate | null {
  if (!hasEventChanges(values, baseline)) return null;
  const input: TimelineEventUpdate = { expected_version: baseline.version };
  const textFields: Array<
    keyof Pick<
      EventFormValues,
      | "title"
      | "description"
      | "category"
      | "cause_summary"
      | "consequence_summary"
    >
  > = [
    "title",
    "description",
    "category",
    "cause_summary",
    "consequence_summary",
  ];
  for (const field of textFields)
    if (values[field] !== baseline[field]) input[field] = values[field];
  if (values.importance !== String(baseline.importance))
    input.importance = parseNonNegative(values.importance);
  if (
    values.location_world_fact_id !==
    (baseline.location_world_fact_id === null
      ? ""
      : String(baseline.location_world_fact_id))
  ) {
    if (
      !values.location_world_fact_id &&
      baseline.location_world_fact_id !== null
    )
      throw new Error("This field cannot currently be cleared by the API.");
    const location = optionalPositive(
      values.location_world_fact_id,
      "Location world fact ID",
    );
    if (location !== null) input.location_world_fact_id = location;
  }
  if (
    JSON.stringify(values.participants) !==
    JSON.stringify(
      baseline.participants.map((item) => ({
        character_id: item.character_id,
        role: item.role,
      })),
    )
  )
    input.participants = buildParticipants(values.participants);
  return input;
}
function buildParticipants(
  participants: TimelineParticipantInput[],
): TimelineParticipantInput[] {
  return participants.map((item) => {
    if (
      !Number.isInteger(item.character_id) ||
      item.character_id <= 0 ||
      !item.role.trim()
    )
      throw new Error(
        "Each participant needs a positive character ID and role.",
      );
    return { character_id: item.character_id, role: item.role.trim() };
  });
}
function buildRelation(
  values: { source: string; target: string; type: string },
  currentEventId: number,
): TimelineRelationCreate {
  const source = positiveInteger(values.source);
  const target = positiveInteger(values.target);
  if (source === null || target === null)
    throw new Error("Relation event IDs must be positive integers.");
  if (
    source === target ||
    (source !== currentEventId && target !== currentEventId)
  )
    throw new Error(
      "A relation must include the selected event and cannot relate an event to itself.",
    );
  if (!values.type.trim()) throw new Error("Relation type is required.");
  return {
    source_id: source,
    target_id: target,
    relation_type: values.type.trim(),
  };
}
function optionalPositive(value: string, label: string): number | null {
  if (!value.trim()) return null;
  const result = positiveInteger(value);
  if (result === null) throw new Error(`${label} must be a positive integer.`);
  return result;
}
function parseNonNegative(value: string): number {
  if (!/^\d+$/.test(value.trim()))
    throw new Error("Importance must be a non-negative integer.");
  return Number(value);
}
function positiveInteger(value: string): number | null {
  return /^[1-9]\d*$/.test(value.trim()) ? Number(value) : null;
}
async function handleConflict(
  caught: unknown,
  projectId: string,
  eventId: number,
  queryClient: ReturnType<typeof useQueryClient>,
  onCurrent: (resource: TimelineEventRecord | null) => void,
) {
  if (!(
    isApiError(caught) &&
    caught.status === 409 &&
    caught.code === "VERSION_CONFLICT"
  ))
    throw caught;
  const current = asRecord<TimelineEventRecord>(
    caught.details.current_resource,
  );
  if (current) {
    onCurrent(current);
    return;
  }
  try {
    const fetched = await fetchTimelineEvent(projectId, eventId);
    queryClient.setQueryData(
      projectQueryKeys.timelineEvent(projectId, eventId),
      fetched,
    );
    onCurrent(fetched);
  } catch {
    onCurrent(null);
  }
}
function asRecord<T>(value: unknown): T | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as T)
    : null;
}
async function invalidateTimelineFamilies(
  projectId: string,
  queryClient: ReturnType<typeof useQueryClient>,
) {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.timelineEventsFamily(projectId),
    }),
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.timelineEventSearchFamily(projectId),
    }),
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.timelineRangeFamily(projectId),
    }),
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.timelineRelationsFamily(projectId),
    }),
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.episodeViews(projectId),
    }),
  ]);
}
