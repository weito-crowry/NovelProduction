import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { formatStoredJson, parseJsonEditor } from "../../api/jsonFields";
import { projectQueryKeys } from "../../api/queryKeys";
import type {
  CharacterCreate,
  CharacterRecord,
  CharacterStateRecord,
  CharacterStateSet,
  CharacterUpdate,
  EpisodeRecord,
  OutlineView,
  RelationshipCreate,
  RelationshipRecord,
  RelationshipUpdate,
} from "../../api/types";
import { AppShell } from "../../components/layout/AppShell";
import { DirtyNavigationGuard } from "../../components/layout/DirtyNavigationGuard";
import { ConflictDialog } from "../conflicts/ConflictDialog";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextArea, TextInput } from "../../components/ui/Field";
import { fetchOutline } from "../structure/structureApi";
import {
  createCharacter,
  createRelationship,
  fetchCharacter,
  fetchCharacterKnowledge,
  fetchCharacterState,
  fetchCharacterStateHistory,
  fetchCharacters,
  fetchRelationships,
  searchCharacters,
  setCharacterState,
  updateCharacter,
  updateRelationship,
} from "./characterApi";

const PAGE_SIZE = 50;
type CharacterTab = "Profile" | "Relationships" | "States" | "Knowledge";
interface CharacterFormValues {
  character_key: string;
  display_name: string;
  entity_type: string;
  description: string;
  birth_date: string;
  death_date: string;
  physical_description: string;
  occupation: string;
  core_beliefs: string;
  goals: string;
  fears: string;
  personality: string;
  speech_style: string;
  ai_attitude: string;
  genetic_modification_attitude: string;
  private_notes: string;
  profile_json: string;
  reason: string;
}
interface StateFormValues {
  physical_state: string;
  emotional_state: string;
  beliefs_json: string;
  location_world_fact_id: string;
  state_json: string;
}

export function CharactersPage() {
  const { projectId, characterId } = useParams();
  const project = projectId ?? "";
  const selectedId = characterId === undefined ? null : Number(characterId);
  const [searchText, setSearchText] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [records, setRecords] = useState<CharacterRecord[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const previousProject = useRef(project);
  const browseQuery = useQuery({
    queryKey: projectQueryKeys.characters(project, PAGE_SIZE, offset),
    queryFn: () => fetchCharacters(project, PAGE_SIZE, offset),
    enabled: activeSearch === "",
  });
  const searchQuery = useQuery({
    queryKey: projectQueryKeys.characterSearch(
      project,
      activeSearch,
      PAGE_SIZE,
      offset,
    ),
    queryFn: () => searchCharacters(project, activeSearch, PAGE_SIZE),
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
    if (result !== undefined)
      setRecords((current) =>
        offset === 0 ? result : [...current, ...result],
      );
  }, [offset, result]);
  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setRecords([]);
    setActiveSearch(searchText.trim());
  }
  function clearSearch() {
    setSearchText("");
    setActiveSearch("");
    setOffset(0);
    setRecords([]);
  }
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
              <p className="eyebrow">Characters</p>
              <h1>Characters</h1>
            </div>
            <Button
              type="button"
              onClick={() => setShowCreate((current) => !current)}
            >
              Add character
            </Button>
          </div>
          <form className="entity-search" onSubmit={submitSearch}>
            <FieldLabel htmlFor="character-search">
              Search characters
            </FieldLabel>
            <div className="search-row">
              <TextInput
                id="character-search"
                role="searchbox"
                aria-label="Search characters"
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
            <CharacterCreateForm
              projectId={project}
              onCreated={() => setShowCreate(false)}
            />
          )}
          {(browseQuery.isError || searchQuery.isError) && (
            <p role="alert">Unable to load characters.</p>
          )}
          {records.length === 0 &&
            (browseQuery.isPending || searchQuery.isPending) && (
              <p role="status">Loading characters…</p>
            )}
          <div className="record-list">
            {records.map((record) => (
              <Link
                key={record.id}
                className="record-list-item"
                to={`/projects/${encodeURIComponent(project)}/characters/${record.id}`}
              >
                <span>
                  <strong>{record.display_name}</strong>
                  <small>
                    {record.entity_type} · {record.description}
                  </small>
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
              <p className="eyebrow">Characters</p>
              <h2>Select a character</h2>
              <p>Choose a character to view or edit the profile.</p>
            </Card>
          ) : (
            <CharacterEditor
              key={`${project}-${selectedId}`}
              projectId={project}
              characterId={selectedId}
            />
          )}
        </section>
      </div>
    </AppShell>
  );
}

function CharacterCreateForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [values, setValues] =
    useState<CharacterFormValues>(emptyCharacterForm());
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (input: CharacterCreate) => createCharacter(projectId, input),
    retry: false,
  });
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const input: CharacterCreate = {
        display_name: values.display_name,
        character_key: values.character_key || undefined,
        entity_type: values.entity_type,
        description: values.description,
        birth_date: values.birth_date || undefined,
        death_date: values.death_date || undefined,
        physical_description: values.physical_description,
        occupation: values.occupation,
        core_beliefs: values.core_beliefs,
        goals: values.goals,
        fears: values.fears,
        personality: values.personality,
        speech_style: values.speech_style,
        ai_attitude: values.ai_attitude,
        genetic_modification_attitude: values.genetic_modification_attitude,
        private_notes: values.private_notes,
        profile_json: parseJsonEditor(values.profile_json),
      };
      const created = await mutation.mutateAsync(input);
      await invalidateCharacterFamilies(projectId, queryClient);
      onCreated();
      navigate(
        `/projects/${encodeURIComponent(projectId)}/characters/${created.id}`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to create the character.",
      );
    }
  }
  return (
    <Card>
      <h2>Create character</h2>
      <form onSubmit={(event) => void submit(event)}>
        <CharacterFields
          values={values}
          setValues={setValues}
          prefix="create-character"
          includeReason={false}
        />
        <div className="form-actions">
          <Button type="submit" disabled={mutation.isPending}>
            Create character
          </Button>
        </div>
      </form>
      {error && <p role="alert">{error}</p>}
    </Card>
  );
}

