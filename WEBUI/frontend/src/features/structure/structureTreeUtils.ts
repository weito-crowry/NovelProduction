import type { OutlineView } from "../../api/types";

type EntityKind = "chapter" | "episode" | "scene";

interface Selection {
  kind: EntityKind;
  id: number;
}

export function sameParent(outline: OutlineView, active: Selection, over: Selection): boolean {
  if (active.kind !== over.kind) return false;
  if (active.kind === "chapter") return true;
  const activeParent = parentId(outline, active);
  const overParent = parentId(outline, over);
  return activeParent !== null && activeParent === overParent;
}

function parentId(outline: OutlineView, selection: Selection): number | null {
  for (const chapter of outline.chapters) {
    if (selection.kind === "episode" && chapter.episodes.some(({ episode }) => episode.id === selection.id)) {
      return chapter.chapter.id;
    }
    if (selection.kind === "scene") {
      for (const episode of chapter.episodes) {
        if (episode.scenes.some((scene) => scene.id === selection.id)) return episode.episode.id;
      }
    }
  }
  return null;
}
