import { useParams } from "react-router-dom";
import { NotFound } from "./NotFound";
import { TimelinePage } from "../features/timeline/TimelinePage";

export function TimelineRoute() {
  const { eventId } = useParams();
  if (eventId !== undefined && !/^[1-9]\d*$/.test(eventId)) {
    return <NotFound message="The timeline event route ID must be a positive integer." />;
  }
  return <TimelinePage />;
}
