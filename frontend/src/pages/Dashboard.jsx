import { useEffect, useRef, useState } from "react";
import API from "../services/api";
import AppLayout from "../components/AppLayout";
import ForecastChart from "../components/ForecastChart";
import HistoryDrawer from "../components/HistoryDrawer";
import MetricsOverview from "../components/MetricsOverview";
import NotificationPanel from "../components/NotificationPanel";
import Sparkline from "../components/Sparkline";
import { useQueryHistory } from "../hooks/useQueryHistory";
import { useSettings } from "../hooks/useSettings";

const SUGGESTIONS = [
  "When does disk hit 80%?",
  "When will CPU reach 90%?",
  "When will memory reach 75%?",
];

const METRIC_COLORS = {
  cpu_usage: "#2563eb",
  memory_usage: "#7c3aed",
  disk_usage: "#ea580c",
};

export default function Dashboard() {
  const { settings } = useSettings();
  const {
    items: historyItems,
    loading: historyLoading,
    reload: reloadHistory,
    clearHistory,
    removeItem,
  } = useQueryHistory();

  const [summary, setSummary] = useState(null);
  const [health, setHealth] = useState(null);
  const [trends, setTrends] = useState(null);
  const [scanResults, setScanResults] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [question, setQuestion] = useState("When does disk hit 80%?");
  const [days, setDays] = useState(60);
  const [method, setMethod] = useState("auto");
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const chatEndRef = useRef(null);

  const loadDashboard = async () => {
    const [summaryRes, healthRes, trendsRes] = await Promise.all([
      API.get("/metrics/summary"),
      API.get("/metrics/health"),
      API.get("/metrics/trends"),
    ]);
    setSummary(summaryRes.data);
    setHealth(healthRes.data);
    setTrends(trendsRes.data);
    setLastUpdated(new Date());
  };

  useEffect(() => {
    loadDashboard();
    const interval = setInterval(loadDashboard, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (settings) {
      setDays(settings.forecast_days);
      setMethod(settings.forecast_method);
    }
  }, [settings]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const askForecast = async (customQuestion) => {
    const query = (customQuestion || question).trim();
    if (!query) return;

    try {
      setLoading(true);
      setError("");
      setQuestion(query);
      setMessages((prev) => [...prev, { role: "user", text: query }]);

      const res = await API.post("/forecast/predict", {
        question: query,
        forecast_days: Number(days),
        method,
      });

      if (res.data.metric && res.data.metric !== "none" && res.data.forecast?.length > 0) {
        setResult(res.data);
      }
      setActiveHistoryId(res.data.history_id || null);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: res.data.answer, data: res.data },
      ]);
      reloadHistory().catch(() => {});
    } catch (err) {
      const detail = err.response?.data?.detail;
      let msg = Array.isArray(detail)
        ? detail.map((d) => d.msg).join(", ")
        : detail || err.response?.data?.message;
      if (!msg && !err.response) {
        msg = "Cannot reach server. Ensure the backend is running.";
      }
      if (!msg) msg = err.message || "Forecast failed";
      setError(msg);
      setMessages((prev) => [...prev, { role: "assistant", text: msg, error: true }]);
    } finally {
      setLoading(false);
    }
  };

  const runQuickScan = async () => {
    try {
      setScanning(true);
      const res = await API.post("/forecast/quick-scan");
      setScanResults(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Quick scan failed");
    } finally {
      setScanning(false);
    }
  };

  const uploadCsv = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setUploading(true);
      setError("");
      const formData = new FormData();
      formData.append("file", file);
      const res = await API.post("/upload/csv", formData);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `Dataset updated — ${res.data.rows} rows imported from ${file.name}.` },
      ]);
      await loadDashboard();
    } catch (err) {
      setError(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const loadHistoryItem = (item) => {
    setQuestion(item.question);
    setActiveHistoryId(item.id);
    setResult({
      metric: item.metric,
      threshold: item.threshold,
      answer: item.answer,
      crossing_date: item.crossing_date,
      forecast_engine: item.forecast_engine,
      history: item.history,
      forecast: item.forecast,
      agent_steps: item.agent_steps,
    });
    setMessages([
      { role: "user", text: item.question },
      { role: "assistant", text: item.answer, data: item },
    ]);
    setError("");
  };

  const handleClearHistory = async () => {
    if (!window.confirm("Clear all saved forecast history?")) return;
    await clearHistory();
    setActiveHistoryId(null);
  };

  const handleRemoveHistory = async (id) => {
    await removeItem(id);
    if (activeHistoryId === id) setActiveHistoryId(null);
  };

  const exportForecast = () => {
    if (!result?.forecast) return;
    const rows = [
      ["date", "predicted_usage", "metric", "threshold"],
      ...result.forecast.map((f) => [f.date, f.predicted_usage, result.metric, result.threshold]),
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `forecast-${result.metric}-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const latest = summary?.latest || {};
  const compact = settings?.compact_mode;

  return (
    <AppLayout
      onHistoryClick={() => setHistoryOpen(true)}
      historyCount={historyItems.length}
    >
      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        items={historyItems}
        loading={historyLoading}
        activeId={activeHistoryId}
        onSelect={loadHistoryItem}
        onClear={handleClearHistory}
        onRemove={handleRemoveHistory}
      />

      <header className="app-header">
        <div>
          <h1>Overview</h1>
          <p>
            Infrastructure capacity monitoring
            {lastUpdated && (
              <span className="live-dot">
                · Updated {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </p>
        </div>
        <div className="app-header-actions">
          <NotificationPanel alerts={health?.alerts || []} onRefresh={loadDashboard} />
          <button type="button" className="header-btn" onClick={runQuickScan} disabled={scanning}>
            {scanning ? "Scanning..." : "Run Scan"}
          </button>
          <button type="button" className="header-btn outline" onClick={() => setHistoryOpen(true)}>
            History {historyItems.length > 0 && `(${historyItems.length})`}
          </button>
          <label className="header-btn primary">
            {uploading ? "Uploading..." : "Import CSV"}
            <input type="file" accept=".csv" onChange={uploadCsv} hidden />
          </label>
        </div>
      </header>

      <section className="status-strip">
        <StatusPill label="Health" value={health?.grade || "—"} tone={health?.grade} />
        <StatusPill label="Score" value={health?.score != null ? `${health.score}/100` : "—"} />
        <StatusPill label="Alerts" value={health?.alerts?.length || 0} alert={health?.alerts?.length > 0} />
        <StatusPill label="Dataset" value={`${summary?.rows || 0} rows`} />
        <StatusPill
          label="Range"
          value={
            summary?.date_range
              ? `${summary.date_range.start} → ${summary.date_range.end}`
              : "—"
          }
        />
      </section>

      <section className="health-row">
        <div className="health-score-card">
          <span className="kpi-label">System Health</span>
          <div className="health-score">
            {health?.score ?? "—"}
            <small>/ 100</small>
          </div>
          <span className={`health-grade grade-${health?.grade?.toLowerCase().replace(" ", "-")}`}>
            {health?.grade || "Loading"}
          </span>
        </div>

        <div className="alerts-panel">
          <div className="panel-header compact-header">
            <h2>Active Alerts</h2>
            <span className="badge">{health?.alerts?.length || 0}</span>
          </div>
          {health?.alerts?.length ? (
            <ul className="alert-list">
              {health.alerts.map((alert) => (
                <li key={alert.metric} className={`alert-item ${alert.status}`}>
                  <strong>{alert.label}</strong>
                  <span>{alert.message}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="no-alerts">All metrics are within configured thresholds.</p>
          )}
        </div>

        {!compact && (
          <div className="dataset-panel">
            <span className="kpi-label">Data Coverage</span>
            <strong>{summary?.rows || 0} records</strong>
            <p>
              {summary?.date_range?.start} → {summary?.date_range?.end}
            </p>
          </div>
        )}
      </section>

      <section className="kpi-grid">
        <Kpi label="CPU" value={latest.cpu_usage} avg={summary?.averages?.cpu_usage} unit="%" color={METRIC_COLORS.cpu_usage} trend={trends?.cpu_usage} />
        <Kpi label="Memory" value={latest.memory_usage} avg={summary?.averages?.memory_usage} unit="%" color={METRIC_COLORS.memory_usage} trend={trends?.memory_usage} />
        <Kpi label="Disk" value={latest.disk_usage} avg={summary?.averages?.disk_usage} unit="%" color={METRIC_COLORS.disk_usage} trend={trends?.disk_usage} />
        <Kpi label="Records" value={summary?.rows || 0} unit="" color="#059669" />
      </section>

      {scanResults && (
        <section className="panel scan-panel">
          <div className="panel-header">
            <h2>Capacity Scan</h2>
            <span className="badge muted">{scanResults.scanned_at}</span>
          </div>
          <div className="scan-grid">
            {scanResults.scan_results.map((item) => (
              <div key={item.metric} className={`scan-card risk-${item.risk}`}>
                <strong>{item.label}</strong>
                <span>{item.current}% current</span>
                <p>{item.answer}</p>
                <small>{item.engine}</small>
              </div>
            ))}
          </div>
        </section>
      )}

      {!compact && trends && (
        <section className="panel overview-panel">
          <div className="panel-header">
            <h2>Usage Trends — 30 Days</h2>
          </div>
          <MetricsOverview trends={trends} />
        </section>
      )}

      <section className="workspace">
        <div className="panel chat-panel">
          <div className="panel-header">
            <h2>Ask CapForecast</h2>
            <span className="badge">AI Assistant</span>
          </div>

          <div className="chat-window">
            {messages.length === 0 && (
              <div className="empty-chat">
                <h3>What would you like to forecast?</h3>
                <p>Type a question about CPU, memory, or disk capacity.</p>
                <div className="chips">
                  {SUGGESTIONS.map((item) => (
                    <button key={item} type="button" className="chip" onClick={() => askForecast(item)}>
                      {item}
                    </button>
                  ))}
                </div>
                <p className="empty-history-hint">
                  Past predictions are saved — open <button type="button" className="inline-link" onClick={() => setHistoryOpen(true)}>History</button> to revisit them.
                </p>
              </div>
            )}

            {messages.map((msg, index) => (
              <div key={index} className={`bubble ${msg.role} ${msg.error ? "error-bubble" : ""}`}>
                <span className="bubble-label">{msg.role === "user" ? "You" : "CapForecast"}</span>
                <div className="markdown-container">
                  <Markdown text={msg.text} />
                </div>
                {msg.data?.agent_steps && (
                  <ul className="agent-steps">
                    {msg.data.agent_steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}

            {loading && (
              <div className="bubble assistant">
                <span className="bubble-label">CapForecast</span>
                <p className="typing">Running forecast analysis...</p>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="composer">
            <div className="composer-options">
              <label>
                Horizon (days)
                <input type="number" min="7" max="365" value={days} onChange={(e) => setDays(e.target.value)} />
              </label>
              <label>
                Model
                <select value={method} onChange={(e) => setMethod(e.target.value)}>
                  <option value="auto">Auto</option>
                  <option value="linear">Linear Regression</option>
                  <option value="arima">ARIMA</option>
                </select>
              </label>
            </div>

            <div className="composer-row">
              <input
                className="input chat-input"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && askForecast()}
                placeholder="e.g. When will disk usage reach 80%?"
              />
              <button type="button" className="button" onClick={() => askForecast()} disabled={loading}>
                {loading ? "Analyzing..." : "Forecast"}
              </button>
            </div>

            {error && <div className="error inline-error">{error}</div>}
          </div>
        </div>

        <div className="panel chart-panel">
          <div className="panel-header">
            <h2>Prediction Chart</h2>
            <div className="chart-actions">
              {result && result.metric && result.metric !== "none" && (
                <button type="button" className="text-btn" onClick={exportForecast}>
                  Export
                </button>
              )}
              {result && result.metric && result.metric !== "none" && <span className="badge muted">{result.forecast_engine}</span>}
            </div>
          </div>

          {result && result.metric && result.metric !== "none" && result.forecast && result.forecast.length > 0 ? (
            <>
              <div className="result-banner">
                <Markdown text={result.answer} />
              </div>
              <ForecastChart
                history={result.history}
                forecast={result.forecast}
                threshold={result.threshold}
                metric={result.metric?.replace("_usage", "")}
              />
              <div className="forecast-meta">
                <div><span>Metric</span><strong>{result.metric}</strong></div>
                <div><span>Threshold</span><strong>{result.threshold}%</strong></div>
                <div><span>Crossing</span><strong>{result.crossing_date || "Not in range"}</strong></div>
              </div>
            </>
          ) : (
            <div className="chart-placeholder">
              <p>Run a forecast to view usage trends and predictions.</p>
            </div>
          )}
        </div>
      </section>
    </AppLayout>
  );
}

function Kpi({ label, value, avg, unit, color, trend }) {
  return (
    <div className="kpi-card" style={{ borderTopColor: color }}>
      <span className="kpi-label">{label}</span>
      <div className="kpi-value">
        {value ?? "-"}
        {unit && <small>{unit}</small>}
      </div>
      {avg !== undefined && <span className="kpi-avg">Avg {avg}{unit}</span>}
      {trend && <Sparkline data={trend} color={color} />}
    </div>
  );
}

function Markdown({ text }) {
  if (!text) return null;

  const lines = text.split("\n");
  const elements = [];
  let listItems = [];
  let keyCounter = 0;

  const parseInline = (str) => {
    const parts = [];
    const regex = /\*\*(.*?)\*\*/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(str)) !== null) {
      if (match.index > lastIndex) {
        parts.push(str.substring(lastIndex, match.index));
      }
      parts.push(<strong key={keyCounter++}>{match[1]}</strong>);
      lastIndex = regex.lastIndex;
    }

    if (lastIndex < str.length) {
      parts.push(str.substring(lastIndex));
    }

    return parts.length > 0 ? parts : str;
  };

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`ul-${keyCounter++}`} className="markdown-ul">
          {listItems.map((item, idx) => (
            <li key={`li-${keyCounter++}-${idx}`} className="markdown-li">
              {parseInline(item)}
            </li>
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  for (let line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      elements.push(<div key={`br-${keyCounter++}`} className="markdown-spacer" />);
      continue;
    }

    // Horizontal Rule
    if (trimmed === "---" || trimmed === "***" || trimmed === "___") {
      flushList();
      elements.push(<hr key={`hr-${keyCounter++}`} className="markdown-hr" />);
      continue;
    }

    // Headings
    if (trimmed.startsWith("### ")) {
      flushList();
      elements.push(
        <h3 key={`h3-${keyCounter++}`} className="markdown-h3">
          {parseInline(trimmed.substring(4))}
        </h3>
      );
    } else if (trimmed.startsWith("## ")) {
      flushList();
      elements.push(
        <h2 key={`h2-${keyCounter++}`} className="markdown-h2">
          {parseInline(trimmed.substring(3))}
        </h2>
      );
    } else if (trimmed.startsWith("# ")) {
      flushList();
      elements.push(
        <h1 key={`h1-${keyCounter++}`} className="markdown-h1">
          {parseInline(trimmed.substring(2))}
        </h1>
      );
    }
    // List items
    else if (trimmed.startsWith("* ") || trimmed.startsWith("- ")) {
      const content = trimmed.substring(2).trim();
      listItems.push(content);
    }
    // Plain paragraph
    else {
      flushList();
      elements.push(
        <p key={`p-${keyCounter++}`} className="markdown-p">
          {parseInline(trimmed)}
        </p>
      );
    }
  }

  flushList();
  return <>{elements}</>;
}

function StatusPill({ label, value, tone, alert }) {
  return (
    <div className={`status-pill${alert ? " alert" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