function CharacterEditor({
  projectId,
  characterId,
}: {
  projectId: string;
  characterId: number;
}) {
  const queryClient = useQueryClient();
  const characterQuery = useQuery({
    queryKey: projectQueryKeys.character(projectId, characterId),
    queryFn: () => fetchCharacter(projectId, characterId),
    staleTime: 10_000,
  });
  const [baseline, setBaseline] = useState<CharacterRecord | null>(null);
  const [values, setValues] = useState<CharacterFormValues | null>(null);
  const [tab, setTab] = useState<CharacterTab>("Profile");
  const [relationshipDirty, setRelationshipDirty] = useState(false);
  const [stateDirty, setStateDirty] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [conflictLatest, setConflictLatest] = useState<CharacterRecord | null>(
    null,
  );
  const [conflictError, setConflictError] = useState<string | null>(null);
  useEffect(() => {
    if (characterQuery.data && baseline === null) {
      setBaseline(characterQuery.data);
      setValues(toCharacterForm(characterQuery.data));
    }
  }, [baseline, characterQuery.data]);
  const dirty = useMemo(
    () =>
      values !== null &&
      baseline !== null &&
      hasCharacterChanges(values, baseline),
    [baseline, values],
  );
  const overallDirty = dirty || relationshipDirty || stateDirty;
  const reportRelationshipDirty = useCallback(
    (value: boolean) => setRelationshipDirty(value),
    [],
  );
  const reportStateDirty = useCallback(
    (value: boolean) => setStateDirty(value),
    [],
  );
  function selectTab(next: CharacterTab) {
    if (next === tab) return;
    const sectionDirty =
      (tab === "Relationships" && relationshipDirty) ||
      (tab === "States" && stateDirty);
    if (sectionDirty && !window.confirm("Discard unsaved section edits?"))
      return;
    if (sectionDirty) {
      setRelationshipDirty(false);
      setStateDirty(false);
    }
    setTab(next);
  }
  if (characterQuery.isError)
    return <p role="alert">Unable to load the character.</p>;
  if (characterQuery.isPending || baseline === null || values === null)
    return <p role="status">Loading character…</p>;
  const currentBaseline = baseline;
  const currentValues = values;
  async function save() {
    setValidationError(null);
    setSaveError(null);
    setSaved(false);
    try {
      const payload = buildCharacterUpdate(currentValues, currentBaseline);
      if (payload === null) {
        if (currentValues.reason.trim())
          setValidationError("A reason alone does not require Save.");
        return;
      }
      const updated = await updateCharacter(projectId, characterId, payload);
      await invalidateCharacterFamilies(projectId, queryClient);
      queryClient.setQueryData(
        projectQueryKeys.character(projectId, characterId),
        updated,
      );
      setBaseline(updated);
      setValues(toCharacterForm(updated));
      setSaved(true);
    } catch (caught) {
      if (
        isApiError(caught) &&
        caught.status === 409 &&
        caught.code === "VERSION_CONFLICT"
      ) {
        const latest = asRecord<CharacterRecord>(
          caught.details.current_resource,
        );
        setConflictLatest(latest);
        setConflictError(null);
        if (!latest) {
          try {
            const fetched = await fetchCharacter(projectId, characterId);
            queryClient.setQueryData(
              projectQueryKeys.character(projectId, characterId),
              fetched,
            );
            setConflictLatest(fetched);
          } catch {
            setConflictError(
              "The latest character could not be loaded. Your local edits were kept.",
            );
          }
        } else
          queryClient.setQueryData(
            projectQueryKeys.character(projectId, characterId),
            latest,
          );
        return;
      }
      setSaveError(
        caught instanceof Error
          ? caught.message
          : "Unable to save the character.",
      );
    }
  }
  async function loadLatest() {
    try {
      const latest = await fetchCharacter(projectId, characterId);
      queryClient.setQueryData(
        projectQueryKeys.character(projectId, characterId),
        latest,
      );
      setBaseline(latest);
      setValues(toCharacterForm(latest));
      setConflictLatest(null);
      setConflictError(null);
    } catch {
      setConflictError(
        "The latest character could not be loaded. Your local edits were kept.",
      );
    }
  }
  return (
    <>
      <Link
        className="back-link"
        to={`/projects/${encodeURIComponent(projectId)}/characters`}
      >
        Back to characters
      </Link>
      <Card>
        <div className="detail-heading">
          <div>
            <p className="eyebrow">Character</p>
            <h2>{baseline.display_name}</h2>
          </div>
          <span className="version-note">Version {baseline.version}</span>
        </div>
        <div
          className="detail-tabs"
          role="tablist"
          aria-label="Character detail sections"
        >
          {(
            [
              "Profile",
              "Relationships",
              "States",
              "Knowledge",
            ] as CharacterTab[]
          ).map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={tab === item}
              className={tab === item ? "detail-tab active" : "detail-tab"}
              onClick={() => selectTab(item)}
            >
              {item}
            </button>
          ))}
        </div>
        {tab === "Profile" && (
          <>
            <CharacterFields
              values={values}
              setValues={setValues}
              prefix="edit-character"
              includeReason
            />
            <p className="read-only-meta">
              Canon status: {baseline.canon_status}
            </p>
            {validationError && <p role="alert">{validationError}</p>}
            {saveError && <p role="alert">{saveError}</p>}
            <div className="form-actions">
              <Button type="button" onClick={() => void save()}>
                Save changes
              </Button>
              {dirty && (
                <span className="dirty-indicator">Unsaved changes</span>
              )}
              {!dirty && saved && (
                <span className="saved-indicator">Saved</span>
              )}
            </div>
          </>
        )}
      </Card>
      {tab === "Relationships" && (
        <RelationshipsPanel
          projectId={projectId}
          characterId={characterId}
          onDirtyChange={reportRelationshipDirty}
        />
      )}
      {tab === "States" && (
        <StatesPanel
          projectId={projectId}
          characterId={characterId}
          onDirtyChange={reportStateDirty}
        />
      )}
      {tab === "Knowledge" && (
        <KnowledgePanel projectId={projectId} characterId={characterId} />
      )}
      <DirtyNavigationGuard dirty={overallDirty} />
      {conflictLatest && (
        <ConflictDialog
          local={values}
          latest={conflictLatest}
          entityLabel="character"
          onDiscard={() => void loadLatest()}
          onKeep={() => setConflictLatest(null)}
          errorMessage={conflictError}
        />
      )}
      {conflictError && !conflictLatest && <p role="alert">{conflictError}</p>}
    </>
  );
}

