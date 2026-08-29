import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { projectQueryKeys } from "../../api/queryKeys";
import type {
  CharacterKnowledgeEventRecord,
  EffectiveKnowledgeRecord,
  InformationItemRecord,
  ReaderDisclosureRecord,
} from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { DirtyNavigationGuard } from "../../components/layout/DirtyNavigationGuard";
import { FieldLabel, TextArea, TextInput } from "../../components/ui/Field";
import { AppShell } from "../../components/layout/AppShell";
import { ConflictDialog } from "../conflicts/ConflictDialog";
import { CanonStatusControl } from "../canon/CanonStatusControl";
import { fetchCharacters } from "../characters/characterApi";
import { fetchOutline } from "../structure/structureApi";
import {
  createInformation,
  fetchEffectiveKnowledge,
  fetchExactKnowledge,
  fetchInformation,
  fetchInformationItem,
  fetchReaderDisclosure,
  saveExactKnowledge,
  searchInformation,
  setReaderDisclosure,
  updateInformation,
} from "./informationApi";
import {
  buildInformationCreate,
  buildInformationUpdate,
  emptyInformationForm,
  hasInformationChanges,
  toInformationForm,
  type InformationFormValues,
} from "./informationForms";

const PAGE_SIZE = 50;
type DetailTab = "information" | "disclosure" | "knowledge";

