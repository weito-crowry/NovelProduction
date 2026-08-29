import { useParams } from "react-router-dom";
import { NotFound } from "./NotFound";
import { WorldPage } from "../features/world/WorldPage";

export function WorldRoute() {
  const { factId } = useParams();
  if (factId !== undefined && !/^[1-9]\d*$/.test(factId)) {
    return <NotFound message="The world fact route ID must be a positive integer." />;
  }
  return <WorldPage />;
}
