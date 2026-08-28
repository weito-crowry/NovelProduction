import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { appRoutes } from "./routes";

const browserRouter = createBrowserRouter(appRoutes);

export function AppRouter() {
  return <RouterProvider router={browserRouter} />;
}
