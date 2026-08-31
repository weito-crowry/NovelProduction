import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { projectQueryKeys } from "../../api/queryKeys";
import type {
  CharacterRecord,
  DraftDocumentRead,
  DraftExport,
  DraftHistoryItem,
  DraftSaveResult,
  DraftWebRead,
  ExportWarning,
  JsonValue,
  NovelBlock,
  OutlineView,
  SceneRecord,
} from "../../api/types";
import { AppShell } from "../../components/layout/AppShell";
import { DirtyNavigationGuard } from "../../components/layout/DirtyNavigationGuard";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { useModalFocus } from "../../components/ui/useModalFocus";
import { ConflictDialog } from "../conflicts/ConflictDialog";
import {
  fetchAllCharacters,
  fetchDraftAuthoringHtml,
  fetchDraftDocument,
  fetchDraftHistory,
  fetchDraftWeb,
  fetchFreshLatestDocument,
  fetchNarouExport,
  restoreDraft,
  saveDraftHtml,
} from "./manuscriptApi";
import { ManuscriptEditor } from "./ManuscriptEditor";
import {
  assertDocumentIdentity,
  assertHtmlIdentity,
  asDraftHtmlPreview,
  assertWebIdentity,
  isFormalBlockId,
  projectableUnknownAnnotations,
  reconcileLatestObservation,
  restoreRefreshStatus,
} from "./manuscriptRead";
import { fetchOutline } from "../structure/structureApi";

export function ManuscriptPage() {
  const { projectId, episodeId } = useParams();
  const project = projectId ?? "";
  const selectedId = episodeId === undefined ? null : positiveId(episodeId);
  const routeValid = episodeId === undefined || selectedId !== null;
  const outlineQuery = useQuery({
    queryKey: projectQueryKeys.outline(project),
    queryFn: () => fetchOutline(project),
    enabled: routeValid,
    retry: false,
  });

  if (!routeValid) {
    return <main className="empty-state"><h1>Page not found</h1><p>Choose a valid episode.</p></main>;
  }
  return (
    <AppShell projectId={project}>
      <div className={selectedId === null ? "entity-layout" : "entity-layout entity-detail-route"}>
        <section className="entity-list-pane">
          <div className="page-heading">
            <div><p className="eyebrow">Manuscript</p><h1>Manuscript</h1></div>
          </div>
          {outlineQuery.isError && <p role="alert">Unable to load the outline.</p>}
          {outlineQuery.isPending && <p role="status">Loading episodes…</p>}
          {outlineQuery.data && <EpisodeList projectId={project} outline={outlineQuery.data} selectedId={selectedId} />}
        </section>
        <section className="entity-detail-pane">
          {selectedId === null ? (
            <Card><p className="eyebrow">Manuscript</p><h2>Select an episode</h2><p>Choose an episode to read its structured manuscript.</p></Card>
          ) : (
            <ManuscriptReader
              key={`${project}-${selectedId}`}
              projectId={project}
              episodeId={selectedId}
              scenes={outlineQuery.data?.chapters.flatMap((chapter) => chapter.episodes).find((entry) => entry.episode.id === selectedId)?.scenes ?? []}
              scenesLoading={outlineQuery.isPending}
              scenesError={outlineQuery.isError ? "Unable to load scenes. Existing scene references were kept." : null}
            />
          )}
        </section>
      </div>
    </AppShell>
  );
}

function EpisodeList({
  projectId,
  outline,
  selectedId,
}: {
  projectId: string;
  outline: OutlineView;
  selectedId: number | null;
}) {
  const episodes = outline.chapters.flatMap((chapter) =>
    chapter.episodes.map((entry) => ({ ...entry.episode, chapterTitle: chapter.chapter.title })),
  );
  if (episodes.length === 0) return <p className="empty-state-inline">No episodes yet.</p>;
  return (
    <div className="record-list">
      {episodes.map((episode) => (
        <Link
          className={episode.id === selectedId ? "record-list-item active" : "record-list-item"}
          key={episode.id}
          to={`/projects/${encodeURIComponent(projectId)}/manuscript/${episode.id}`}
        >
          <span><strong>{episode.title}</strong><small>{episode.chapterTitle} · {episode.production_status}</small></span>
          <small>#{episode.position}</small>
        </Link>
      ))}
    </div>
  );
}

