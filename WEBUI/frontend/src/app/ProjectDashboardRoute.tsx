import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { Button } from "../components/ui/Button";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { WorkEditor } from "../features/dashboard/WorkEditor";
import { updateProjectStatus } from "../features/projects/projectApi";
import { NotFound } from "./NotFound";

export function ProjectDashboardRoute() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const archiveMutation = useMutation({
    mutationFn: () => updateProjectStatus(projectId ?? "", "archived"),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/");
    },
  });
  if (!projectId) {
    return <NotFound />;
  }
  return (
    <AppShell projectId={projectId}>
      <div className="page-actions">
        <Button
          type="button"
          variant="danger"
          onClick={() => archiveMutation.mutate()}
          disabled={archiveMutation.isPending}
        >
          Archive project
        </Button>
      </div>
      <DashboardPage projectId={projectId} />
      <WorkEditor key={projectId} projectId={projectId} />
      {archiveMutation.isError && (
        <p role="alert">Unable to archive this project.</p>
      )}
    </AppShell>
  );
}
