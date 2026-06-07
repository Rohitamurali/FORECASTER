function formatTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function metricLabel(metric) {
  if (!metric) return "Forecast";
  return metric.replace("_usage", "").toUpperCase();
}

export default function HistoryDrawer({
  open,
  onClose,
  items,
  loading,
  activeId,
  onSelect,
  onClear,
  onRemove,
}) {
  if (!open) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside className="history-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="history-drawer-header">
          <div>
            <h2>Forecast History</h2>
            <p>{items.length} saved predictions</p>
          </div>
          <button type="button" className="drawer-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="history-drawer-toolbar">
          <span className="badge muted">Click any entry to restore chart & answer</span>
          {items.length > 0 && (
            <button type="button" className="text-btn danger-text" onClick={onClear}>
              Clear all
            </button>
          )}
        </div>

        <div className="history-drawer-list">
          {loading && <p className="history-drawer-empty">Loading history...</p>}

          {!loading && items.length === 0 && (
            <div className="history-drawer-empty-state">
              <div className="empty-icon">📋</div>
              <h3>No history yet</h3>
              <p>Run a forecast and it will appear here automatically.</p>
            </div>
          )}

          {!loading &&
            items.map((item) => (
              <div
                key={item.id}
                className={`history-drawer-item${activeId === item.id ? " active" : ""}`}
                onClick={() => {
                  onSelect(item);
                  onClose();
                }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && (onSelect(item), onClose())}
              >
                <div className="history-drawer-item-top">
                  <span className={`metric-pill pill-${item.metric}`}>{metricLabel(item.metric)}</span>
                  <button
                    type="button"
                    className="history-remove-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemove(item.id);
                    }}
                  >
                    ×
                  </button>
                </div>
                <p className="history-drawer-question">{item.question}</p>
                <p className="history-drawer-answer">{item.answer}</p>
                <div className="history-drawer-meta">
                  <span>{item.crossing_date ? `Crossing: ${item.crossing_date}` : "No threshold crossing"}</span>
                  <span>{formatTime(item.created_at)}</span>
                </div>
              </div>
            ))}
        </div>
      </aside>
    </div>
  );
}