function ManuscriptReader({
  projectId,
  episodeId,
  scenes,
  scenesLoading,
  scenesError,
}: {
  projectId: string;
  episodeId: number;
  scenes: SceneRecord[];
  scenesLoading: boolean;
  scenesError: string | null;
}) {
  const queryClient = useQueryClient();
  const [selectedRevision, setSelectedRevision] = useState<number | null>(null);
  const [includeNotes, setIncludeNotes] = useState(false);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [rawDocumentOpen, setRawDocumentOpen] = useState(false);
  const [rawAnnotationsOpen, setRawAnnotationsOpen] = useState(false);
  const [restoreRevision, setRestoreRevision] = useState<number | null>(null);
  const [restorePending, setRestorePending] = useState(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [restoreSuccess, setRestoreSuccess] = useState<DraftSaveResult | null>(null);
  const [postRefreshError, setPostRefreshError] = useState<string | null>(null);
  const [committedRestore, setCommittedRestore] = useState<CommittedRestore | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportWarnings, setExportWarnings] = useState<ExportWarning[]>([]);
  const [editSession, setEditSession] = useState<EditSession | null>(null);
  const [editPending, setEditPending] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editDirty, setEditDirty] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editConflict, setEditConflict] = useState<EditConflict | null>(null);
  const [discardDialogOpen, setDiscardDialogOpen] = useState(false);
  const [discardPending, setDiscardPending] = useState(false);
  const [committedSave, setCommittedSave] = useState<CommittedSave | null>(null);
  const [committedSaveError, setCommittedSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<DraftSaveResult | null>(null);
  const [committedSaveRefreshPending, setCommittedSaveRefreshPending] = useState(false);
  const committedSaveRefreshInFlight = useRef(false);
  const saveInFlight = useRef(false);
  const cancelRefreshInFlight = useRef(false);
  const [conflictReloadPending, setConflictReloadPending] = useState(false);
  const conflictReloadInFlight = useRef(false);

  const documentKey = projectQueryKeys.draftDocument(projectId, episodeId, selectedRevision ?? "latest");
  const documentQuery = useQuery({
    queryKey: documentKey,
    queryFn: async () => {
      const read = selectedRevision === null
        ? await fetchFreshLatestDocument(projectId, episodeId)
        : await fetchDraftDocument(projectId, episodeId, selectedRevision);
      if (read === null) {
        if (selectedRevision !== null) throw new Error("The selected manuscript revision could not be loaded.");
        return null;
      }
      return assertDocumentIdentity(read, episodeId, selectedRevision ?? undefined);
    },
    retry: false,
    staleTime: selectedRevision === null ? 10_000 : Infinity,
    refetchOnMount: selectedRevision === null ? "always" : false,
    structuralSharing: selectedRevision === null
      ? (previous, incoming) => safeReconcileLatestObservation(
        previous as DraftDocumentRead | null | undefined,
        incoming as DraftDocumentRead | null | undefined,
      )
      : undefined,
  });
  const documentRead = documentQuery.data ?? null;
  const displayRevision = documentRead?.revision ?? null;
  const historyQuery = useQuery({
    queryKey: projectQueryKeys.draftHistory(projectId, episodeId),
    queryFn: () => fetchDraftHistory(projectId, episodeId),
    retry: false,
  });
  const charactersQuery = useQuery<CharacterRecord[]>({
    queryKey: projectQueryKeys.charactersAll(projectId),
    queryFn: () => fetchAllCharacters(projectId),
    enabled: editSession !== null || editPending,
    retry: false,
  });
  const webQuery = useQuery({
    queryKey: projectQueryKeys.draftWeb(projectId, episodeId, displayRevision ?? 0, includeNotes),
    queryFn: async () => {
      if (documentRead === null || displayRevision === null) throw new Error("A manuscript document is required before its WEB projection.");
      return assertWebIdentity(await fetchDraftWeb(projectId, episodeId, displayRevision, includeNotes), documentRead);
    },
    enabled: documentRead !== null && displayRevision !== null,
    retry: false,
    staleTime: Infinity,
  });
  const visibleBlocks = documentRead?.content.blocks.filter((block) => includeNotes || block.type !== "note") ?? [];
  const selectedBlock = visibleBlocks.find((block) => block.id === selectedBlockId) ?? null;

  async function beginEdit() {
    if (editPending || committedRestore !== null || committedSave !== null) return;
    setEditPending(true);
    setEditError(null);
    setEditConflict(null);
    setSaveSuccess(null);
    try {
      const latest = await getFreshDocument(projectId, episodeId);
      const adopted = setLatestDocument(queryClient, projectId, episodeId, latest);
      if (adopted === null) {
        setEditSession({ key: Date.now(), baselineDocument: null, baselineDraftId: null, initialHtml: "" });
      } else {
        const html = await getMatchingAuthoringHtml(projectId, episodeId, adopted);
        setSelectedRevision(null);
        setEditSession({ key: Date.now(), baselineDocument: adopted, baselineDraftId: adopted.id, initialHtml: html.content });
      }
      setEditDirty(false);
    } catch (caught) {
      setEditError(caught instanceof Error ? caught.message : "Unable to start manuscript editing.");
    } finally {
      setEditPending(false);
    }
  }

  async function saveEditedHtml(html: string) {
    if (saveInFlight.current || discardDialogOpen || cancelRefreshInFlight.current) return;
    const session = editSession;
    if (session === null || editSaving) return;
    saveInFlight.current = true;
    setEditSaving(true);
    setEditError(null);
    try {
      if (session.baselineDocument === null) {
        const latest = setLatestDocument(queryClient, projectId, episodeId, await getFreshDocument(projectId, episodeId));
        if (latest !== null) {
          setEditConflict({ localHtml: html, latest, initial: true });
          return;
        }
      }
      const saved = await saveDraftHtml(projectId, episodeId, {
        html,
        ...(session.baselineDraftId === null ? {} : { expected_parent_draft_id: session.baselineDraftId }),
        source_agent: "webui",
        change_summary: session.baselineDraftId === null ? "Create manuscript" : "Edit manuscript",
      });
      assertSaveResult(saved);
      const committed: CommittedSave = { createdRevision: saved.revision, createdDraftId: saved.id };
      setSaveSuccess(saved);
      setEditSession(null);
      setEditDirty(false);
      setCommittedSave(committed);
      setCommittedSaveError(null);
      await confirmCommittedSave(committed);
    } catch (caught) {
      if (isApiError(caught) && caught.status === 409 && caught.code === "VERSION_CONFLICT") {
        setEditConflict({ localHtml: html, latest: asDraftHtmlPreview(caught.details.current_resource), initial: false });
      } else {
        setEditError(caught instanceof Error ? caught.message : "Unable to save the manuscript.");
      }
    } finally {
      saveInFlight.current = false;
      setEditSaving(false);
    }
  }

  async function loadLatestIntoEditor() {
    if (conflictReloadInFlight.current) return;
    conflictReloadInFlight.current = true;
    setConflictReloadPending(true);
    setEditError(null);
    try {
      const latest = await getFreshDocument(projectId, episodeId);
      const adopted = setLatestDocument(queryClient, projectId, episodeId, latest);
      if (adopted === null) {
        setEditSession({ key: Date.now(), baselineDocument: null, baselineDraftId: null, initialHtml: "" });
      } else {
        const html = await getMatchingAuthoringHtml(projectId, episodeId, adopted);
        setEditSession({ key: Date.now(), baselineDocument: adopted, baselineDraftId: adopted.id, initialHtml: html.content });
      }
      setEditDirty(false);
      setEditConflict(null);
      setEditError(null);
    } catch (caught) {
      setEditError(caught instanceof Error ? caught.message : "The latest manuscript could not be loaded. Your local edits were kept.");
    } finally {
      conflictReloadInFlight.current = false;
      setConflictReloadPending(false);
    }
  }

  async function cancelEditing() {
    if (cancelRefreshInFlight.current) return;
    cancelRefreshInFlight.current = true;
    setDiscardPending(true);
    setEditError(null);
    try {
      const latest = await getFreshDocument(projectId, episodeId);
      setLatestDocument(queryClient, projectId, episodeId, latest);
      await invalidateAfterSave(queryClient, projectId, episodeId);
      setEditSession(null);
      setEditDirty(false);
      setDiscardDialogOpen(false);
      setEditConflict(null);
      setSelectedRevision(null);
    } catch (caught) {
      setEditError(caught instanceof Error ? caught.message : "The latest manuscript could not be loaded. Your local edits were kept.");
    } finally {
      cancelRefreshInFlight.current = false;
      setDiscardPending(false);
    }
  }

  function keepLocalConflict() {
    if (conflictReloadInFlight.current) return;
    setEditConflict(null);
  }

  async function confirmCommittedSave(committed: CommittedSave) {
    if (committedSaveRefreshInFlight.current) return;
    committedSaveRefreshInFlight.current = true;
    setCommittedSaveRefreshPending(true);
    setCommittedSaveError(null);
    try {
      const actualLatest = setLatestDocument(queryClient, projectId, episodeId, await getFreshDocument(projectId, episodeId));
      if (actualLatest === null || restoreRefreshStatus(actualLatest, { revision: committed.createdRevision, id: committed.createdDraftId }) !== "confirmed") {
        setCommittedSaveError(saveRefreshMessage(committed.createdRevision));
        return;
      }
      await invalidateAfterSave(queryClient, projectId, episodeId);
      setSelectedRevision(null);
      setSelectedBlockId(null);
      setCommittedSave(null);
      setCommittedSaveError(null);
    } catch {
      setCommittedSaveError(saveRefreshMessage(committed.createdRevision));
    } finally {
      committedSaveRefreshInFlight.current = false;
      setCommittedSaveRefreshPending(false);
    }
  }

  async function reloadCommittedSave() {
    if (committedSave === null) return;
    await confirmCommittedSave(committedSave);
  }

  useEffect(() => {
    setSelectedBlockId(null);
    setRawAnnotationsOpen(false);
    setExportWarnings([]);
  }, [episodeId, displayRevision]);

  useEffect(() => {
    if (
      !includeNotes &&
      selectedBlockId !== null &&
      documentRead?.content.blocks.some((block) => block.id === selectedBlockId && block.type === "note")
    ) {
      setSelectedBlockId(null);
    }
  }, [documentRead, includeNotes, selectedBlockId]);

  function selectHistoricalRevision(revision: number) {
    setRestoreError(null);
    setPostRefreshError(null);
    setSelectedRevision(revision);
  }

  async function viewLatest() {
    if (editSession !== null || editPending) return;
    if (committedSave !== null) {
      await reloadCommittedSave();
      return;
    }
    setRestoreError(null);
    setPostRefreshError(null);
    try {
      const latest = setLatestDocument(queryClient, projectId, episodeId, await getFreshDocument(projectId, episodeId));
      if (latest === null) throw new Error("No latest manuscript draft is available.");
      if (committedRestore !== null) {
        const status = restoreRefreshStatus(latest, { revision: committedRestore.createdRevision, id: committedRestore.createdDraftId });
        if (status !== "confirmed") {
          setPostRefreshError(refreshMessage(committedRestore.createdRevision));
          return;
        }
        setCommittedRestore(null);
      }
      setSelectedRevision(null);
      setSelectedBlockId(null);
    } catch (caught) {
      setRestoreError(caught instanceof Error ? caught.message : "Unable to load the latest manuscript.");
    }
  }

  async function confirmRestore() {
    const sourceRevision = restoreRevision;
    if (sourceRevision === null || selectedRevision !== sourceRevision || committedRestore !== null) return;
    setRestorePending(true);
    setRestoreError(null);
    setPostRefreshError(null);
    try {
      const freshLatest = setLatestDocument(queryClient, projectId, episodeId, await getFreshDocument(projectId, episodeId));
      if (freshLatest === null) throw new Error("Restore cannot proceed because there is no current manuscript revision.");
      if (freshLatest.revision === sourceRevision) {
        setRestoreRevision(null);
        setSelectedRevision(null);
        setSelectedBlockId(null);
        return;
      }
      if (freshLatest.revision < sourceRevision) {
        throw new Error("Restore cannot proceed because the latest manuscript revision is inconsistent.");
      }
      const saved = await restoreDraft(projectId, episodeId, {
        restore_revision: sourceRevision,
        expected_parent_draft_id: freshLatest.id,
        source_agent: "webui",
        change_summary: `Restore revision ${sourceRevision}`,
      });
      assertSaveResult(saved);
      const committed: CommittedRestore = {
        sourceRevision,
        createdRevision: saved.revision,
        createdDraftId: saved.id,
      };
      setCommittedRestore(committed);
      setRestoreSuccess(saved);
      setRestoreRevision(null);
      await refreshAfterRestore(committed);
    } catch (caught) {
      if (isApiError(caught) && caught.status === 409 && caught.code === "VERSION_CONFLICT") {
        setRestoreError("Restore conflict: the manuscript changed before the restore could be appended.");
        await refreshHistory(queryClient, projectId, episodeId);
      } else if (caught instanceof Error) {
        setRestoreError(caught.message);
      } else {
        setRestoreError("Unable to restore the manuscript revision.");
      }
    } finally {
      setRestorePending(false);
    }
  }

  async function refreshAfterRestore(committed: CommittedRestore) {
    try {
      const actualLatest = setLatestDocument(queryClient, projectId, episodeId, await getFreshDocument(projectId, episodeId));
      if (actualLatest === null || restoreRefreshStatus(actualLatest, { revision: committed.createdRevision, id: committed.createdDraftId }) !== "confirmed") {
        await invalidateAfterRestore(queryClient, projectId, episodeId);
        setPostRefreshError(refreshMessage(committed.createdRevision));
        return;
      }
      await invalidateAfterRestore(queryClient, projectId, episodeId);
      setSelectedRevision(null);
      setSelectedBlockId(null);
      setCommittedRestore(null);
    } catch {
      await invalidateAfterRestore(queryClient, projectId, episodeId);
      setPostRefreshError(refreshMessage(committed.createdRevision));
    }
  }

  async function downloadExport() {
    if (displayRevision === null) return;
    setExportError(null);
    setExportWarnings([]);
    try {
      const exported = await fetchNarouExport(projectId, episodeId, displayRevision);
      if (exported === null) throw new Error("The manuscript export did not match the displayed revision.");
      assertExport(exported);
      setExportWarnings(exported.warnings);
      downloadText(exported);
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : "Unable to export the manuscript.");
    }
  }

  function handleReaderClick(event: MouseEvent<HTMLDivElement>) {
    let element: Element | null = event.target instanceof Element ? event.target.closest("[id]") : null;
    while (element !== null) {
      if (isFormalBlockId(element.id)) {
        setSelectedBlockId(element.id);
        return;
      }
      element = element.parentElement?.closest("[id]") ?? null;
    }
  }

  const isHistorical = selectedRevision !== null;
  const restoreLocked = committedRestore !== null;
  const snapshotLocked = editSession !== null || editPending || committedSave !== null || restoreLocked;

  return (
    <>
      <Link className="back-link" to={`/projects/${encodeURIComponent(projectId)}/manuscript`}>Back to manuscript</Link>
      <div className="detail-heading">
        <div><p className="eyebrow">Episode #{episodeId}</p><h1>{editSession ? "Manuscript editor" : committedSave ? "Manuscript save" : documentRead ? "Manuscript reader" : "Manuscript"}</h1></div>
        {committedSave === null && displayRevision !== null && <span className="version-note">{isHistorical ? "Historical" : "Latest"} revision {displayRevision}</span>}
      </div>
      {restoreSuccess && <p className="saved-indicator" role="status">Restore succeeded as revision {restoreSuccess.revision}.</p>}
      {saveSuccess && <p className="saved-indicator" role="status">Save succeeded as revision {saveSuccess.revision}.</p>}
      {postRefreshError && <p role="alert">{postRefreshError}</p>}
      {restoreError && <p role="alert">{restoreError}</p>}
      {editPending && <p role="status">Preparing manuscript editor…</p>}
      {editError && <p role="alert">{editError}</p>}
      {editSession && (
        <>
          <DirtyNavigationGuard dirty={editDirty} pending={editSaving} />
          <ManuscriptEditor
            key={editSession.key}
            initialHtml={editSession.initialHtml}
            baselineDocument={editSession.baselineDocument}
            scenes={scenes}
            scenesLoading={scenesLoading}
            scenesError={scenesError}
            characters={charactersQuery.data ?? []}
            charactersLoading={charactersQuery.isPending}
            charactersError={charactersQuery.isError ? "Unable to load characters. Existing speaker references were kept." : null}
            saving={editSaving}
            cancelPending={discardPending}
            interactionBlocked={discardDialogOpen || editConflict !== null}
            onDirtyChange={setEditDirty}
            onSave={(html) => void saveEditedHtml(html)}
            onCancel={(dirty) => dirty ? setDiscardDialogOpen(true) : void cancelEditing()}
          />
        </>
      )}
      {editConflict && <ConflictDialog local={{ html: editConflict.localHtml }} latest={editConflict.latest} entityLabel="manuscript" onKeep={keepLocalConflict} onDiscard={() => void loadLatestIntoEditor()} errorMessage={editError} discardPending={conflictReloadPending} />}
      {committedSave && (
        <Card>
          <p className="saved-indicator">Save succeeded as revision {committedSave.createdRevision}.</p>
          <p role={committedSaveError ? "alert" : "status"}>{committedSaveError ?? "Confirming latest manuscript…"}</p>
          <Button type="button" variant="secondary" onClick={() => void reloadCommittedSave()} disabled={editPending || committedSaveRefreshPending}>Reload latest</Button>
        </Card>
      )}
      {!editSession && committedSave === null && (
        <>
          {documentQuery.isPending && <p role="status">Loading manuscript…</p>}
          {documentQuery.isError && <p role="alert">{documentQuery.error instanceof Error ? documentQuery.error.message : "Unable to load the manuscript document."}</p>}
          {!documentQuery.isPending && !documentQuery.isError && documentRead === null && <div className="empty-state-inline"><p>No manuscript draft yet.</p><Button type="button" onClick={() => void beginEdit()} disabled={snapshotLocked}>Create manuscript</Button></div>}
        </>
      )}
      {!editSession && committedSave === null && documentRead !== null && (
        <>
          <Card>
            <div className="manuscript-toolbar">
              <div><strong>{isHistorical ? "Historical snapshot" : "Latest snapshot"}</strong><p className="read-only-meta">Revision {displayRevision} · {documentRead.created_at} · {documentRead.source_agent ?? "unknown source"}</p></div>
              <label className="toggle-control"><input type="checkbox" checked={includeNotes} onChange={(event) => setIncludeNotes(event.target.checked)} />Show production notes</label>
              {!isHistorical && <a className="button button-secondary" href={readEpisodeUrl(projectId, episodeId)} target="_blank" rel="noopener noreferrer">この話を読む</a>}
              {!isHistorical && <Button type="button" onClick={() => void beginEdit()} disabled={snapshotLocked}>Edit manuscript</Button>}
            </div>
            {documentRead.content.blocks.length === 0 && <p className="empty-state-inline">This manuscript revision is empty.</p>}
            {webQuery.isPending && <p role="status">Loading manuscript projection…</p>}
            {webQuery.isError && <p role="alert">{webQuery.error instanceof Error ? webQuery.error.message : "Unable to load a consistent manuscript view."}</p>}
            {webQuery.data && <Reader web={webQuery.data} onClick={handleReaderClick} />}
          </Card>
          <div className="manuscript-columns">
            <Inspector blocks={visibleBlocks} selectedBlock={selectedBlock} selectedBlockId={selectedBlockId} onSelect={setSelectedBlockId} rawOpen={rawAnnotationsOpen} onToggleRaw={() => setRawAnnotationsOpen((open) => !open)} />
            <Card>
              <h2>Snapshot actions</h2>
              <div className="form-actions">
                 <Button type="button" variant="secondary" onClick={() => setRawDocumentOpen((open) => !open)} disabled={snapshotLocked}>{rawDocumentOpen ? "Hide Raw Document" : "Show Raw Document"}</Button>
                 <Button type="button" onClick={() => void downloadExport()} disabled={snapshotLocked}>Download Narou export</Button>
              </div>
              {exportError && <p role="alert">{exportError}</p>}
              {exportWarnings.length > 0 && <div className="export-warnings" role="status"><strong>Export warnings</strong><ul>{exportWarnings.map((warning, index) => <li key={`${warning.code}-${warning.block_id ?? "document"}-${index}`}><code>{warning.code}</code>: {warning.message}{warning.block_id && <small> (block {warning.block_id})</small>}</li>)}</ul></div>}
              {rawDocumentOpen && <pre className="json-block raw-document">{JSON.stringify(documentRead.content, null, 2)}</pre>}
               {isHistorical && <div className="form-actions"><Button type="button" variant="secondary" onClick={() => void viewLatest()} disabled={restorePending || snapshotLocked}>View latest</Button><Button type="button" variant="danger" onClick={() => setRestoreRevision(selectedRevision)} disabled={restorePending || restoreLocked || snapshotLocked}>Restore revision {selectedRevision}</Button></div>}
              {restoreLocked && <p className="helper-text">Restore is locked until the post-write latest revision is confirmed.</p>}
            </Card>
          </div>
        </>
      )}
      <History history={historyQuery.data ?? []} isLoading={historyQuery.isPending} isError={historyQuery.isError} selectedRevision={selectedRevision} onSelect={selectHistoricalRevision} disabled={snapshotLocked} />
      {restoreRevision !== null && <RestoreDialog revision={restoreRevision} pending={restorePending} onCancel={() => setRestoreRevision(null)} onConfirm={() => void confirmRestore()} />}
      {discardDialogOpen && <DiscardDialog pending={discardPending} onKeep={() => setDiscardDialogOpen(false)} onDiscard={() => void cancelEditing()} />}
    </>
  );
}

