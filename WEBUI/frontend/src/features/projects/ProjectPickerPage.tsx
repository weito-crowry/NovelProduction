import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { FormEvent } from "react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextInput } from "../../components/ui/Field";
import {
  createProject,
  fetchProjects,
  updateProjectStatus,
} from "./projectApi";

export function ProjectPickerPage() {
  const [includeArchived, setIncludeArchived] = useState(false);
  const [workingTitle, setWorkingTitle] = useState("");
  const [projectId, setProjectId] = useState("");
  const projectsQuery = useQuery({
    queryKey: ["projects", includeArchived],
    queryFn: () => fetchProjects(includeArchived),
  });

  const createMutation = useMutationForCreate();
  const statusMutation = useMutationForStatus(includeArchived);

  function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workingTitle.trim()) return;
    createMutation.mutate({
      working_title: workingTitle,
      ...(projectId.trim() ? { project_id: projectId.trim() } : {}),
    });
  }

  return (
    <main className="picker-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>Projects</h1>
        </div>
        <label className="toggle-control">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
          />
          Include archived
        </label>
      </div>

      <Card>
        <h2>Create a project</h2>
        <form className="create-form" onSubmit={submitCreate}>
          <div className="field-group">
            <FieldLabel htmlFor="new-working-title">Working title</FieldLabel>
            <TextInput
              id="new-working-title"
              required
              value={workingTitle}
              onChange={(event) => setWorkingTitle(event.target.value)}
            />
          </div>
          <div className="field-group">
            <FieldLabel htmlFor="new-project-id">Project ID (optional)</FieldLabel>
            <TextInput
              id="new-project-id"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
            />
          </div>
          <Button type="submit" disabled={createMutation.isPending}>
            Create project
          </Button>
        </form>
        {createMutation.isError && <p role="alert">Unable to create project.</p>}
      </Card>

      <section aria-labelledby="project-list-heading">
        <h2 id="project-list-heading">Available projects</h2>
        {projectsQuery.isPending && <p role="status">Loading projects…</p>}
        {projectsQuery.isError && <p role="alert">Unable to load projects.</p>}
        <div className="project-grid">
          {projectsQuery.data?.map((project) => (
            <Card key={project.project_id}>
              <div className="project-card-heading">
                <h3>
                  <Link to={`/projects/${encodeURIComponent(project.project_id)}/dashboard`}>
                    {project.working_title || "Untitled project"}
                  </Link>
                </h3>
                <Badge>{project.status}</Badge>
              </div>
              <dl className="project-meta">
                <div><dt>Project ID</dt><dd>{project.project_id}</dd></div>
                <div><dt>Health</dt><dd>{project.health}</dd></div>
                <div><dt>Metadata</dt><dd>{project.metadata_state}</dd></div>
              </dl>
              <Button
                type="button"
                variant={project.status === "archived" ? "secondary" : "danger"}
                onClick={() =>
                  statusMutation.mutate({
                    projectId: project.project_id,
                    status: project.status === "archived" ? "active" : "archived",
                  })
                }
              >
                {project.status === "archived" ? "Unarchive" : "Archive"}
              </Button>
            </Card>
          ))}
        </div>
      </section>
    </main>
  );
}

function useMutationForCreate() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/projects/${encodeURIComponent(project.project_id)}/dashboard`);
    },
  });
}

function useMutationForStatus(includeArchived: boolean) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, status }: { projectId: string; status: "active" | "archived" }) =>
      updateProjectStatus(projectId, status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      if (!includeArchived) {
        await queryClient.refetchQueries({ queryKey: ["projects", false] });
      }
    },
  });
}
