import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { formatStoredJson, parseJsonEditor } from "../../api/jsonFields";
import { projectQueryKeys } from "../../api/queryKeys";
import type {
  WorldFactCreate,
  WorldFactRecord,
  WorldFactUpdate,
} from "../../api/types";
import { AppShell } from "../../components/layout/AppShell";
import { DirtyNavigationGuard } from "../../components/layout/DirtyNavigationGuard";
import { ConflictDialog } from "../../features/conflicts/ConflictDialog";
import { CanonStatusControl } from "../canon/CanonStatusControl";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextArea, TextInput } from "../../components/ui/Field";
import {
  createWorldFact,
  fetchWorldFact,
  fetchWorldFacts,
  searchWorldFacts,
  updateWorldFact,
} from "./worldApi";

const PAGE_SIZE = 50;

interface WorldFactFormValues {
  topic_key: string;
  category: string;
  title: string;
  statement: string;
  details_json: string;
  valid_from: string;
  valid_to: string;
  importance: string;
  reason: string;
}

export function WorldPage() {
  const { projectId, factId } = useParams();
  const project = projectId ?? "";
  const selectedId = factId === undefined ? null : Number(factId);
  const [searchText, setSearchText] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [records, setRecords] = useState<WorldFactRecord[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const previousProject = useRef(project);
  const browseQuery = useQuery({
    queryKey: projectQueryKeys.worldFacts(project, PAGE_SIZE, offset),
    queryFn: () => fetchWorldFacts(project, PAGE_SIZE, offset),
    enabled: activeSearch === "",
  });
  const searchQuery = useQuery({
    queryKey: projectQueryKeys.worldFactSearch(
      project,
      activeSearch,
      PAGE_SIZE,
      offset,
    ),
    queryFn: () => searchWorldFacts(project, activeSearch, PAGE_SIZE),
    enabled: activeSearch !== "",
  });
  const result = activeSearch === "" ? browseQuery.data : searchQuery.data;

  useEffect(() => {
    if (previousProject.current === project) return;
    previousProject.current = project;
    setSearchText("");
    setActiveSearch("");
    setOffset(0);
    setRecords([]);
    setShowCreate(false);
  }, [project]);

  useEffect(() => {
    if (result === undefined) return;
    setRecords((current) => (offset === 0 ? result : [...current, ...result]));
  }, [offset, result]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const normalized = searchText.trim();
    setOffset(0);
    setRecords([]);
    setActiveSearch(normalized);
  }

  function clearSearch() {
    setSearchText("");
    setActiveSearch("");
    setOffset(0);
    setRecords([]);
  }

  const listError = browseQuery.isError || searchQuery.isError;
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
              <p className="eyebrow">World</p>
              <h1>World</h1>
            </div>
            <Button
              type="button"
              onClick={() => setShowCreate((current) => !current)}
            >
              Add world fact
            </Button>
          </div>
          <form className="entity-search" onSubmit={submitSearch}>
            <FieldLabel htmlFor="world-search">Search world facts</FieldLabel>
            <div className="search-row">
              <TextInput
                id="world-search"
                aria-label="Search world facts"
                role="searchbox"
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
              />
              <Button type="submit">Search</Button>
              {activeSearch && (
                <Button type="button" variant="secondary" onClick={clearSearch}>
                  Clear
                </Button>
              )}
            </div>
          </form>
          {showCreate && (
            <WorldFactCreateForm
              projectId={project}
              onCreated={() => setShowCreate(false)}
            />
          )}
          {listError && <p role="alert">Unable to load world facts.</p>}
          {!listError &&
            records.length === 0 &&
            (browseQuery.isPending || searchQuery.isPending) && (
              <p role="status">Loading world facts…</p>
            )}
          {!listError &&
            !browseQuery.isPending &&
            !searchQuery.isPending &&
            records.length === 0 && (
              <p className="empty-state-inline">No world facts yet.</p>
            )}
          <div className="record-list">
            {records.map((record) => (
              <Link
                key={record.id}
                className="record-list-item"
                to={`/projects/${encodeURIComponent(project)}/world/${record.id}`}
              >
                <span>
                  <strong>{record.title}</strong>
                  <small>{record.statement}</small>
                </span>
                <small>v{record.version}</small>
              </Link>
            ))}
          </div>
          {activeSearch === "" && result?.length === PAGE_SIZE && (
            <Button
              type="button"
              variant="secondary"
              onClick={() => setOffset((current) => current + PAGE_SIZE)}
            >
              Load more
            </Button>
          )}
        </section>
        <section className="entity-detail-pane">
          {selectedId === null ? (
            <Card>
              <p className="eyebrow">World</p>
              <h2>Select a world fact</h2>
              <p>Choose a fact to view or edit it.</p>
            </Card>
          ) : (
            <WorldFactEditor
              key={`${project}-${selectedId}`}
              projectId={project}
              factId={selectedId}
            />
          )}
        </section>
      </div>
    </AppShell>
  );
}

function WorldFactCreateForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [values, setValues] =
    useState<WorldFactFormValues>(emptyWorldFactForm());
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (input: WorldFactCreate) => createWorldFact(projectId, input),
    retry: false,
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const importance = Number(values.importance);
      const input: WorldFactCreate = {
        statement: values.statement,
        topic_key: values.topic_key || undefined,
        category: values.category || undefined,
        title: values.title || undefined,
        details_json: parseJsonEditor(values.details_json),
        valid_from: values.valid_from || undefined,
        valid_to: values.valid_to || undefined,
        importance,
      };
      if (!Number.isInteger(importance) || importance < 0)
        throw new Error("Importance must be a non-negative integer.");
      const created = await mutation.mutateAsync(input);
      await invalidateWorld(projectId, queryClient);
      onCreated();
      navigate(
        `/projects/${encodeURIComponent(projectId)}/world/${created.id}`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to create the world fact.",
      );
    }
  }

  return (
    <Card>
      <h2>Create world fact</h2>
      <form onSubmit={(event) => void submit(event)}>
        <WorldFactFields
          values={values}
          setValues={setValues}
          prefix="create-world"
          includeReason={false}
        />
        <div className="form-actions">
          <Button type="submit" disabled={mutation.isPending}>
            Create world fact
          </Button>
        </div>
      </form>
      {error && <p role="alert">{error}</p>}
    </Card>
  );
}

