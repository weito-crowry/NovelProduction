import { useState } from "react";
import type { PropsWithChildren } from "react";
import { Sidebar } from "./Sidebar";

export function AppShell({ projectId, children }: PropsWithChildren<{ projectId: string }>) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  return (
    <div className="app-shell">
      <button
        className="mobile-nav-toggle"
        type="button"
        aria-expanded={sidebarOpen}
        aria-controls="project-navigation"
        onClick={() => setSidebarOpen((open) => !open)}
      >
        {sidebarOpen ? "Close navigation" : "Open navigation"}
      </button>
      <Sidebar
        projectId={projectId}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <main className="content-area">{children}</main>
    </div>
  );
}