function Reader({ web, onClick }: { web: DraftWebRead; onClick: (event: MouseEvent<HTMLDivElement>) => void }) {
  return <section aria-label="Manuscript reader" className="manuscript-reader"><div className="manuscript-reader-content" onClick={onClick} dangerouslySetInnerHTML={{ __html: web.content }} /></section>;
}

function Inspector({
  blocks,
  selectedBlock,
  selectedBlockId,
  onSelect,
  rawOpen,
  onToggleRaw,
}: {
  blocks: NovelBlock[];
  selectedBlock: NovelBlock | null;
  selectedBlockId: string | null;
  onSelect: (id: string | null) => void;
  rawOpen: boolean;
  onToggleRaw: () => void;
}) {
  return (
    <Card>
      <h2>Block Inspector</h2>
      <label className="field-group" htmlFor="block-selector">Block selector</label>
      <select id="block-selector" className="field-control" value={selectedBlockId ?? ""} onChange={(event) => onSelect(event.target.value || null)}>
        <option value="">Select a block</option>
        {blocks.map((block) => <option key={block.id} value={block.id}>{block.type} · {block.id}</option>)}
      </select>
      {selectedBlock === null ? <p className="helper-text">Select a block to inspect its canonical metadata.</p> : <BlockDetails block={selectedBlock} rawOpen={rawOpen} onToggleRaw={onToggleRaw} />}
    </Card>
  );
}