function CharacterFields({
  values,
  setValues,
  prefix,
  includeReason,
}: {
  values: CharacterFormValues;
  setValues: (values: CharacterFormValues) => void;
  prefix: string;
  includeReason: boolean;
}) {
  const update = (field: keyof CharacterFormValues, value: string) =>
    setValues({ ...values, [field]: value });
  const textFields: Array<[keyof CharacterFormValues, string]> = [
    ["description", "Description"],
    ["physical_description", "Physical description"],
    ["occupation", "Occupation"],
    ["core_beliefs", "Core beliefs"],
    ["goals", "Goals"],
    ["fears", "Fears"],
    ["personality", "Personality"],
    ["speech_style", "Speech style"],
    ["ai_attitude", "AI attitude"],
    ["genetic_modification_attitude", "Genetic modification attitude"],
    ["private_notes", "Private notes"],
  ];
  return (
    <div className="editor-form">
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-display-name`}>Display name</FieldLabel>
        <TextInput
          id={`${prefix}-display-name`}
          required
          value={values.display_name}
          onChange={(event) => update("display_name", event.target.value)}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-character-key`}>
          Character key
        </FieldLabel>
        <TextInput
          id={`${prefix}-character-key`}
          value={values.character_key}
          onChange={(event) => update("character_key", event.target.value)}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-entity-type`}>Entity type</FieldLabel>
        <select
          id={`${prefix}-entity-type`}
          className="field-control"
          value={values.entity_type}
          onChange={(event) => update("entity_type", event.target.value)}
        >
          <option value="human">human</option>
          <option value="ai">ai</option>
          <option value="organization">organization</option>
        </select>
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-birth-date`}>Birth date</FieldLabel>
        <TextInput
          id={`${prefix}-birth-date`}
          value={values.birth_date}
          onChange={(event) => update("birth_date", event.target.value)}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`${prefix}-death-date`}>Death date</FieldLabel>
        <TextInput
          id={`${prefix}-death-date`}
          value={values.death_date}
          onChange={(event) => update("death_date", event.target.value)}
        />
      </div>
      {textFields.map(([field, label]) => (
        <div key={field} className="field-group field-span">
          <FieldLabel htmlFor={`${prefix}-${field}`}>{label}</FieldLabel>
          <TextArea
            id={`${prefix}-${field}`}
            value={values[field]}
            onChange={(event) => update(field, event.target.value)}
            rows={2}
          />
        </div>
      ))}
      <div className="field-group field-span">
        <FieldLabel htmlFor={`${prefix}-profile-json`}>Profile JSON</FieldLabel>
        <TextArea
          id={`${prefix}-profile-json`}
          value={values.profile_json}
          onChange={(event) => update("profile_json", event.target.value)}
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

async function invalidateRelationshipMutationCaches(
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
  affectedCharacterIds: number[],
) {
  const uniqueCharacterIds = [...new Set(affectedCharacterIds)];
  await Promise.all([
    ...uniqueCharacterIds.map((affectedCharacterId) =>
      queryClient.invalidateQueries({
        queryKey: projectQueryKeys.relationships(
          projectId,
          affectedCharacterId,
        ),
      }),
    ),
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.episodeViews(projectId),
    }),
  ]);
}