function WorldFactEditor({
  projectId,
  factId,
}: {
  projectId: string;
  factId: number;
}) {
  const queryClient = useQueryClient();
  const factQuery = useQuery({
    queryKey: projectQueryKeys.worldFact(projectId, factId),
    queryFn: () => fetchWorldFact(projectId, factId),
    staleTime: 10_000,
  });
  const [baseline, setBaseline] = useState<WorldFactRecord | null>(null);
  const [values, setValues] = useState<WorldFactFormValues | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [conflictLatest, setConflictLatest] = useState<WorldFactRecord | null>(
    null,
  );
  const [conflictError, setConflictError] = useState<string | null>(null);

  useEffect(() => {
    if (factQuery.data && baseline === null) {
      setBaseline(factQuery.data);
      setValues(toWorldFactForm(factQuery.data));
    }
  }, [baseline, factQuery.data]);

  const dirty = useMemo(
    () =>
      values !== null &&
      baseline !== null &&
      hasWorldFactChanges(values, baseline),
    [baseline, values],
  );
  if (factQuery.isError)
    return <p role="alert">Unable to load the world fact.</p>;
  if (factQuery.isPending || baseline === null || values === null)
    return <p role="status">Loading world fact…</p>;
  const currentBaseline = baseline;
  const currentValues = values;

  async function save() {
    setValidationError(null);
    setSaveError(null);
    setSaved(false);
    try {
      const payload = buildWorldFactUpdate(currentValues, currentBaseline);
      if (payload === null) {
        if (currentValues.reason.trim())
          setValidationError("A reason alone does not require Save.");
        return;
      }
      const updated = await updateWorldFact(projectId, factId, payload);
      await invalidateWorld(projectId, queryClient);
      queryClient.setQueryData(
        projectQueryKeys.worldFact(projectId, factId),
        updated,
      );
      setBaseline(updated);
      setValues(toWorldFactForm(updated));
      setSaved(true);
    } catch (caught) {
      if (
        isApiError(caught) &&
        caught.status === 409 &&
        caught.code === "VERSION_CONFLICT"
      ) {
        const latest = asWorldFact(caught.details.current_resource);
        setConflictError(null);
        if (latest)
          queryClient.setQueryData(
            projectQueryKeys.worldFact(projectId, factId),
            latest,
          );
        setConflictLatest(latest);
        if (!latest) {
          try {
            const fetched = await fetchWorldFact(projectId, factId);
            queryClient.setQueryData(
              projectQueryKeys.worldFact(projectId, factId),
              fetched,
            );
            setConflictLatest(fetched);
          } catch {
            setConflictError(
              "The latest world fact could not be loaded. Your local edits were kept.",
            );
          }
        }
        return;
      }
      setSaveError(
        caught instanceof Error
          ? caught.message
          : "Unable to save the world fact.",
      );
    }
  }

  async function loadLatest() {
    try {
      const latest = await fetchWorldFact(projectId, factId);
      queryClient.setQueryData(
        projectQueryKeys.worldFact(projectId, factId),
        latest,
      );
      setBaseline(latest);
      setValues(toWorldFactForm(latest));
      setConflictLatest(null);
      setConflictError(null);
      setSaved(false);
    } catch {
      setConflictError(
        "The latest world fact could not be loaded. Your local edits were kept.",
      );
    }
  }

  return (
    <>
      <Link
        className="back-link"
        to={`/projects/${encodeURIComponent(projectId)}/world`}
      >
        Back to world
      </Link>
      <Card>
        <div className="detail-heading">
          <div>
            <p className="eyebrow">World fact</p>
            <h2>{baseline.title}</h2>
          </div>
          <span className="version-note">Version {baseline.version}</span>
        </div>
        <WorldFactFields
          values={values}
          setValues={setValues}
          prefix="edit-world"
          includeReason
        />
        <p className="read-only-meta">Canon status: {baseline.canon_status}</p>
        {validationError && <p role="alert">{validationError}</p>}
        {saveError && <p role="alert">{saveError}</p>}
        <div className="form-actions">
          <Button type="button" onClick={() => void save()}>
            Save changes
          </Button>
          {dirty && <span className="dirty-indicator">Unsaved changes</span>}
          {!dirty && saved && <span className="saved-indicator">Saved</span>}
        </div>
      </Card>
      <DirtyNavigationGuard dirty={dirty} />
      <CanonStatusControl
        projectId={projectId}
        entityType="world_fact"
        record={baseline}
        dirty={dirty}
        readCurrent={() => fetchWorldFact(projectId, factId)}
        onStatusChanged={async () => {
          const current = await fetchWorldFact(projectId, factId);
          queryClient.setQueryData(projectQueryKeys.worldFact(projectId, factId), current);
          setBaseline(current);
          setValues(toWorldFactForm(current));
        }}
      />
      {conflictLatest && (
        <ConflictDialog
          local={values}
          latest={conflictLatest}
          entityLabel="world fact"
          onDiscard={() => void loadLatest()}
          onKeep={() => setConflictLatest(null)}
          errorMessage={conflictError}
        />
      )}
      {conflictError && !conflictLatest && <p role="alert">{conflictError}</p>}
    </>
  );
}

