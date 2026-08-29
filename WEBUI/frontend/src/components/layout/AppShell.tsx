import { useEffect, useRef, useState } from "react";
import type { PropsWithChildren } from "react";
import { Sidebar } from "./Sidebar";

export function AppShell({ projectId, children }: PropsWithChildren<{ projectId: string }>) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (sidebarOpen) closeRef.current?.focus();
  }, [sidebarOpen]);

  function closeSidebar(restoreFocus = false) {
    setSidebarOpen(false);
    if (restoreFocus) toggleRef.current?.focus();
  }

  return (
    <div className="app-shell">
      <button
        ref={toggleRef}
        className="mobile-nav-toggle"
        type="button"
        aria-expanded={sidebarOpen}
        aria-controls="project-navigation"
        onClick={() => {
          if (sidebarOpen) {
            closeSidebar(true);
          } else {
            setSidebarOpen(true);
          }
        }}
      >
        {sidebarOpen ? "Close navigation" : "Open navigation"}
      </button>
      <Sidebar
        projectId={projectId}
        open={sidebarOpen}
        closeButtonRef={closeRef}
        onClose={closeSidebar}
      />
      <main className="content-area">{children}</main>
    </div>
  );
}