function RelationshipsPanel({
  projectId,
  characterId,
  onDirtyChange,
}: {
  projectId: string;
  characterId: number;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const relationshipsQuery = useQuery({
    queryKey: projectQueryKeys.relationships(projectId, characterId),
    queryFn: () => fetchRelationships(projectId, characterId),
  });
  const outlineQuery = useQuery({
    queryKey: projectQueryKeys.outline(projectId),
    queryFn: () => fetchOutline(projectId),
  });
  const [side, setSide] = useState<"source" | "target">("source");
  const [otherId, setOtherId] = useState("");
  const [type, setType] = useState("");
  const [description, setDescription] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [dirtyIds, setDirtyIds] = useState<Set<number>>(() => new Set());
  const mutation = useMutation({
    mutationFn: (input: RelationshipCreate) =>
      createRelationship(projectId, input),
    retry: false,
  });
  const episodes = episodeOptions(outlineQuery.data);
  useEffect(() => {
    onDirtyChange(dirtyIds.size > 0);
  }, [dirtyIds, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  const reportEditorDirty = useCallback((id: number, dirty: boolean) => {
    setDirtyIds((current) => {
      if (current.has(id) === dirty) return current;
      const next = new Set(current);
      if (dirty) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const id = positiveInteger(otherId);
    if (id === null) {
      setError("Other character ID must be a positive integer.");
      return;
    }
    if (id === characterId) {
      setError("A character cannot relate to itself.");
      return;
    }
    if (!type.trim()) {
      setError("Relationship type is required.");
      return;
    }
    try {
      const created = await mutation.mutateAsync({
        source_character_id: side === "source" ? characterId : id,
        target_character_id: side === "source" ? id : characterId,
        relationship_type: type,
        description,
        valid_from_episode_id: from ? Number(from) : undefined,
        valid_to_episode_id: to ? Number(to) : undefined,
      });
      await invalidateRelationshipMutationCaches(queryClient, projectId, [
        created.source_character_id,
        created.target_character_id,
      ]);
      setOtherId("");
      setType("");
      setDescription("");
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to create the relationship.",
      );
    }
  }
  if (relationshipsQuery.isPending)
    return (
      <Card>
        <p role="status">Loading relationships…</p>
      </Card>
    );
  if (relationshipsQuery.isError)
    return (
      <Card>
        <p role="alert">Unable to load relationships.</p>
      </Card>
    );
  return (
    <Card>
      <div className="section-heading">
        <h2>Relationships</h2>
      </div>
      <form
        className="relationship-create-form"
        onSubmit={(event) => void submit(event)}
      >
        <fieldset>
          <legend>Selected character is</legend>
          <label>
            <input
              type="radio"
              checked={side === "source"}
              onChange={() => setSide("source")}
            />{" "}
            source
          </label>
          <label>
            <input
              type="radio"
              checked={side === "target"}
              onChange={() => setSide("target")}
            />{" "}
            target
          </label>
        </fieldset>
        <div className="field-group">
          <FieldLabel htmlFor="relationship-other-id">
            Other character ID
          </FieldLabel>
          <TextInput
            id="relationship-other-id"
            inputMode="numeric"
            value={otherId}
            onChange={(event) => setOtherId(event.target.value)}
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor="relationship-type">Relationship type</FieldLabel>
          <TextInput
            id="relationship-type"
            required
            value={type}
            onChange={(event) => setType(event.target.value)}
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor="relationship-description">
            Description
          </FieldLabel>
          <TextArea
            id="relationship-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
          />
        </div>
        <EpisodeSelect
          id="relationship-from-episode"
          label="Valid from episode"
          value={from}
          options={episodes}
          onChange={setFrom}
        />
        <EpisodeSelect
          id="relationship-to-episode"
          label="Valid to episode"
          value={to}
          options={episodes}
          onChange={setTo}
        />
        <Button type="submit" disabled={mutation.isPending}>
          Create relationship
        </Button>
      </form>
      {error && <p role="alert">{error}</p>}
      {relationshipsQuery.data.length === 0 ? (
        <p>No relationships yet.</p>
      ) : (
        <div className="record-list">
          {relationshipsQuery.data.map((record) => (
            <RelationshipEditor
              key={record.id}
              projectId={projectId}
              characterId={characterId}
              record={record}
              episodes={episodes}
              onDirtyChange={(dirty) => reportEditorDirty(record.id, dirty)}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

function RelationshipEditor({
  projectId,
  characterId,
  record,
  episodes,
  onDirtyChange,
}: {
  projectId: string;
  characterId: number;
  record: RelationshipRecord;
  episodes: EpisodeRecord[];
  onDirtyChange: (dirty: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [baseline, setBaseline] = useState(record);
  const [type, setType] = useState(record.relationship_type);
  const [description, setDescription] = useState(record.description);
  const [from, setFrom] = useState(
    baseline.valid_from_episode_id === null
      ? ""
      : String(baseline.valid_from_episode_id),
  );
  const [to, setTo] = useState(
    baseline.valid_to_episode_id === null
      ? ""
      : String(baseline.valid_to_episode_id),
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<RelationshipRecord | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const mutation = useMutation({
    mutationFn: (input: RelationshipUpdate) =>
      updateRelationship(projectId, record.id, input),
    retry: false,
  });
  const dirty =
    type !== baseline.relationship_type ||
    description !== baseline.description ||
    from !==
      (baseline.valid_from_episode_id === null
        ? ""
        : String(baseline.valid_from_episode_id)) ||
    to !==
      (baseline.valid_to_episode_id === null
        ? ""
        : String(baseline.valid_to_episode_id));
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty && latest === null && record.version !== baseline.version) {
      adoptLatest(record);
    }
  }, [baseline.version, dirty, latest, record]);
  async function save() {
    if (!dirty) return;
    const input: RelationshipUpdate = {
      expected_version: baseline.version,
      relationship_type: type,
      ...(description !== baseline.description ? { description } : {}),
      ...(from !==
      (baseline.valid_from_episode_id === null
        ? ""
        : String(baseline.valid_from_episode_id))
        ? from
          ? { valid_from_episode_id: Number(from) }
          : { clear_valid_from: true }
        : {}),
      ...(to !==
      (baseline.valid_to_episode_id === null
        ? ""
        : String(baseline.valid_to_episode_id))
        ? to
          ? { valid_to_episode_id: Number(to) }
          : { clear_valid_to: true }
        : {}),
      ...(reason.trim() ? { reason: reason.trim() } : {}),
    };
    try {
      const updated = await mutation.mutateAsync(input);
      setBaseline(updated);
      adoptLatest(updated);
      setReason("");
      queryClient.setQueryData<RelationshipRecord[] | undefined>(
        projectQueryKeys.relationships(projectId, characterId),
        (current) =>
          current?.map((item) => (item.id === updated.id ? updated : item)),
      );
      await invalidateRelationshipMutationCaches(queryClient, projectId, [
        updated.source_character_id,
        updated.target_character_id,
      ]);
      setError(null);
    } catch (caught) {
      if (
        isApiError(caught) &&
        caught.status === 409 &&
        caught.code === "VERSION_CONFLICT"
      ) {
        const current = asRecord<RelationshipRecord>(
          caught.details.current_resource,
        );
        if (current) {
          setLatest(current);
          queryClient.setQueryData<RelationshipRecord[] | undefined>(
            projectQueryKeys.relationships(projectId, characterId),
            (rows) =>
              rows?.map((item) => (item.id === current.id ? current : item)),
          );
          setError(null);
        } else {
          try {
            const rows = await fetchRelationships(projectId, characterId);
            queryClient.setQueryData(
              projectQueryKeys.relationships(projectId, characterId),
              rows,
            );
            const found = rows.find((item) => item.id === baseline.id);
            if (found) setLatest(found);
            else
              setError(
                "The relationship no longer appears in the selected character list.",
              );
          } catch {
            setError(
              "The latest relationship could not be loaded. Your local edits were kept.",
            );
          }
        }
        setConflictOpen(true);
        return;
      }
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to save relationship.",
      );
    }
  }
  async function loadLatest() {
    try {
      const rows = await fetchRelationships(projectId, characterId);
      queryClient.setQueryData(
        projectQueryKeys.relationships(projectId, characterId),
        rows,
      );
      const found = rows.find((item) => item.id === baseline.id);
      if (!found) {
        setError(
          "The relationship no longer appears in the selected character list.",
        );
        return;
      }
      adoptLatest(found);
    } catch {
      setError(
        "The latest relationship could not be loaded. Your local edits were kept.",
      );
    }
  }
  function adoptLatest(value: RelationshipRecord) {
    setBaseline(value);
    setType(value.relationship_type);
    setDescription(value.description);
    setFrom(
      value.valid_from_episode_id === null
        ? ""
        : String(value.valid_from_episode_id),
    );
    setTo(
      value.valid_to_episode_id === null
        ? ""
        : String(value.valid_to_episode_id),
    );
    setReason("");
    setLatest(null);
    setConflictOpen(false);
    setError(null);
  }
  return (
    <div className="relationship-editor">
      <div>
        <strong>#{baseline.id}</strong> {baseline.source_character_id} →{" "}
        {baseline.target_character_id}
      </div>
      <div className="editor-form">
        <div className="field-group">
          <FieldLabel htmlFor={`relationship-${baseline.id}-type`}>
            Relationship type
          </FieldLabel>
          <TextInput
            id={`relationship-${baseline.id}-type`}
            value={type}
            onChange={(event) => setType(event.target.value)}
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor={`relationship-${baseline.id}-description`}>
            Description
          </FieldLabel>
          <TextInput
            id={`relationship-${baseline.id}-description`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
        <EpisodeSelect
          id={`relationship-${baseline.id}-from`}
          label="Valid from episode"
          value={from}
          options={episodes}
          onChange={setFrom}
        />
        <EpisodeSelect
          id={`relationship-${baseline.id}-to`}
          label="Valid to episode"
          value={to}
          options={episodes}
          onChange={setTo}
        />
      </div>
      <div className="field-group">
        <FieldLabel htmlFor={`relationship-${baseline.id}-reason`}>
          Reason (optional)
        </FieldLabel>
        <TextInput
          id={`relationship-${baseline.id}-reason`}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </div>
      <Button
        type="button"
        onClick={() => void save()}
        disabled={!dirty || mutation.isPending}
      >
        Save relationship
      </Button>
      {error && <p role="alert">{error}</p>}
      {conflictOpen && (
        <ConflictDialog
          local={{ type, description, from, to, reason }}
          latest={latest}
          entityLabel="relationship"
          onDiscard={() => void loadLatest()}
          onKeep={() => {
            setConflictOpen(false);
            setLatest(null);
            setError(null);
          }}
        />
      )}
    </div>
  );
}

function StatesPanel({
  projectId,
  characterId,
  onDirtyChange,
}: {
  projectId: string;
  characterId: number;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const outlineQuery = useQuery({
    queryKey: projectQueryKeys.outline(projectId),
    queryFn: () => fetchOutline(projectId),
  });
  const [episodeId, setEpisodeId] = useState<number | null>(null);
  const [episodeDirty, setEpisodeDirty] = useState(false);
  const episodes = episodeOptions(outlineQuery.data);
  useEffect(() => {
    if (episodeId === null && episodes[0]) setEpisodeId(episodes[0].id);
  }, [episodeId, episodes]);
  useEffect(() => {
    onDirtyChange(episodeDirty);
  }, [episodeDirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  const historyQuery = useQuery({
    queryKey: projectQueryKeys.characterStateHistory(projectId, characterId),
    queryFn: () => fetchCharacterStateHistory(projectId, characterId),
  });
  function selectEpisode(value: string) {
    const nextEpisodeId = Number(value);
    if (nextEpisodeId === episodeId) return;
    if (episodeDirty && !window.confirm("Discard unsaved state edits?")) return;
    setEpisodeDirty(false);
    setEpisodeId(nextEpisodeId);
  }
  if (outlineQuery.isError || historyQuery.isError)
    return (
      <Card>
        <p role="alert">Unable to load character state.</p>
      </Card>
    );
  if (outlineQuery.isPending || historyQuery.isPending || episodeId === null)
    return (
      <Card>
        <p role="status">Loading character state…</p>
      </Card>
    );
  return (
    <Card>
      <div className="section-heading">
        <h2>States</h2>
        <EpisodeSelect
          id="state-episode"
          label="Episode"
          value={String(episodeId)}
          options={episodes}
          onChange={selectEpisode}
        />
      </div>
      <StateEpisodeEditor
        key={`${projectId}-${characterId}-${episodeId}`}
        projectId={projectId}
        characterId={characterId}
        episodeId={episodeId}
        onDirtyChange={setEpisodeDirty}
      />
      <h3>History</h3>
      {(historyQuery.data ?? []).length === 0 ? (
        <p>No state history.</p>
      ) : (
        <div className="record-list">
          {(historyQuery.data ?? []).map((item) => (
            <div className="record-list-item" key={item.id}>
              Episode {item.episode_id} · v{item.version}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function StateEpisodeEditor({
  projectId,
  characterId,
  episodeId,
  onDirtyChange,
}: {
  projectId: string;
  characterId: number;
  episodeId: number;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const effectiveQuery = useQuery({
    queryKey: projectQueryKeys.characterState(
      projectId,
      characterId,
      episodeId,
    ),
    queryFn: () => fetchCharacterState(projectId, characterId, episodeId),
    retry: false,
  });
  const [baseline, setBaseline] = useState<CharacterStateRecord | null>(null);
  const [values, setValues] = useState<StateFormValues | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<CharacterStateRecord | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const dirty = values !== null && hasStateChanges(values, baseline);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  useEffect(() => {
    if (!effectiveQuery.isSuccess) return;
    const baselineVersion = baseline?.version ?? null;
    const queryVersion = effectiveQuery.data?.version ?? null;
    const shouldAdopt =
      values === null || (!dirty && baselineVersion !== queryVersion);
    if (!shouldAdopt) return;
    setBaseline(effectiveQuery.data);
    setValues(toStateForm(effectiveQuery.data));
    setLatest(null);
    setConflictOpen(false);
  }, [baseline, dirty, effectiveQuery.data, effectiveQuery.isSuccess, values]);
  if (effectiveQuery.isError)
    return <p role="alert">Unable to load character state.</p>;
  if (effectiveQuery.isPending || values === null)
    return <p role="status">Loading character state…</p>;
  const currentValues = values;
  async function save() {
    if (!dirty) return;
    try {
      const input = buildStateSet(currentValues, baseline);
      const saved = await setCharacterState(
        projectId,
        characterId,
        episodeId,
        input,
      );
      queryClient.setQueryData(
        projectQueryKeys.characterState(projectId, characterId, episodeId),
        saved,
      );
      setBaseline(saved);
      setValues(toStateForm(saved));
      setLatest(null);
      setConflictOpen(false);
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: projectQueryKeys.characterStateHistory(
            projectId,
            characterId,
          ),
        }),
        queryClient.invalidateQueries({
          queryKey: projectQueryKeys.episodeViews(projectId),
        }),
      ]);
    } catch (caught) {
      if (
        isApiError(caught) &&
        caught.status === 409 &&
        caught.code === "VERSION_CONFLICT"
      ) {
        const current = asRecord<CharacterStateRecord>(
          caught.details.current_resource,
        );
        if (current) {
          setLatest(current);
          queryClient.setQueryData(
            projectQueryKeys.characterState(projectId, characterId, episodeId),
            current,
          );
        } else {
          try {
            const fetched = await fetchCharacterState(
              projectId,
              characterId,
              episodeId,
            );
            queryClient.setQueryData(
              projectQueryKeys.characterState(
                projectId,
                characterId,
                episodeId,
              ),
              fetched,
            );
            setLatest(fetched);
          } catch {
            setError(
              "The latest state could not be loaded. Your local edits were kept.",
            );
          }
        }
        setConflictOpen(true);
        return;
      }
      setError(
        caught instanceof Error ? caught.message : "Unable to save the state.",
      );
    }
  }
  const update = (field: keyof StateFormValues, value: string) =>
    setValues({ ...currentValues, [field]: value });
  async function loadLatest() {
    try {
      const fetched = await fetchCharacterState(
        projectId,
        characterId,
        episodeId,
      );
      queryClient.setQueryData(
        projectQueryKeys.characterState(projectId, characterId, episodeId),
        fetched,
      );
      setBaseline(fetched);
      setValues(toStateForm(fetched));
      setLatest(null);
      setConflictOpen(false);
      setError(null);
    } catch {
      setError(
        "The latest state could not be loaded. Your local edits were kept.",
      );
    }
  }
  return (
    <>
      {baseline === null && <p>No state for this episode.</p>}
      <div className="editor-form">
        <div className="field-group">
          <FieldLabel htmlFor="physical-state">Physical state</FieldLabel>
          <TextArea
            id="physical-state"
            value={values.physical_state}
            onChange={(event) => update("physical_state", event.target.value)}
            rows={2}
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor="emotional-state">Emotional state</FieldLabel>
          <TextArea
            id="emotional-state"
            value={values.emotional_state}
            onChange={(event) => update("emotional_state", event.target.value)}
            rows={2}
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor="beliefs-json">Beliefs JSON</FieldLabel>
          <TextArea
            id="beliefs-json"
            value={values.beliefs_json}
            onChange={(event) => update("beliefs_json", event.target.value)}
            rows={4}
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor="state-json">State JSON</FieldLabel>
          <TextArea
            id="state-json"
            value={values.state_json}
            onChange={(event) => update("state_json", event.target.value)}
            rows={4}
          />
        </div>
        <div className="field-group">
          <FieldLabel htmlFor="state-location-world-fact-id">
            Location world fact ID
          </FieldLabel>
          <TextInput
            id="state-location-world-fact-id"
            inputMode="numeric"
            value={values.location_world_fact_id}
            onChange={(event) =>
              update("location_world_fact_id", event.target.value)
            }
          />
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
      <Button type="button" onClick={() => void save()} disabled={!dirty}>
        Save state
      </Button>
      {conflictOpen && (
        <ConflictDialog
          local={currentValues}
          latest={latest}
          entityLabel="character state"
          onDiscard={() => void loadLatest()}
          onKeep={() => {
            setConflictOpen(false);
            setLatest(null);
            setError(null);
          }}
          errorMessage={error}
        />
      )}
    </>
  );
}

function KnowledgePanel({
  projectId,
  characterId,
}: {
  projectId: string;
  characterId: number;
}) {
  const outlineQuery = useQuery({
    queryKey: projectQueryKeys.outline(projectId),
    queryFn: () => fetchOutline(projectId),
  });
  const [episodeId, setEpisodeId] = useState<number | null>(null);
  const episodes = episodeOptions(outlineQuery.data);
  useEffect(() => {
    if (episodeId === null && episodes[0]) setEpisodeId(episodes[0].id);
  }, [episodeId, episodes]);
  const knowledgeQuery = useQuery({
    queryKey: projectQueryKeys.characterKnowledge(
      projectId,
      characterId,
      episodeId ?? 0,
    ),
    queryFn: () =>
      fetchCharacterKnowledge(projectId, characterId, episodeId ?? 0),
    enabled: episodeId !== null,
  });
  if (outlineQuery.isError || knowledgeQuery.isError)
    return (
      <Card>
        <p role="alert">Unable to load knowledge.</p>
      </Card>
    );
  if (outlineQuery.isPending || episodeId === null || knowledgeQuery.isPending)
    return (
      <Card>
        <p role="status">Loading knowledge…</p>
      </Card>
    );
  return (
    <Card>
      <div className="section-heading">
        <h2>Knowledge</h2>
        <EpisodeSelect
          id="knowledge-episode"
          label="Episode"
          value={String(episodeId)}
          options={episodes}
          onChange={(value) => setEpisodeId(Number(value))}
        />
      </div>
      {knowledgeQuery.data.length === 0 ? (
        <p>No effective knowledge for this episode.</p>
      ) : (
        <div className="record-list">
          {knowledgeQuery.data.map((item) => (
            <div className="record-list-item" key={item.information_item.id}>
              <span>{item.information_item.statement}</span>
              <small>
                {item.knowledge_state} · episode {item.event_episode_id}
              </small>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function EpisodeSelect({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: EpisodeRecord[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="field-group">
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <select
        id={id}
        className="field-control"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((episode) => (
          <option key={episode.id} value={episode.id}>
            {episode.title}
          </option>
        ))}
      </select>
    </div>
  );
}
function episodeOptions(outline: OutlineView | undefined): EpisodeRecord[] {
  return (
    outline?.chapters.flatMap((chapter) =>
      chapter.episodes.map((item) => item.episode),
    ) ?? []
  );
}
function positiveInteger(value: string): number | null {
  return /^[1-9]\d*$/.test(value) ? Number(value) : null;
}
function emptyCharacterForm(): CharacterFormValues {
  return {
    character_key: "",
    display_name: "",
    entity_type: "human",
    description: "",
    birth_date: "",
    death_date: "",
    physical_description: "",
    occupation: "",
    core_beliefs: "",
    goals: "",
    fears: "",
    personality: "",
    speech_style: "",
    ai_attitude: "",
    genetic_modification_attitude: "",
    private_notes: "",
    profile_json: "{}",
    reason: "",
  };
}
function toCharacterForm(record: CharacterRecord): CharacterFormValues {
  return {
    character_key: record.character_key,
    display_name: record.display_name,
    entity_type: record.entity_type,
    description: record.description,
    birth_date: record.birth_date ?? "",
    death_date: record.death_date ?? "",
    physical_description: record.physical_description,
    occupation: record.occupation,
    core_beliefs: record.core_beliefs,
    goals: record.goals,
    fears: record.fears,
    personality: record.personality,
    speech_style: record.speech_style,
    ai_attitude: record.ai_attitude,
    genetic_modification_attitude: record.genetic_modification_attitude,
    private_notes: record.private_notes,
    profile_json: formatStoredJson(record.profile_json),
    reason: "",
  };
}
function hasCharacterChanges(
  values: CharacterFormValues,
  baseline: CharacterRecord,
): boolean {
  return (
    values.character_key !== baseline.character_key ||
    values.display_name !== baseline.display_name ||
    values.entity_type !== baseline.entity_type ||
    values.description !== baseline.description ||
    values.birth_date !== (baseline.birth_date ?? "") ||
    values.death_date !== (baseline.death_date ?? "") ||
    values.physical_description !== baseline.physical_description ||
    values.occupation !== baseline.occupation ||
    values.core_beliefs !== baseline.core_beliefs ||
    values.goals !== baseline.goals ||
    values.fears !== baseline.fears ||
    values.personality !== baseline.personality ||
    values.speech_style !== baseline.speech_style ||
    values.ai_attitude !== baseline.ai_attitude ||
    values.genetic_modification_attitude !==
      baseline.genetic_modification_attitude ||
    values.private_notes !== baseline.private_notes ||
    jsonChanged(values.profile_json, baseline.profile_json)
  );
}
function buildCharacterUpdate(
  values: CharacterFormValues,
  baseline: CharacterRecord,
): CharacterUpdate | null {
  if (!hasCharacterChanges(values, baseline)) return null;
  for (const [original, current] of [
    [baseline.character_key, values.character_key],
    [baseline.birth_date, values.birth_date],
    [baseline.death_date, values.death_date],
  ] as const)
    if (original !== null && original !== "" && current.trim() === "")
      throw new Error("This field cannot currently be cleared by the API.");
  const update: CharacterUpdate = { expected_version: baseline.version };
  const fields: Array<keyof CharacterFormValues> = [
    "character_key",
    "display_name",
    "entity_type",
    "description",
    "birth_date",
    "death_date",
    "physical_description",
    "occupation",
    "core_beliefs",
    "goals",
    "fears",
    "personality",
    "speech_style",
    "ai_attitude",
    "genetic_modification_attitude",
    "private_notes",
  ];
  for (const field of fields) {
    const baselineValue = baseline[field as keyof CharacterRecord] as
      string | null;
    if (values[field] !== (baselineValue ?? ""))
      (update as unknown as Record<string, unknown>)[field] = values[field];
  }
  if (jsonChanged(values.profile_json, baseline.profile_json))
    update.profile_json = parseJsonEditor(values.profile_json);
  if (values.reason.trim()) update.reason = values.reason.trim();
  return update;
}
function emptyStateForm(): StateFormValues {
  return {
    physical_state: "",
    emotional_state: "",
    beliefs_json: "{}",
    location_world_fact_id: "",
    state_json: "{}",
  };
}
function toStateForm(record: CharacterStateRecord | null): StateFormValues {
  return record === null
    ? emptyStateForm()
    : {
        physical_state: record.physical_state,
        emotional_state: record.emotional_state,
        beliefs_json: formatStoredJson(record.beliefs_json),
        location_world_fact_id:
          record.location_world_fact_id === null
            ? ""
            : String(record.location_world_fact_id),
        state_json: formatStoredJson(record.state_json),
      };
}
function hasStateChanges(
  values: StateFormValues,
  baseline: CharacterStateRecord | null,
): boolean {
  const empty = emptyStateForm();
  return (
    values.physical_state !==
      (baseline?.physical_state ?? empty.physical_state) ||
    values.emotional_state !==
      (baseline?.emotional_state ?? empty.emotional_state) ||
    jsonChanged(
      values.beliefs_json,
      baseline?.beliefs_json ?? empty.beliefs_json,
    ) ||
    values.location_world_fact_id !==
      (baseline?.location_world_fact_id === null ||
      baseline?.location_world_fact_id === undefined
        ? empty.location_world_fact_id
        : String(baseline.location_world_fact_id)) ||
    jsonChanged(values.state_json, baseline?.state_json ?? empty.state_json)
  );
}
function buildStateSet(
  values: StateFormValues,
  baseline: CharacterStateRecord | null,
): CharacterStateSet {
  const input: CharacterStateSet = {
    physical_state: values.physical_state,
    emotional_state: values.emotional_state,
    beliefs_json: parseJsonEditor(values.beliefs_json),
    state_json: parseJsonEditor(values.state_json),
  };
  if (values.location_world_fact_id) {
    const id = positiveInteger(values.location_world_fact_id);
    if (id === null)
      throw new Error("Location world fact ID must be a positive integer.");
    input.location_world_fact_id = id;
  } else if (
    baseline?.location_world_fact_id !== null &&
    baseline?.location_world_fact_id !== undefined
  )
    throw new Error("This field cannot currently be cleared by the API.");
  if (baseline) input.expected_version = baseline.version;
  return input;
}
function jsonChanged(left: string, right: string): boolean {
  try {
    return !jsonValuesEqual(parseJsonEditor(left), JSON.parse(right));
  } catch {
    return true;
  }
}
function jsonValuesEqual(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((value, index) => jsonValuesEqual(value, right[index]))
    );
  }
  if (
    typeof left !== "object" ||
    left === null ||
    typeof right !== "object" ||
    right === null
  )
    return false;
  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const leftKeys = Object.keys(leftRecord);
  const rightKeys = Object.keys(rightRecord);
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key) =>
        Object.prototype.hasOwnProperty.call(rightRecord, key) &&
        jsonValuesEqual(leftRecord[key], rightRecord[key]),
    )
  );
}
function asRecord<T>(value: unknown): T | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as T)
    : null;
}
async function invalidateCharacterFamilies(
  projectId: string,
  queryClient: ReturnType<typeof useQueryClient>,
) {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.charactersFamily(projectId),
    }),
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.characterSearchFamily(projectId),
    }),
    queryClient.invalidateQueries({
      queryKey: projectQueryKeys.episodeViews(projectId),
    }),
  ]);
}
