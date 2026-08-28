import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState, type ReactNode } from "react";
import { isApiError } from "../../api/errors";
import { projectQueryKeys } from "../../api/queryKeys";
import type {
  ChapterRecord,
  EpisodeRecord,
  OutlineChapterView,
  OutlineEpisodeView,
  OutlineView,
  SceneRecord,
} from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ConflictDialog } from "../conflicts/ConflictDialog";
import {
  fetchOutline,
  reorderChapter,
  reorderEpisode,
  reorderScene,
} from "./structureApi";

type EntityKind = "chapter" | "episode" | "scene";
type TreeRecord = ChapterRecord | EpisodeRecord | SceneRecord;

interface Selection {
  kind: EntityKind;
  id: number;
}

interface ConflictState {
  kind: EntityKind;
  local: TreeRecord;
  latest: TreeRecord;
}

interface StructureTreeProps {
  projectId: string;
  outline: OutlineView | undefined;
  selection: Selection | null;
  onAddChapter: () => void;
  onAddEpisode: (chapterId: number) => void;
  onAddScene: (episodeId: number) => void;
}

export function StructureTree({
  projectId,
  outline,
  selection,
  onAddChapter,
  onAddEpisode,
  onAddScene,
}: StructureTreeProps) {
  const queryClient = useQueryClient();
  const [reorderError, setReorderError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<ConflictState | null>(null);
  const reorderMutation = useMutation({
    mutationFn: async ({
      kind,
      id,
      targetPosition,
      expectedVersion,
    }: {
      kind: EntityKind;
      id: number;
      targetPosition: number;
      expectedVersion: number;
    }) => {
      const input = {
        target_position: targetPosition,
        expected_version: expectedVersion,
      };
      if (kind === "chapter") return reorderChapter(projectId, id, input);
      if (kind === "episode") return reorderEpisode(projectId, id, input);
      return reorderScene(projectId, id, input);
    },
    retry: false,
    onSuccess: async () => {
      setReorderError(null);
      setConflict(null);
      await queryClient.invalidateQueries({
        queryKey: projectQueryKeys.outline(projectId),
      });
    },
    onError: async (error, variables) => {
      await queryClient.invalidateQueries({
        queryKey: projectQueryKeys.outline(projectId),
      });
      if (isApiError(error) && error.status === 409 && error.code === "VERSION_CONFLICT") {
        const local = findRecord(outline, variables.kind, variables.id);
        let latest = asTreeRecord(error.details.current_resource);
        if (latest === null) {
          const latestOutline = await fetchOutline(projectId);
          queryClient.setQueryData(projectQueryKeys.outline(projectId), latestOutline);
          latest = findRecord(latestOutline, variables.kind, variables.id);
        }
        if (local && latest) {
          setConflict({ kind: variables.kind, local, latest });
          return;
        }
      }
      setReorderError(
        isApiError(error) ? error.message : "Unable to reorder the structure.",
      );
    },
  });

  function handleDragEnd(event: DragEndEvent) {
    const active = parseDragId(event.active.id);
    const over = event.over ? parseDragId(event.over.id) : null;
    if (!outline || !active || !over || !sameParent(outline, active, over)) return;

    const siblings = siblingsFor(outline, active);
    const fromIndex = siblings.findIndex((record) => record.id === active.id);
    const toIndex = siblings.findIndex((record) => record.id === over.id);
    if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return;

    const dragged = siblings[fromIndex];
    reorderMutation.mutate({
      kind: active.kind,
      id: active.id,
      targetPosition: toIndex + 1,
      expectedVersion: dragged.version,
    });
  }

  if (!outline) return null;

  return (
    <Card>
      <div className="structure-tree-heading">
        <div>
          <p className="eyebrow">Narrative structure</p>
          <h2>Structure tree</h2>
        </div>
        <Button type="button" onClick={onAddChapter}>
          Add chapter
        </Button>
      </div>
      {reorderError && <p role="alert">{reorderError}</p>}
      <StructureDndContext onDragEnd={handleDragEnd}>
        <SortableContext
          items={outline.chapters.map(({ chapter }) => dragId("chapter", chapter.id))}
          strategy={verticalListSortingStrategy}
        >
          <div className="structure-tree" aria-label="Structure tree">
            {outline.chapters.map((chapter) => (
              <ChapterTreeItem
                key={chapter.chapter.id}
                projectId={projectId}
                chapter={chapter}
                selection={selection}
                onAddEpisode={onAddEpisode}
                onAddScene={onAddScene}
                onDragEnd={handleDragEnd}
              />
            ))}
          </div>
        </SortableContext>
      </StructureDndContext>
      {conflict && (
        <ConflictDialog
          entityLabel={`${conflict.kind} order`}
          local={conflict.local}
          latest={conflict.latest}
          onDiscard={() => setConflict(null)}
          onKeep={() => setConflict(null)}
        />
      )}
    </Card>
  );
}

function StructureDndContext({
  children,
  onDragEnd,
}: {
  children: ReactNode;
  onDragEnd: (event: DragEndEvent) => void;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={onDragEnd}
    >
      {children}
    </DndContext>
  );
}

function ChapterTreeItem({
  projectId,
  chapter,
  selection,
  onAddEpisode,
  onAddScene,
  onDragEnd,
}: {
  projectId: string;
  chapter: OutlineChapterView;
  selection: Selection | null;
  onAddEpisode: (chapterId: number) => void;
  onAddScene: (episodeId: number) => void;
  onDragEnd: (event: DragEndEvent) => void;
}) {
  return (
    <div className="tree-node tree-node-chapter">
      <SortableTreeLink
        kind="chapter"
        record={chapter.chapter}
        selected={selection?.kind === "chapter" && selection.id === chapter.chapter.id}
        to={`/projects/${encodeURIComponent(projectId)}/structure/chapters/${chapter.chapter.id}`}
      />
      <Button type="button" variant="ghost" onClick={() => onAddEpisode(chapter.chapter.id)}>
        Add episode
      </Button>
      <StructureDndContext onDragEnd={onDragEnd}>
        <SortableContext
          items={chapter.episodes.map(({ episode }) => dragId("episode", episode.id))}
          strategy={verticalListSortingStrategy}
        >
          <div className="tree-children">
            {chapter.episodes.map((episode) => (
              <EpisodeTreeItem
                key={episode.episode.id}
                projectId={projectId}
                episode={episode}
                selection={selection}
                onAddScene={onAddScene}
                onDragEnd={onDragEnd}
              />
            ))}
          </div>
        </SortableContext>
      </StructureDndContext>
    </div>
  );
}

function EpisodeTreeItem({
  projectId,
  episode,
  selection,
  onAddScene,
  onDragEnd,
}: {
  projectId: string;
  episode: OutlineEpisodeView;
  selection: Selection | null;
  onAddScene: (episodeId: number) => void;
  onDragEnd: (event: DragEndEvent) => void;
}) {
  return (
    <div className="tree-node tree-node-episode">
      <SortableTreeLink
        kind="episode"
        record={episode.episode}
        selected={selection?.kind === "episode" && selection.id === episode.episode.id}
        to={`/projects/${encodeURIComponent(projectId)}/structure/episodes/${episode.episode.id}`}
      />
      <Button type="button" variant="ghost" onClick={() => onAddScene(episode.episode.id)}>
        Add scene
      </Button>
      <StructureDndContext onDragEnd={onDragEnd}>
        <SortableContext
          items={episode.scenes.map((scene) => dragId("scene", scene.id))}
          strategy={verticalListSortingStrategy}
        >
          <div className="tree-children">
            {episode.scenes.map((scene) => (
              <SortableTreeLink
                key={scene.id}
                kind="scene"
                record={scene}
                selected={selection?.kind === "scene" && selection.id === scene.id}
                to={`/projects/${encodeURIComponent(projectId)}/structure/scenes/${scene.id}`}
              />
            ))}
          </div>
        </SortableContext>
      </StructureDndContext>
    </div>
  );
}

function SortableTreeLink({
  kind,
  record,
  selected,
  to,
}: {
  kind: EntityKind;
  record: TreeRecord;
  selected: boolean;
  to: string;
}) {
  const sortable = useSortable({ id: dragId(kind, record.id) });
  const style = {
    transform: CSS.Transform.toString(sortable.transform),
    transition: sortable.transition,
  };
  return (
    <div ref={sortable.setNodeRef} style={style} className="tree-link-row">
      <Link
        className={selected ? "tree-link selected" : "tree-link"}
        data-entity-kind={kind}
        data-entity-id={record.id}
        to={to}
      >
        <span>{record.title}</span>
        <small>v{record.version}</small>
      </Link>
      <button
        type="button"
        className="tree-drag-handle"
        aria-label={`Reorder ${kind} ${record.title}`}
        {...sortable.attributes}
        {...sortable.listeners}
      >
        ↕
      </button>
    </div>
  );
}

function dragId(kind: EntityKind, id: number): string {
  return `${kind}:${id}`;
}

function parseDragId(value: string | number): Selection | null {
  const match = String(value).match(/^(chapter|episode|scene):([1-9]\d*)$/);
  if (!match) return null;
  return { kind: match[1] as EntityKind, id: Number(match[2]) };
}

function sameParent(outline: OutlineView, active: Selection, over: Selection): boolean {
  if (active.kind !== over.kind) return false;
  if (active.kind === "chapter") return true;
  const activeParent = parentId(outline, active);
  const overParent = parentId(outline, over);
  return activeParent !== null && activeParent === overParent;
}

function siblingsFor(outline: OutlineView, selection: Selection): TreeRecord[] {
  if (selection.kind === "chapter") return outline.chapters.map(({ chapter }) => chapter);
  for (const chapter of outline.chapters) {
    if (selection.kind === "episode") {
      if (chapter.episodes.some(({ episode }) => episode.id === selection.id)) {
        return chapter.episodes.map(({ episode }) => episode);
      }
    }
    for (const episode of chapter.episodes) {
      if (episode.scenes.some((scene) => scene.id === selection.id)) {
        return episode.scenes;
      }
    }
  }
  return [];
}

function parentId(outline: OutlineView, selection: Selection): number | null {
  if (selection.kind === "chapter") return 0;
  for (const chapter of outline.chapters) {
    if (selection.kind === "episode" && chapter.episodes.some(({ episode }) => episode.id === selection.id)) {
      return chapter.chapter.id;
    }
    for (const episode of chapter.episodes) {
      if (selection.kind === "scene" && episode.scenes.some((scene) => scene.id === selection.id)) {
        return episode.episode.id;
      }
    }
  }
  return null;
}

function findRecord(
  outline: OutlineView | undefined,
  kind: EntityKind,
  id: number,
): TreeRecord | null {
  if (!outline) return null;
  if (kind === "chapter") {
    return outline.chapters.find(({ chapter }) => chapter.id === id)?.chapter ?? null;
  }
  for (const chapter of outline.chapters) {
    for (const episode of chapter.episodes) {
      if (kind === "episode" && episode.episode.id === id) return episode.episode;
      if (kind === "scene") {
        const scene = episode.scenes.find((item) => item.id === id);
        if (scene) return scene;
      }
    }
  }
  return null;
}

function asTreeRecord(value: unknown): TreeRecord | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const record = value as Partial<TreeRecord>;
  if (
    typeof record.id !== "number" ||
    typeof record.title !== "string" ||
    typeof record.version !== "number"
  ) {
    return null;
  }
  return value as TreeRecord;
}
