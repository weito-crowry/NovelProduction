import { useParams } from "react-router-dom";
import { NotFound } from "./NotFound";
import { StructurePage } from "../features/structure/StructurePage";

export function StructureRoute() {
  const params = useParams();
  const invalid = [params.chapterId, params.episodeId, params.sceneId].some(
    (value) => value !== undefined && !isPositiveInteger(value),
  );
  if (invalid) return <NotFound message="The structure route ID must be a positive integer." />;
  return <StructurePage />;
}

function isPositiveInteger(value: string): boolean {
  return /^[1-9]\d*$/.test(value);
}
