import { createElement } from "react";
import type { RouteObject } from "react-router-dom";
import { ProjectPickerPage } from "../features/projects/ProjectPickerPage";
import { NotFound } from "./NotFound";
import { ProjectDashboardRoute } from "./ProjectDashboardRoute";
import { StructureRoute } from "./StructureRoute";
import { WorldRoute } from "./WorldRoute";
import { CharactersRoute } from "./CharactersRoute";
import { TimelineRoute } from "./TimelineRoute";
import { InformationPage } from "../features/information/InformationPage";
import { CanonPage } from "../features/canon/CanonPage";
import { ManuscriptPage } from "../features/manuscript/ManuscriptPage";
import { StyleAnalysisPage } from "../features/styleAnalysis/StyleAnalysisPage";

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
  { path: "/projects/:projectId/world", element: createElement(WorldRoute) },
  { path: "/projects/:projectId/world/:factId", element: createElement(WorldRoute) },
  { path: "/projects/:projectId/characters", element: createElement(CharactersRoute) },
  { path: "/projects/:projectId/characters/:characterId", element: createElement(CharactersRoute) },
  { path: "/projects/:projectId/timeline", element: createElement(TimelineRoute) },
  { path: "/projects/:projectId/timeline/:eventId", element: createElement(TimelineRoute) },
  { path: "/projects/:projectId/information", element: createElement(InformationPage) },
  { path: "/projects/:projectId/information/:informationId", element: createElement(InformationPage) },
  { path: "/projects/:projectId/canon", element: createElement(CanonPage) },
  { path: "/projects/:projectId/canon/:decisionId", element: createElement(CanonPage) },
  { path: "/projects/:projectId/manuscript", element: createElement(ManuscriptPage) },
  { path: "/projects/:projectId/manuscript/:episodeId", element: createElement(ManuscriptPage) },
  {
    path: "/projects/:projectId/style-analysis",
    element: createElement(StyleAnalysisPage),
  },
  {
    path: "/projects/:projectId/style-analysis/sources",
    element: createElement(StyleAnalysisPage),
  },
  {
    path: "/projects/:projectId/style-analysis/reference-works/:workId",
    element: createElement(StyleAnalysisPage),
  },
  {
    path: "/projects/:projectId/style-analysis/documents/:documentId",
    element: createElement(StyleAnalysisPage),
  },
  {
    path: "/projects/:projectId/style-analysis/corpora",
    element: createElement(StyleAnalysisPage),
  },
  {
    path: "/projects/:projectId/style-analysis/corpora/compare",
    element: createElement(StyleAnalysisPage),
  },
  {
    path: "/projects/:projectId/style-analysis/profiles",
    element: createElement(StyleAnalysisPage),
  },
  {
    path: "/projects/:projectId/style-analysis/profiles/:profileId",
    element: createElement(StyleAnalysisPage),
  },
  {
    path: "/projects/:projectId/style-analysis/review",
    element: createElement(StyleAnalysisPage),
  },
  {
    path: "/projects/:projectId/style-analysis/lint",
    element: createElement(StyleAnalysisPage),
  },
  { path: "*", element: createElement(NotFound) },
];
