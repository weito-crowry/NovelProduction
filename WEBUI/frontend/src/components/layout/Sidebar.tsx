import { NavLink, Link } from "react-router-dom";

const futureSections = [
  "Structure",
  "World",
  "Characters",
  "Timeline",
  "Information",
  "Manuscript",
  "Canon / History",
];

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
        <div className="nav-future" aria-label="Future sections">
          {futureSections.map((section) => (
            <span key={section} className="nav-link disabled" aria-disabled="true">
              {section}
            </span>
          ))}
        </div>
      </nav>
    </aside>
  );
}
