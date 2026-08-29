import { NavLink, Link } from "react-router-dom";


export function Sidebar({
  projectId,
  open,
  onClose,
}: {
  projectId: string;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <aside
      id="project-navigation"
      className={open ? "sidebar sidebar-open" : "sidebar"}
      aria-label="Project navigation"
    >
      <div className="sidebar-brand">NovelProduction</div>
      <button className="sidebar-close" type="button" onClick={onClose}>
        Hide navigation
      </button>
      <Link className="sidebar-projects" to="/" onClick={onClose}>
        All projects
      </Link>
      <nav>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/dashboard`}
          onClick={onClose}
        >
          Dashboard
        </NavLink>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/structure`}
          onClick={onClose}
        >
          Structure
        </NavLink>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/world`}
          onClick={onClose}
        >
          World
        </NavLink>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/characters`}
          onClick={onClose}
        >
          Characters
        </NavLink>
        <NavLink
          className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          to={`/projects/${encodeURIComponent(projectId)}/timeline`}
          onClick={onClose}
        >
          Timeline
        </NavLink>
        <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to={`/projects/${encodeURIComponent(projectId)}/information`} onClick={onClose}>Information</NavLink>
        <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to={`/projects/${encodeURIComponent(projectId)}/manuscript`} onClick={onClose}>Manuscript</NavLink>
        <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to={`/projects/${encodeURIComponent(projectId)}/canon`} onClick={onClose}>Canon / History</NavLink>
      </nav>
    </aside>
  );
}