function WorldFactFields({
  values,
  setValues,
  prefix,
  includeReason,
}: {
  values: WorldFactFormValues;
  setValues: (values: WorldFactFormValues) => void;
  prefix: string;
  includeReason: boolean;
}) {
  const update = (field: keyof WorldFactFormValues, value: string) =>
    setValues({ ...values, [field]: value });
  return (
    <div className="editor-form">
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-statement`}>Statement</FieldLabel>
        <TextArea
          id={`${prefix}-statement`}
          required
          value={values.statement}
          onChange={(event) => update("statement", event.target.value)}
          rows={3}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-title`}>Title</FieldLabel>
        <TextInput
          id={`${prefix}-title`}
          value={values.title}
          onChange={(event) => update("title", event.target.value)}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-topic-key`}>Topic key</FieldLabel>
        <TextInput
          id={`${prefix}-topic-key`}
          value={values.topic_key}
          onChange={(event) => update("topic_key", event.target.value)}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-category`}>Category</FieldLabel>
        <TextInput
          id={`${prefix}-category`}
          value={values.category}
          onChange={(event) => update("category", event.target.value)}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-valid-from`}>Valid from</FieldLabel>
        <TextInput
          id={`${prefix}-valid-from`}
          value={values.valid_from}
          onChange={(event) => update("valid_from", event.target.value)}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-valid-to`}>Valid to</FieldLabel>
        <TextInput
          id={`${prefix}-valid-to`}
          value={values.valid_to}
          onChange={(event) => update("valid_to", event.target.value)}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-importance`}>Importance</FieldLabel>
        <TextInput
          id={`${prefix}-importance`}
          type="number"
          min="0"
          step="1"
          value={values.importance}
          onChange={(event) => update("importance", event.target.value)}
        />
      </div>
      <div className="field-group field-span">
        <FieldLabel htmlFor={`${prefix}-details-json`}>Details JSON</FieldLabel>
        <TextArea
          id={`${prefix}-details-json`}
          value={values.details_json}
          onChange={(event) => update("details_json", event.target.value)}
          rows={6}
        />
      </div>
      {includeReason && (
        <div className="field-group field-span">
          <FieldLabel htmlFor={`${prefix}-reason`}>
            Reason (optional)
          </FieldLabel>
          <TextInput
            id={`${prefix}-reason`}
            value={values.reason}
            onChange={(event) => update("reason", event.target.value)}
          />
        </div>
      )}
    </div>
  );
}

function emptyWorldFactForm(): WorldFactFormValues {
  return {
    topic_key: "",
    category: "general",
    title: "",
    statement: "",
    details_json: "{}",
    valid_from: "",
    valid_to: "",
    importance: "0",
    reason: "",
  };
}
function toWorldFactForm(record: WorldFactRecord): WorldFactFormValues {
  return {
    topic_key: record.topic_key,
    category: record.category,
    title: record.title,
    statement: record.statement,
    details_json: formatStoredJson(record.details_json),
    valid_from: record.valid_from ?? "",
    valid_to: record.valid_to ?? "",
    importance: String(record.importance),
    reason: "",
  };
}
function hasWorldFactChanges(
  values: WorldFactFormValues,
  baseline: WorldFactRecord,
): boolean {
  return (
    values.statement !== baseline.statement ||
    values.topic_key !== baseline.topic_key ||
    values.category !== baseline.category ||
    values.title !== baseline.title ||
    values.valid_from !== (baseline.valid_from ?? "") ||
    values.valid_to !== (baseline.valid_to ?? "") ||
    Number(values.importance) !== baseline.importance ||
    jsonChanged(values.details_json, baseline.details_json)
  );
}
function jsonChanged(left: string, right: string): boolean {
  try {
    return (
      JSON.stringify(parseJsonEditor(left)) !==
      JSON.stringify(JSON.parse(right))
    );
  } catch {
    return true;
  }
}
function buildWorldFactUpdate(
  values: WorldFactFormValues,
  baseline: WorldFactRecord,
): WorldFactUpdate | null {
  if (!hasWorldFactChanges(values, baseline)) return null;
  for (const [, original, current] of [
    ["topic_key", baseline.topic_key, values.topic_key],
    ["title", baseline.title, values.title],
    ["valid_from", baseline.valid_from, values.valid_from],
    ["valid_to", baseline.valid_to, values.valid_to],
  ] as const)
    if (original !== null && original !== "" && current.trim() === "")
      throw new Error("This field cannot currently be cleared by the API.");
  const update: WorldFactUpdate = {
    statement: values.statement,
    expected_version: baseline.version,
  };
  if (values.topic_key !== baseline.topic_key)
    update.topic_key = values.topic_key;
  if (values.category !== baseline.category) update.category = values.category;
  if (values.title !== baseline.title) update.title = values.title;
  if (jsonChanged(values.details_json, baseline.details_json))
    update.details_json = parseJsonEditor(values.details_json);
  if (values.valid_from !== (baseline.valid_from ?? ""))
    update.valid_from = values.valid_from;
  if (values.valid_to !== (baseline.valid_to ?? ""))
    update.valid_to = values.valid_to;
  if (Number(values.importance) !== baseline.importance) {
    if (
      !Number.isInteger(Number(values.importance)) ||
      Number(values.importance) < 0
    )
      throw new Error("Importance must be a non-negative integer.");
    update.importance = Number(values.importance);
  }
  if (values.reason.trim()) update.reason = values.reason.trim();
  return update;
}
function asWorldFact(value: unknown): WorldFactRecord | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as WorldFactRecord)
    : null;
}
async function invalidateWorld(
  projectId: string,
  queryClient: ReturnType<typeof useQueryClient>,
) {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.worldFactsFamily(projectId),
    }),
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.worldFactSearchFamily(projectId),
    }),
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.episodeViews(projectId),
    }),
  ]);
}