function BlockDetails({ block, rawOpen, onToggleRaw }: { block: NovelBlock; rawOpen: boolean; onToggleRaw: () => void }) {
  const unknown = projectableUnknownAnnotations(block.annotations);
  return (
    <div className="block-details">
      <dl className="record-summary">
        <Detail label="Block ID" value={block.id} />
        <Detail label="type" value={block.type} />
        <Detail label="scene_id" value={displayNumber(block.attrs.scene_id)} />
        <Detail label="speaker_character_id" value={displayNumber(block.attrs.speaker_character_id)} />
        <Detail label="heading_level" value={displayNumber(block.attrs.heading_level)} />
      </dl>
      <h3>Emotions</h3><p className="read-only-meta">{displayJson(block.annotations.emotions)}</p>
      <h3>Projectable annotations</h3>
      {unknown.length === 0 ? <p className="helper-text">None.</p> : <dl className="record-summary">{unknown.map((annotation) => <Detail key={annotation.key} label={annotation.key} value={annotation.value} />)}</dl>}
      <Button type="button" variant="ghost" onClick={onToggleRaw}>{rawOpen ? "Hide Raw annotations JSON" : "Show Raw annotations JSON"}</Button>
      {rawOpen && <pre className="json-block">{JSON.stringify(block.annotations, null, 2)}</pre>}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function History({
  history,
  isLoading,
  isError,
  selectedRevision,
  onSelect,
  disabled,
}: {
  history: DraftHistoryItem[];
  isLoading: boolean;
  isError: boolean;
  selectedRevision: number | null;
  onSelect: (revision: number) => void;
  disabled: boolean;
}) {
  return (
    <Card>
      <h2>Draft history</h2>
      {isError && <p role="alert">Unable to load draft history.</p>}
      {isLoading && <p role="status">Loading draft history…</p>}
      {!isLoading && !isError && history.length === 0 && <p>No draft history.</p>}
       {history.length > 0 && <div className="record-list">{history.map((item) => <div className="record-list-item" key={item.id}><span><strong>Revision {item.revision}</strong><small>{item.created_at} · {item.source_agent ?? "unknown source"}</small><small>{item.change_summary || "No change summary"} · {parentText(item, history)}</small></span><Button type="button" variant="secondary" onClick={() => onSelect(item.revision)} disabled={disabled || selectedRevision === item.revision}>View revision {item.revision}</Button></div>)}</div>}
    </Card>
  );
}

function RestoreDialog({ revision, pending, onCancel, onConfirm }: { revision: number; pending: boolean; onCancel: () => void; onConfirm: () => void }) {
  return <div className="dialog-backdrop"><div className="dialog" role="dialog" aria-modal="true" aria-labelledby="restore-title"><h2 id="restore-title">Restore revision {revision} as a new revision?</h2><p>The selected Canonical Document will be appended as a new revision. No historical revision will be changed.</p><div className="dialog-actions"><Button type="button" variant="secondary" onClick={onCancel} disabled={pending}>Cancel</Button><Button type="button" variant="danger" onClick={onConfirm} disabled={pending}>{pending ? "Restoring…" : "Confirm restore"}</Button></div></div></div>;
}

function DiscardDialog({ pending, onKeep, onDiscard }: { pending: boolean; onKeep: () => void; onDiscard: () => void }) {
  const keepButtonRef = useRef<HTMLButtonElement>(null);
  const { dialogRef, onKeyDown } = useModalFocus(true, {
    initialFocusRef: keepButtonRef,
    onEscape: () => {
      if (!pending) onKeep();
    },
  });

  return (
    <div className="dialog-backdrop" role="presentation">
      <section ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="discard-title" onKeyDown={onKeyDown}>
        <h2 id="discard-title">Discard unsaved manuscript edits?</h2>
        <p>Your local manuscript changes will be discarded after the latest revision is loaded.</p>
        <div className="dialog-actions">
          <Button ref={keepButtonRef} type="button" variant="secondary" onClick={onKeep} disabled={pending}>Keep editing</Button>
          <Button type="button" variant="danger" onClick={onDiscard} disabled={pending}>{pending ? "Loading latest…" : "Discard edits"}</Button>
        </div>
      </section>
    </div>
  );
}

type CommittedRestore = { sourceRevision: number; createdRevision: number; createdDraftId: number };
type CommittedSave = { createdRevision: number; createdDraftId: number };
type EditSession = { key: number; baselineDocument: DraftDocumentRead | null; baselineDraftId: number | null; initialHtml: string };
type EditConflict = { localHtml: string; latest: DraftDocumentRead | ReturnType<typeof asDraftHtmlPreview>; initial: boolean };

async function getFreshDocument(projectId: string, episodeId: number): Promise<DraftDocumentRead | null> {
  const read = await fetchFreshLatestDocument(projectId, episodeId);
  return read === null ? null : assertDocumentIdentity(read, episodeId);
}

function safeReconcileLatestObservation(
  previous: DraftDocumentRead | null | undefined,
  incoming: DraftDocumentRead | null | undefined,
): DraftDocumentRead | null | undefined {
  try {
    return reconcileLatestObservation(previous, incoming);
  } catch {
    return previous;
  }
}

function setLatestDocument(
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
  episodeId: number,
  incoming: DraftDocumentRead | null,
): DraftDocumentRead | null {
  let adopted: DraftDocumentRead | null | undefined;
  let inconsistency: unknown = null;
  queryClient.setQueryData<DraftDocumentRead | null>(
    projectQueryKeys.draftDocument(projectId, episodeId, "latest"),
    (previous) => {
      try {
        adopted = reconcileLatestObservation(previous, incoming);
        return adopted ?? null;
      } catch (caught) {
        inconsistency = caught;
        adopted = previous;
        return previous ?? null;
      }
    },
  );
  if (inconsistency !== null) throw inconsistency;
  return adopted ?? null;
}

async function getMatchingAuthoringHtml(projectId: string, episodeId: number, document: DraftDocumentRead) {
  const html = assertHtmlIdentity(
    await fetchDraftAuthoringHtml(projectId, episodeId, document.revision),
    episodeId,
    document.revision,
  );
  if (html.id !== document.id || html.work_id !== document.work_id || html.episode_id !== document.episode_id || html.revision !== document.revision) {
    throw new Error("The manuscript document and authoring HTML have inconsistent snapshot identity.");
  }
  return html;
}

async function refreshHistory(queryClient: ReturnType<typeof useQueryClient>, projectId: string, episodeId: number) {
  await queryClient.invalidateQueries({ queryKey: projectQueryKeys.draftHistory(projectId, episodeId) });
}

async function invalidateAfterRestore(queryClient: ReturnType<typeof useQueryClient>, projectId: string, episodeId: number) {
  await queryClient.invalidateQueries({ queryKey: projectQueryKeys.draftHistory(projectId, episodeId) });
  await queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) });
}

