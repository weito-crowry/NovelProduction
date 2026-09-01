import { NavLink, Link } from "react-router-dom";
import type { RefObject } from "react";


export function Sidebar({
  projectId,
  open,
  onClose,
  closeButtonRef,
}: {
  projectId: string;
  open: boolean;
  onClose: (restoreFocus?: boolean) => void;
  closeButtonRef: RefObject<HTMLButtonElement | null>;
}) {
  return (
    <aside
      id="project-navigation"
      className={open ? "sidebar sidebar-open" : "sidebar"}
      aria-label="Project navigation"
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          onClose(true);
        }
      }}
    >
      <div className="sidebar-brand">NovelProduction</div>
      <button
        ref={closeButtonRef}
        className="sidebar-close"
        type="button"
        onClick={() => onClose(true)}
      >
        Hide navigation
      </button>
      <Link className="sidebar-projects" to="/" onClick={() => onClose(false)}>
        All projects
      </Link>
      <nav>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/dashboard`}
          onClick={() => onClose(false)}
        >
          Dashboard
        </NavLink>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/structure`}
          onClick={() => onClose(false)}
        >
          Structure
        </NavLink>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/world`}
          onClick={() => onClose(false)}
        >
          World
        </NavLink>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/characters`}
          onClick={() => onClose(false)}
        >
          Characters
        </NavLink>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/timeline`}
          onClick={() => onClose(false)}
        >
          Timeline
        </NavLink>
        <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to={`/projects/${encodeURIComponent(projectId)}/information`} onClick={() => onClose(false)}>Information</NavLink>
        <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to={`/projects/${encodeURIComponent(projectId)}/manuscript`} onClick={() => onClose(false)}>Manuscript</NavLink>
        <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to={`/projects/${encodeURIComponent(projectId)}/canon`} onClick={() => onClose(false)}>Canon / History</NavLink>
        <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to={`/projects/${encodeURIComponent(projectId)}/style-analysis`} onClick={() => onClose(false)}>Style analysis</NavLink>
      </nav>
    </aside>
  );
}
