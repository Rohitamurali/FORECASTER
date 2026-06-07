import { NavLink } from "react-router-dom";
import API from "../services/api";

const NAV = [
  { to: "/dashboard", label: "Overview", icon: "▦" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

export default function AppLayout({
  children,
  onHistoryClick,
  historyCount = 0,
}) {
  const user = JSON.parse(localStorage.getItem("user") || "{}");

  const logout = async () => {
    try {
      await API.post("/auth/logout");
    } catch (err) {
      console.error("Logout error:", err);
    }

    localStorage.clear();
    window.location.href = "/";
  };

  return (
    <>
      <style>{`
        .app-shell {
          display: flex;
          height: 100vh;
          overflow: hidden;
        }

        .sidebar {
          width: 260px;
          min-width: 260px;
          height: 100vh;
          overflow-y: auto;
          overflow-x: hidden;
          display: flex;
          flex-direction: column;
        }

        .sidebar-spacer {
          flex: 1;
        }

        .main {
          flex: 1;
          overflow-y: auto;
          overflow-x: hidden;
          min-width: 0;
        }
      `}</style>

      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-icon">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
              >
                <path d="M3 3v18h18" />
                <path d="M7 16l4-8 4 5 5-9" />
              </svg>
            </div>

            <div>
              <h2>CapForecast</h2>
              <span>Capacity Intelligence</span>
            </div>
          </div>

          <nav className="nav">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `nav-item${isActive ? " active" : ""}`
                }
              >
                <span className="nav-icon">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}

            {onHistoryClick && (
              <button
                type="button"
                className="nav-item nav-btn"
                onClick={onHistoryClick}
              >
                <span className="nav-icon">🕘</span>
                History

                {historyCount > 0 && (
                  <span className="nav-badge">
                    {historyCount}
                  </span>
                )}
              </button>
            )}
          </nav>

          <div className="sidebar-spacer" />

          <div className="sidebar-user">
            <div className="avatar">
              {(user?.name?.charAt(0) || "U").toUpperCase()}
            </div>

            <div className="sidebar-user-info">
              <strong>{user?.name || "User"}</strong>
              <p>{user?.email || ""}</p>
            </div>
          </div>

          <button
            type="button"
            className="sidebar-logout"
            onClick={logout}
          >
            Sign out
          </button>
        </aside>

        <main className="main">
          {children}
        </main>
      </div>
    </>
  );
}