export function InformationPage() {
  const { projectId, informationId } = useParams();
  const project = projectId ?? "";
  const selectedId = informationId === undefined ? null : positiveId(informationId);
  const routeValid = informationId === undefined || selectedId !== null;
  const [searchText, setSearchText] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [records, setRecords] = useState<InformationItemRecord[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const previousProject = useRef(project);
  const browseQuery = useQuery({
    queryKey: projectQueryKeys.information(project, PAGE_SIZE, offset),
    queryFn: () => fetchInformation(project, PAGE_SIZE, offset),
    enabled: routeValid && activeSearch === "",
  });
  const searchQuery = useQuery({
    queryKey: projectQueryKeys.informationSearch(project, activeSearch, PAGE_SIZE),
    queryFn: () => searchInformation(project, activeSearch, PAGE_SIZE),
    enabled: routeValid && activeSearch !== "",
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

  if (informationId !== undefined && selectedId === null)
    return <main className="empty-state"><h1>Page not found</h1><p>Choose a valid information item.</p></main>;
  return (
    <AppShell projectId={project}>
      <div className={selectedId === null ? "entity-layout" : "entity-layout entity-detail-route"}>
        <section className="entity-list-pane">
          <div className="page-heading">
            <div><p className="eyebrow">Information</p><h1>Information</h1></div>
            <Button type="button" onClick={() => setShowCreate((value) => !value)}>Add information</Button>
          </div>
          <form className="entity-search" onSubmit={submitSearch}>
            <FieldLabel htmlFor="information-search">Search information</FieldLabel>
            <div className="search-row">
              <TextInput id="information-search" aria-label="Search information" role="searchbox" value={searchText} onChange={(event) => setSearchText(event.target.value)} />
              <Button type="submit">Search</Button>
              {activeSearch && <Button type="button" variant="secondary" onClick={clearSearch}>Clear</Button>}
            </div>
          </form>
          {showCreate && <InformationCreateForm projectId={project} onCreated={() => setShowCreate(false)} />}
          {(browseQuery.isError || searchQuery.isError) && <p role="alert">Unable to load information.</p>}
          {records.length === 0 && (browseQuery.isPending || searchQuery.isPending) && <p role="status">Loading information…</p>}
          {records.length === 0 && !browseQuery.isPending && !searchQuery.isPending && <p className="empty-state-inline">No information items yet.</p>}
          <div className="record-list">
            {records.map((record) => <Link key={record.id} className="record-list-item" to={`/projects/${encodeURIComponent(project)}/information/${record.id}`}><span><strong>{record.statement}</strong><small>{record.truth_status} · {record.canon_status}</small></span><small>v{record.version}</small></Link>)}
          </div>
          {activeSearch === "" && result?.length === PAGE_SIZE && <Button type="button" variant="secondary" onClick={() => setOffset((value) => value + PAGE_SIZE)}>Load more</Button>}
        </section>
        <section className="entity-detail-pane">
          {selectedId === null ? <Card><p className="eyebrow">Information</p><h2>Select an information item</h2><p>Choose an item to view or edit it.</p></Card> : <InformationDetail key={`${project}-${selectedId}`} projectId={project} informationItemId={selectedId} />}
        </section>
      </div>
    </AppShell>
  );
}

function InformationCreateForm({ projectId, onCreated }: { projectId: string; onCreated: () => void }) {
  const navigate = useNavigate();
  const [values, setValues] = useState<InformationFormValues>(emptyInformationForm());
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const queryClient = useQueryClient();
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const created = await createInformation(projectId, buildInformationCreate(values));
      await invalidateInformationQueries(projectId, queryClient);
      setSaved(true);
      onCreated();
      navigate(`/projects/${encodeURIComponent(projectId)}/information/${created.id}`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to create information."); }
  }
  return <Card><h2>Create information</h2><form onSubmit={(event) => void submit(event)}><InformationFields values={values} setValues={setValues} prefix="create-information" includeReason={false} /><div className="form-actions"><Button type="submit" disabled={saved}>Create information</Button></div></form>{error && <p role="alert">{error}</p>}</Card>;
}

function InformationDetail({ projectId, informationItemId }: { projectId: string; informationItemId: number }) {
  const itemQuery = useQuery({ queryKey: projectQueryKeys.informationItem(projectId, informationItemId), queryFn: () => fetchInformationItem(projectId, informationItemId), staleTime: 10_000, retry: false });
  const [tab, setTab] = useState<DetailTab>("information");
  const [dirty, setDirty] = useState(false);
  if (itemQuery.isError) return <p role="alert">Unable to load the information item.</p>;
  if (itemQuery.isPending || !itemQuery.data) return <p role="status">Loading information item…</p>;
  const item = itemQuery.data;
  function changeTab(next: DetailTab) {
    if (next === tab) return;
    if (dirty && !window.confirm("Discard unsaved information edits?")) return;
    setDirty(false);
    setTab(next);
  }
  return <>
    <Link className="back-link" to={`/projects/${encodeURIComponent(projectId)}/information`}>Back to information</Link>
    <div className="detail-heading"><div><p className="eyebrow">Information item</p><h1>{item.statement}</h1></div><span className="version-note">Version {item.version}</span></div>
    <div className="detail-tabs" role="tablist">
      {(["information", "disclosure", "knowledge"] as DetailTab[]).map((value) => <button key={value} type="button" role="tab" aria-selected={tab === value} className={tab === value ? "detail-tab active" : "detail-tab"} onClick={() => changeTab(value)}>{value === "information" ? "Information" : value === "disclosure" ? "Reader Disclosure" : "Knowledge"}</button>)}
    </div>
    {tab === "information" && <InformationEditor projectId={projectId} informationItemId={informationItemId} initial={item} onDirtyChange={setDirty} />}
    {tab === "disclosure" && <ReaderDisclosurePanel projectId={projectId} item={item} onDirtyChange={setDirty} />}
    {tab === "knowledge" && <KnowledgePanel projectId={projectId} item={item} onDirtyChange={setDirty} />}
    <DirtyNavigationGuard dirty={dirty} />
  </>;
}

function InformationEditor({ projectId, informationItemId, initial, onDirtyChange }: { projectId: string; informationItemId: number; initial: InformationItemRecord; onDirtyChange: (dirty: boolean) => void }) {
  const queryClient = useQueryClient();
  const [baseline, setBaseline] = useState(initial);
  const [values, setValues] = useState(toInformationForm(initial));
  const [error, setError] = useState<string | null>(null);
  const [conflictError, setConflictError] = useState<string | null>(null);
  const [latest, setLatest] = useState<InformationItemRecord | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const dirty = hasInformationChanges(values, baseline);
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  async function save() {
    setError(null); setSaved(false);
    try {
      const update = buildInformationUpdate(values, baseline);
      if (!update) { if (values.reason.trim()) setError("A reason alone does not require Save."); return; }
      const updated = await updateInformation(projectId, informationItemId, update);
      queryClient.setQueryData(projectQueryKeys.informationItem(projectId, informationItemId), updated);
      await invalidateInformationQueries(projectId, queryClient);
      setBaseline(updated); setValues(toInformationForm(updated)); setLatest(null); setConflictOpen(false); setSaved(true);
    } catch (caught) {
      if (isApiError(caught) && caught.status === 409 && caught.code === "VERSION_CONFLICT") {
        setConflictOpen(true);
        const current = asRecord<InformationItemRecord>(caught.details.current_resource);
        if (current) { setLatest(current); queryClient.setQueryData(projectQueryKeys.informationItem(projectId, informationItemId), current); }
        else { try { const fetched = await fetchInformationItem(projectId, informationItemId); setLatest(fetched); queryClient.setQueryData(projectQueryKeys.informationItem(projectId, informationItemId), fetched); } catch { setConflictError("The latest information item could not be loaded. Your local edits were kept."); } }
        return;
      }
      setError(caught instanceof Error ? caught.message : "Unable to save information.");
    }
  }
  async function loadLatest() {
    try { const fetched = await fetchInformationItem(projectId, informationItemId); queryClient.setQueryData(projectQueryKeys.informationItem(projectId, informationItemId), fetched); setBaseline(fetched); setValues(toInformationForm(fetched)); setLatest(null); setConflictOpen(false); setConflictError(null); setSaved(false); } catch { setConflictOpen(true); setConflictError("The latest information item could not be loaded. Your local edits were kept."); }
  }
  return <>
    <Card><InformationFields values={values} setValues={setValues} prefix="edit-information" includeReason /><div className="read-only-meta">Version {baseline.version} · Canon status {baseline.canon_status}</div>{error && <p role="alert">{error}</p>}<div className="form-actions"><Button type="button" onClick={() => void save()}>Save changes</Button>{dirty && <span className="dirty-indicator">Unsaved changes</span>}{!dirty && saved && <span className="saved-indicator">Saved</span>}</div></Card>
    <CanonStatusControl projectId={projectId} entityType="information_item" record={baseline} dirty={dirty} onStatusChanged={async () => { const fetched = await fetchInformationItem(projectId, informationItemId); queryClient.setQueryData(projectQueryKeys.informationItem(projectId, informationItemId), fetched); setBaseline(fetched); setValues(toInformationForm(fetched)); }} onLoadLatest={(latest) => { const fetched = latest as InformationItemRecord; queryClient.setQueryData(projectQueryKeys.informationItem(projectId, informationItemId), fetched); setBaseline(fetched); setValues(toInformationForm(fetched)); }} readCurrent={() => fetchInformationItem(projectId, informationItemId)} />
    {conflictOpen && <ConflictDialog local={values} latest={latest} entityLabel="information item" onDiscard={() => void loadLatest()} onKeep={() => { setLatest(null); setConflictOpen(false); setConflictError(null); }} errorMessage={conflictError} />}
  </>;
}

function ReaderDisclosurePanel({ projectId, item, onDirtyChange }: { projectId: string; item: InformationItemRecord; onDirtyChange: (dirty: boolean) => void }) {
  const queryClient = useQueryClient();
  const outlineQuery = useQuery({ queryKey: projectQueryKeys.outline(projectId), queryFn: () => fetchOutline(projectId), retry: false });
  const disclosureQuery = useQuery({ queryKey: projectQueryKeys.readerDisclosure(projectId, item.id), queryFn: () => fetchReaderDisclosure(projectId, item.id), retry: false, staleTime: 10_000 });
  const [baseline, setBaseline] = useState<ReaderDisclosureRecord | null | undefined>(undefined);
  const [selectedEpisode, setSelectedEpisode] = useState("");
  const [latest, setLatest] = useState<ReaderDisclosureRecord | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const episodes = episodeOptions(outlineQuery.data);
  const dirty = baseline !== undefined && selectedEpisode !== String(baseline?.episode_id ?? "");
  useEffect(() => { if (disclosureQuery.isSuccess && !dirty) { setBaseline(disclosureQuery.data); setSelectedEpisode(disclosureQuery.data ? String(disclosureQuery.data.episode_id) : ""); } }, [disclosureQuery.data, disclosureQuery.isSuccess, dirty]);
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  function selectEpisode(value: string) { if (dirty && !window.confirm("Discard unsaved disclosure edits?")) return; setSelectedEpisode(value); }
  async function save() {
    const episodeId = positiveId(selectedEpisode); if (episodeId === null) return;
    if (baseline && episodeId === baseline.episode_id) return;
    const body = baseline ? { episode_id: episodeId, expected_version: baseline.version } : { episode_id: episodeId };
    try { const saved = await setReaderDisclosure(projectId, item.id, body); queryClient.setQueryData(projectQueryKeys.readerDisclosure(projectId, item.id), saved); setBaseline(saved); setSelectedEpisode(String(saved.episode_id)); setLatest(null); setConflictOpen(false); setError(null); await queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) }); } catch (caught) { if (isApiError(caught) && caught.status === 409 && caught.code === "VERSION_CONFLICT") { setConflictOpen(true); const current = asRecord<ReaderDisclosureRecord>(caught.details.current_resource); if (current) setLatest(current); else { try { setLatest(await fetchReaderDisclosure(projectId, item.id)); } catch { setError("The latest disclosure could not be loaded. Your local selection was kept."); } } return; } setError(caught instanceof Error ? caught.message : "Unable to save disclosure."); }
  }
  async function loadLatest() { try { const current = await fetchReaderDisclosure(projectId, item.id); queryClient.setQueryData(projectQueryKeys.readerDisclosure(projectId, item.id), current); setBaseline(current); setSelectedEpisode(current ? String(current.episode_id) : ""); setLatest(null); setConflictOpen(false); setError(null); } catch { setConflictOpen(true); setError("The latest disclosure could not be loaded. Your local selection was kept."); } }
  if (outlineQuery.isError || disclosureQuery.isError) return <Card><p role="alert">Unable to load reader disclosure.</p></Card>;
  if (outlineQuery.isPending || disclosureQuery.isPending || baseline === undefined) return <Card><p role="status">Loading reader disclosure…</p></Card>;
  return <><Card><h2>Reader Disclosure</h2>{baseline === null && <p>No disclosure set.</p>}<div className="field-group"><FieldLabel htmlFor="disclosure-episode">Disclosure episode</FieldLabel><select id="disclosure-episode" className="field-control" value={selectedEpisode} onChange={(event) => selectEpisode(event.target.value)}><option value="">Select an episode</option>{episodes.map((episode) => <option key={episode.id} value={episode.id}>{episode.title}</option>)}</select></div>{error && <p role="alert">{error}</p>}<div className="form-actions"><Button type="button" onClick={() => void save()} disabled={!selectedEpisode || !dirty}>Save disclosure</Button>{dirty && <span className="dirty-indicator">Unsaved changes</span>}</div></Card>{conflictOpen && <ConflictDialog local={{ episode_id: selectedEpisode }} latest={latest} entityLabel="reader disclosure" onDiscard={() => void loadLatest()} onKeep={() => { setLatest(null); setConflictOpen(false); setError(null); }} errorMessage={error} />}</>;
}

