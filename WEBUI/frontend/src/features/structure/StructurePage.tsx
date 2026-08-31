import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { projectQueryKeys } from "../../api/queryKeys";
import type { OutlineView } from "../../api/types";
import { AppShell } from "../../components/layout/AppShell";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ChapterEditor, SceneEditor } from "./NarrativeEditors";
import { CreateChapterForm, CreateEpisodeForm, CreateSceneForm } from "./NarrativeCreateForms";
import { EpisodeDetail } from "./EpisodeDetail";
import { StructureTree } from "./StructureTree";
import { fetchOutline } from "./structureApi";

type DetailKind = "chapter" | "episode" | "scene";

export function StructurePage() {
  const params = useParams();
  const [createKind, setCreateKind] = useState<"chapter" | "episode" | "scene" | null>(null);
  const [createParentId, setCreateParentId] = useState<number | null>(null);
  const projectId = params.projectId ?? "";
  const selection = getSelection(params);
  const outlineQuery = useQuery({
    queryKey: projectQueryKeys.outline(projectId),
    queryFn: () => fetchOutline(projectId),
  });

  function closeCreate() {
    setCreateKind(null);
    setCreateParentId(null);
  }

  if (outlineQuery.isPending) {
    return <AppShell projectId={projectId}><p role="status">Loading structure…</p></AppShell>;
  }
  if (outlineQuery.isError || !outlineQuery.data) {
    return <AppShell projectId={projectId}><p role="alert">Unable to load the structure.</p></AppShell>;
  }

  return (
    <AppShell projectId={projectId}>
      <div className="detail-actions">
        <a
          className="button button-secondary"
          href={readProjectUrl(projectId)}
          target="_blank"
          rel="noopener noreferrer"
        >
          読書ビュー
        </a>
      </div>
      <div className={selection ? "structure-layout structure-detail-route" : "structure-layout"}>
        <section className="structure-tree-pane">
          <StructureTree
            projectId={projectId}
            outline={outlineQuery.data}
            selection={selection}
            onAddChapter={() => {
              setCreateKind("chapter");
              setCreateParentId(null);
            }}
            onAddEpisode={(chapterId) => {
              setCreateKind("episode");
              setCreateParentId(chapterId);
            }}
            onAddScene={(episodeId) => {
              setCreateKind("scene");
              setCreateParentId(episodeId);
            }}
          />
        </section>
        <main className="structure-detail-pane">
          {selection ? (
            <StructureDetail
              projectId={projectId}
              outline={outlineQuery.data}
              selection={selection}
              onAddEpisode={(chapterId) => {
                setCreateKind("episode");
                setCreateParentId(chapterId);
              }}
            />
          ) : (
            <Card>
              <p className="eyebrow">Structure</p>
              <h1>Select a chapter, episode, or scene</h1>
              <p>Choose an item from the structure tree to view or edit it.</p>
            </Card>
          )}
        </main>
      </div>
      {createKind === "chapter" && <CreateChapterForm projectId={projectId} onClose={closeCreate} />}
      {createKind === "episode" && createParentId !== null && (
        <CreateEpisodeForm projectId={projectId} chapterId={createParentId} onClose={closeCreate} />
      )}
      {createKind === "scene" && createParentId !== null && (
        <CreateSceneForm projectId={projectId} episodeId={createParentId} onClose={closeCreate} />
      )}
    </AppShell>
  );
}

function readProjectUrl(projectId: string): string {
  return `/read/projects/${encodeURIComponent(projectId)}/`;
}

function StructureDetail({
  projectId,
  outline,
  selection,
  onAddEpisode,
}: {
  projectId: string;
  outline: OutlineView;
  selection: { kind: DetailKind; id: number };
  onAddEpisode: (chapterId: number) => void;
}) {
  const backLink = selection.kind === "episode" ? null : (
    <Link className="back-link" to={`/projects/${encodeURIComponent(projectId)}/structure`}>Back to structure</Link>
  );
  if (selection.kind === "chapter") {
    const chapter = outline.chapters.find(({ chapter }) => chapter.id === selection.id)?.chapter;
    return chapter ? (
      <>
        {backLink}
        <div className="detail-actions"><Button type="button" onClick={() => onAddEpisode(chapter.id)}>Add episode</Button></div>
        <ChapterEditor key={`${projectId}-${chapter.id}`} projectId={projectId} chapter={chapter} />
      </>
    ) : <MissingDetail />;
  }
  if (selection.kind === "episode") {
    return <EpisodeDetail key={`${projectId}-${selection.id}`} projectId={projectId} episodeId={selection.id} />;
  }
  return <>{backLink}<SceneEditor key={`${projectId}-${selection.id}`} projectId={projectId} sceneId={selection.id} /></>;
}

function MissingDetail() {
  return <Card><h1>Not found</h1><p>The requested narrative entity is not in this project.</p></Card>;
}

function getSelection(params: Readonly<Record<string, string | undefined>>): { kind: DetailKind; id: number } | null {
  if (params.chapterId) return { kind: "chapter", id: Number(params.chapterId) };
  if (params.episodeId) return { kind: "episode", id: Number(params.episodeId) };
  if (params.sceneId) return { kind: "scene", id: Number(params.sceneId) };
  return null;
}
