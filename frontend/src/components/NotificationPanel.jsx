import { useEffect, useRef, useState } from "react";

export default function NotificationPanel({ alerts = [], onRefresh }) {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState([]);
  const panelRef = useRef(null);

  const visible = alerts.filter((a) => !dismissed.includes(a.metric));
  const count = visible.length;

  useEffect(() => {
    const handleClick = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const dismiss = (metric) => {
    setDismissed((prev) => [...prev, metric]);
  };

  const dismissAll = () => {
    setDismissed(alerts.map((a) => a.metric));
    setOpen(false);
  };

  return (
    <div className="notification-wrap" ref={panelRef}>
      <button
        type="button"
        className="icon-btn notification-btn"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {count > 0 && <span className="notification-badge">{count}</span>}
      </button>

      {open && (
        <div className="notification-dropdown">
          <div className="notification-dropdown-header">
            <strong>Alerts</strong>
            <div className="notification-dropdown-actions">
              {onRefresh && (
                <button type="button" className="text-btn" onClick={onRefresh}>
                  Refresh
                </button>
              )}
              {count > 0 && (
                <button type="button" className="text-btn" onClick={dismissAll}>
                  Dismiss all
                </button>
              )}
            </div>
          </div>

          {count === 0 ? (
            <p className="notification-empty">No active alerts. All systems healthy.</p>
          ) : (
            <ul className="notification-list">
              {visible.map((alert) => (
                <li key={alert.metric} className={`notification-item ${alert.status}`}>
                  <div>
                    <strong>{alert.label}</strong>
                    <p>{alert.message}</p>
                  </div>
                  <button type="button" className="notif-dismiss" onClick={() => dismiss(alert.metric)}>
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