function KnowledgePanel({ projectId, item, onDirtyChange }: { projectId: string; item: InformationItemRecord; onDirtyChange: (dirty: boolean) => void }) {
  const queryClient = useQueryClient();
  const outlineQuery = useQuery({ queryKey: projectQueryKeys.outline(projectId), queryFn: () => fetchOutline(projectId), retry: false });
  const charactersQuery = useQuery({ queryKey: projectQueryKeys.characters(projectId, 100, 0), queryFn: () => fetchCharacters(projectId, 100, 0), retry: false });
  const episodes = episodeOptions(outlineQuery.data);
  const [characterId, setCharacterId] = useState<number | null>(null);
  const [episodeId, setEpisodeId] = useState<number | null>(null);
  const [baseline, setBaseline] = useState<CharacterKnowledgeEventRecord | null | undefined>(undefined);
  const [state, setState] = useState("");
  const [note, setNote] = useState("");
  const [latest, setLatest] = useState<CharacterKnowledgeEventRecord | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (characterId === null && charactersQuery.data?.[0]) setCharacterId(charactersQuery.data[0].id); if (episodeId === null && episodes[0]) setEpisodeId(episodes[0].id); }, [characterId, charactersQuery.data, episodeId, episodes]);
  const exactQuery = useQuery({ queryKey: projectQueryKeys.characterKnowledgeExact(projectId, characterId ?? 0, item.id, episodeId ?? 0), queryFn: () => fetchExactKnowledge(projectId, characterId ?? 0, item.id, episodeId ?? 0), enabled: characterId !== null && episodeId !== null, retry: false, staleTime: 10_000 });
  const effectiveQuery = useQuery({ queryKey: projectQueryKeys.characterKnowledge(projectId, characterId ?? 0, episodeId ?? 0), queryFn: () => fetchEffectiveKnowledge(projectId, characterId ?? 0, episodeId ?? 0), enabled: characterId !== null && episodeId !== null, retry: false });
  const dirty = baseline !== undefined && (state !== (baseline?.knowledge_state ?? "") || note !== (baseline?.note ?? ""));
  useEffect(() => { if (exactQuery.isSuccess && !dirty) { setBaseline(exactQuery.data); setState(exactQuery.data?.knowledge_state ?? ""); setNote(exactQuery.data?.note ?? ""); setSaved(false); } }, [dirty, exactQuery.data, exactQuery.isSuccess]);
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  function switchSelection(nextCharacterId: number | null, nextEpisodeId: number | null) { if (dirty && !window.confirm("Discard unsaved knowledge edits?")) return; setBaseline(undefined); setState(""); setNote(""); setCharacterId(nextCharacterId); setEpisodeId(nextEpisodeId); }
  async function save() { if (characterId === null || episodeId === null || !state) { setError("Select a knowledge state before saving."); return; } try { const input: import("../../api/types").CharacterKnowledgeSet = { episode_id: episodeId, knowledge_state: state, note }; if (baseline) input.expected_version = baseline.version; const savedEvent = await saveExactKnowledge(projectId, characterId, item.id, input); queryClient.setQueryData(projectQueryKeys.characterKnowledgeExact(projectId, characterId, item.id, episodeId), savedEvent); setBaseline(savedEvent); setState(savedEvent.knowledge_state); setNote(savedEvent.note); setLatest(null); setConflictOpen(false); setError(null); setSaved(true); await Promise.all([queryClient.invalidateQueries({ queryKey: projectQueryKeys.characterKnowledgeFamily(projectId, characterId) }), queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) })]); } catch (caught) { if (isApiError(caught) && caught.status === 409 && caught.code === "VERSION_CONFLICT") { setConflictOpen(true); const current = asRecord<CharacterKnowledgeEventRecord>(caught.details.current_resource); if (current) setLatest(current); else { try { setLatest(await fetchExactKnowledge(projectId, characterId, item.id, episodeId)); } catch { setError("The latest knowledge event could not be loaded. Your local edits were kept."); } } return; } setError(caught instanceof Error ? caught.message : "Unable to save knowledge."); } }
  async function loadLatest() { if (characterId === null || episodeId === null) return; try { const current = await fetchExactKnowledge(projectId, characterId, item.id, episodeId); queryClient.setQueryData(projectQueryKeys.characterKnowledgeExact(projectId, characterId, item.id, episodeId), current); setBaseline(current); setState(current?.knowledge_state ?? ""); setNote(current?.note ?? ""); setLatest(null); setConflictOpen(false); setError(null); await Promise.all([queryClient.invalidateQueries({ queryKey: projectQueryKeys.characterKnowledgeFamily(projectId, characterId) }), queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) })]); } catch { setConflictOpen(true); setError("The latest knowledge event could not be loaded. Your local edits were kept."); } }
  const effective = (effectiveQuery.data ?? []).find((record) => record.information_item.id === item.id) as EffectiveKnowledgeRecord | undefined;
  if (outlineQuery.isError || charactersQuery.isError || exactQuery.isError || effectiveQuery.isError) return <Card><p role="alert">Unable to load knowledge.</p></Card>;
  if (outlineQuery.isPending || charactersQuery.isPending || characterId === null || episodeId === null || exactQuery.isPending || effectiveQuery.isPending || baseline === undefined) return <Card><p role="status">Loading knowledge…</p></Card>;
  return <><Card><h2>Character Knowledge</h2><div className="reference-form"><div className="field-group"><FieldLabel htmlFor="knowledge-character">Character</FieldLabel><select id="knowledge-character" className="field-control" value={characterId} onChange={(event) => switchSelection(positiveId(event.target.value), episodeId)}>{(charactersQuery.data ?? []).map((character) => <option key={character.id} value={character.id}>{character.display_name}</option>)}</select></div><div className="field-group"><FieldLabel htmlFor="knowledge-episode">Episode</FieldLabel><select id="knowledge-episode" className="field-control" value={episodeId} onChange={(event) => switchSelection(characterId, positiveId(event.target.value))}>{episodes.map((episode) => <option key={episode.id} value={episode.id}>{episode.title}</option>)}</select></div></div>{effective && <div className="read-only-meta">Effective state: {effective.knowledge_state} · source episode {effective.event_episode_id} · event version {effective.event_version}</div>}{!effective && <p className="read-only-meta">No effective knowledge for this episode.</p>}{baseline === null && <p className="helper-text">No event at the selected episode. Effective state is read-only context; choose a state to create an event.</p>}<div className="field-group"><FieldLabel htmlFor="knowledge-state">Knowledge state</FieldLabel><select id="knowledge-state" className="field-control" value={state} onChange={(event) => setState(event.target.value)}><option value="">Select state</option>{["suspects", "believes", "knows", "confirmed", "doubts", "rejected"].map((value) => <option key={value} value={value}>{value}</option>)}</select></div><div className="field-group"><FieldLabel htmlFor="knowledge-note">Note</FieldLabel><TextArea id="knowledge-note" value={note} onChange={(event) => setNote(event.target.value)} rows={3} /></div>{error && <p role="alert">{error}</p>}<div className="form-actions"><Button type="button" onClick={() => void save()} disabled={!dirty || !state}>Save knowledge</Button>{dirty && <span className="dirty-indicator">Unsaved changes</span>}{saved && <span className="saved-indicator">Saved</span>}</div></Card>{conflictOpen && <ConflictDialog local={{ knowledge_state: state, note }} latest={latest} entityLabel="knowledge event" onDiscard={() => void loadLatest()} onKeep={() => { setLatest(null); setConflictOpen(false); setError(null); }} errorMessage={error} />}</>;
}

