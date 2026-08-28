import { createElement } from "react";
import type { RouteObject } from "react-router-dom";
import { ProjectPickerPage } from "../features/projects/ProjectPickerPage";
import { NotFound } from "./NotFound";
import { ProjectDashboardRoute } from "./ProjectDashboardRoute";

export const appRoutes: RouteObject[] = [
  { path: "/", element: createElement(ProjectPickerPage) },
  {
    path: "/projects/:projectId/dashboard",
    element: createElement(ProjectDashboardRoute),
  },
  { path: "*", element: createElement(NotFound) },
];
