import { createElement } from "react";
import type { RouteObject } from "react-router-dom";
import { ProjectPickerPage } from "../features/projects/ProjectPickerPage";
import { NotFound } from "./NotFound";
import { ProjectDashboardRoute } from "./ProjectDashboardRoute";
import { StructureRoute } from "./StructureRoute";

export const appRoutes: RouteObject[] = [
  { path: "/", element: createElement(ProjectPickerPage) },
  {
    path: "/projects/:projectId/dashboard",
    element: createElement(ProjectDashboardRoute),
  },
  {
    path: "/projects/:projectId/structure",
    element: createElement(StructureRoute),
  },
  {
    path: "/projects/:projectId/structure/chapters/:chapterId",
    element: createElement(StructureRoute),
  },
  {
    path: "/projects/:projectId/structure/episodes/:episodeId",
    element: createElement(StructureRoute),
  },
  {
    path: "/projects/:projectId/structure/scenes/:sceneId",
    element: createElement(StructureRoute),
  },
  { path: "*", element: createElement(NotFound) },
];