function InformationFields({ values, setValues, prefix, includeReason }: { values: InformationFormValues; setValues: (values: InformationFormValues) => void; prefix: string; includeReason: boolean }) {
  const update = (field: keyof InformationFormValues, value: string) => setValues({ ...values, [field]: value });
  return <div className="editor-form"><div className="field-group field-span"><FieldLabel htmlFor={`${prefix}-statement`}>Statement</FieldLabel><TextArea id={`${prefix}-statement`} required value={values.statement} onChange={(event) => update("statement", event.target.value)} rows={3} /></div><div className="field-group"><FieldLabel htmlFor={`${prefix}-truth-status`}>Truth status</FieldLabel><select id={`${prefix}-truth-status`} className="field-control" value={values.truth_status} onChange={(event) => update("truth_status", event.target.value)}>{["true", "false", "uncertain", "subjective"].map((value) => <option key={value} value={value}>{value}</option>)}</select></div><div className="field-group"><FieldLabel htmlFor={`${prefix}-canon-status`}>Canon status</FieldLabel><select id={`${prefix}-canon-status`} className="field-control" value={values.canon_status} onChange={(event) => update("canon_status", event.target.value)}>{["idea", "draft", "canon", "deprecated"].map((value) => <option key={value} value={value}>{value}</option>)}</select></div><div className="field-group"><FieldLabel htmlFor={`${prefix}-importance`}>Importance</FieldLabel><TextInput id={`${prefix}-importance`} type="number" min="0" step="1" value={values.importance} onChange={(event) => update("importance", event.target.value)} /></div><div className="field-group"><FieldLabel htmlFor={`${prefix}-authoring-guard`}>Authoring guard</FieldLabel><TextInput id={`${prefix}-authoring-guard`} value={values.authoring_guard} onChange={(event) => update("authoring_guard", event.target.value)} /></div><div className="field-group field-span"><FieldLabel htmlFor={`${prefix}-notes-json`}>Notes JSON</FieldLabel><TextArea id={`${prefix}-notes-json`} value={values.notes_json} onChange={(event) => update("notes_json", event.target.value)} rows={6} /></div>{includeReason && <div className="field-group field-span"><FieldLabel htmlFor={`${prefix}-reason`}>Reason (optional)</FieldLabel><TextInput id={`${prefix}-reason`} value={values.reason} onChange={(event) => update("reason", event.target.value)} /></div>}</div>;
}

function episodeOptions(outline: import("../../api/types").OutlineView | undefined) { return outline?.chapters.flatMap((chapter) => chapter.episodes.map((entry) => entry.episode)) ?? []; }
function positiveId(value: string): number | null { return /^[1-9]\d*$/.test(value) ? Number(value) : null; }
function asRecord<T>(value: unknown): T | null { return typeof value === "object" && value !== null && !Array.isArray(value) ? value as T : null; }
async function invalidateInformationQueries(projectId: string, queryClient: ReturnType<typeof useQueryClient>) { await Promise.all([queryClient.invalidateQueries({ queryKey: projectQueryKeys.informationFamily(projectId) }), queryClient.invalidateQueries({ queryKey: projectQueryKeys.informationSearchFamily(projectId) }), queryClient.invalidateQueries({ queryKey: projectQueryKeys.canonDecisionsFamily(projectId) }), queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) })]); }
