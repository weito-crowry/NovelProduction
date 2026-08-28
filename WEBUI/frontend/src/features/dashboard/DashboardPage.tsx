import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { projectQueryKeys } from "../../api/queryKeys";
import { fetchDashboard } from "../projects/projectApi";
import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";

export function DashboardPage({ projectId }: { projectId: string }) {
  const dashboardQuery = useQuery({
    queryKey: projectQueryKeys.dashboard(projectId),
    queryFn: () => fetchDashboard(projectId),
  });

  if (dashboardQuery.isPending) {
    return <p role="status">Loading dashboard…</p>;
  }
  if (dashboardQuery.isError) {
    return (
      <section className="empty-state" role="alert">
        <h1>Project unavailable</h1>
        <p>Unable to load this project dashboard.</p>
        <Link to="/">Return to projects</Link>
      </section>
    );
  }

  const { work, chapter_count, episode_count, scene_count } = dashboardQuery.data;
  return (
    <section aria-labelledby="dashboard-heading">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Project dashboard</p>
          <h1 id="dashboard-heading">{work.working_title}</h1>
        </div>
        <Badge>{work.production_status}</Badge>
      </div>
      <div className="metric-grid">
        <Card>
          <span className="metric-label">Chapters</span>
          <strong>{chapter_count}</strong>
        </Card>
        <Card>
          <span className="metric-label">Episodes</span>
          <strong>{episode_count}</strong>
        </Card>
        <Card>
          <span className="metric-label">Scenes</span>
          <strong>{scene_count}</strong>
        </Card>
      </div>
    </section>
  );
}