async function invalidateAfterSave(queryClient: ReturnType<typeof useQueryClient>, projectId: string, episodeId: number) {
  await queryClient.invalidateQueries({ queryKey: projectQueryKeys.draftHistory(projectId, episodeId) });
  await queryClient.invalidateQueries({ queryKey: projectQueryKeys.episodeViews(projectId) });
}

function parentText(item: DraftHistoryItem, history: DraftHistoryItem[]): string {
  if (item.parent_draft_id === null) return "No parent draft";
  const parent = history.find((candidate) => candidate.id === item.parent_draft_id);
  return parent ? `Parent revision ${parent.revision}` : `Parent draft #${item.parent_draft_id}`;
}

function displayNumber(value: number | undefined): string {
  return value === undefined ? "—" : String(value);
}

function displayJson(value: JsonValue | undefined): string {
  return value === undefined ? "—" : JSON.stringify(value);
}

function assertSaveResult(value: DraftSaveResult): asserts value is DraftSaveResult {
  if (!Number.isInteger(value.id) || value.id <= 0 || !Number.isInteger(value.revision) || value.revision <= 0) throw new Error("The draft save response has an invalid revision identity.");
}

function assertExport(value: DraftExport): asserts value is DraftExport {
  if (value.format !== "narou" || typeof value.media_type !== "string" || typeof value.content !== "string" || typeof value.suggested_filename !== "string" || !Array.isArray(value.warnings) || !value.warnings.every(isExportWarning)) throw new Error("The manuscript export response is inconsistent.");
}

function isExportWarning(value: unknown): value is ExportWarning {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const warning = value as { code?: unknown; message?: unknown; block_id?: unknown };
  return typeof warning.code === "string" && typeof warning.message === "string" && (typeof warning.block_id === "string" || warning.block_id === null);
}

function downloadText(exported: DraftExport) {
  const blob = new Blob([exported.content], { type: exported.media_type });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = exported.suggested_filename;
  document.body.append(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  }
}

function refreshMessage(revision: number): string {
  return `Restore succeeded as revision ${revision}, but the latest manuscript could not be reloaded.`;
}

function saveRefreshMessage(revision: number): string {
  return `Save succeeded as revision ${revision}, but the latest manuscript could not be reloaded.`;
}

function positiveId(value: string): number | null {
  return /^[1-9]\d*$/.test(value) ? Number(value) : null;
}

function readEpisodeUrl(projectId: string, episodeId: number): string {
  return `/read/projects/${encodeURIComponent(projectId)}/episodes/${episodeId}/`;
}
