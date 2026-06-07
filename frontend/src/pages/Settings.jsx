import { useEffect, useState } from "react";
import API from "../services/api";
import AppLayout from "../components/AppLayout";
import { useQueryHistory } from "../hooks/useQueryHistory";
import { useSettings } from "../hooks/useSettings";

const TABS = [
  { id: "profile", label: "Profile", icon: "👤" },
  { id: "forecast", label: "Forecast", icon: "📈" },
  { id: "alerts", label: "Alerts", icon: "🔔" },
  { id: "appearance", label: "Appearance", icon: "🎨" },
  { id: "security", label: "Security", icon: "🔒" },
  { id: "data", label: "Data", icon: "💾" },
];

export default function Settings() {
  const { settings, loading, saveSettings } = useSettings();
  const { clearHistory } = useQueryHistory();
  const [activeTab, setActiveTab] = useState("profile");
  const [form, setForm] = useState(null);
  const [profile, setProfile] = useState({ name: "", email: "" });
  const [passwords, setPasswords] = useState({ current: "", new: "", confirm: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (settings) setForm({ ...settings, alert_thresholds: { ...settings.alert_thresholds } });
    const user = JSON.parse(localStorage.getItem("user") || "{}");
    setProfile({ name: user.name || "", email: user.email || "" });
  }, [settings]);

  const showToast = (text, isError = false) => {
    if (isError) {
      setError(text);
      setMessage("");
    } else {
      setMessage(text);
      setError("");
    }
    setTimeout(() => {
      setMessage("");
      setError("");
    }, 3500);
  };

  const updateForm = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const updateThreshold = (metric, value) => {
    setForm((prev) => ({
      ...prev,
      alert_thresholds: { ...prev.alert_thresholds, [metric]: Number(value) },
    }));
  };

  const applyThemePreview = (theme) => {
    document.documentElement.setAttribute("data-theme", theme);
  };

  const handleSavePreferences = async () => {
    try {
      setSaving(true);
      setError("");
      await saveSettings({
        forecast_days: Number(form.forecast_days),
        forecast_method: form.forecast_method,
        theme: form.theme,
        email_alerts: form.email_alerts,
        compact_mode: form.compact_mode,
        alert_thresholds: form.alert_thresholds,
        api_key: form.api_key,
      });
      showToast("Preferences saved successfully");
    } catch (err) {
      showToast(err.response?.data?.detail || "Failed to save settings", true);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveProfile = async () => {
    try {
      setSaving(true);
      setError("");
      const res = await API.put("/auth/profile", { name: profile.name });
      localStorage.setItem("user", JSON.stringify(res.data.user));
      setProfile((prev) => ({ ...prev, name: res.data.user.name }));
      showToast("Profile updated successfully");
    } catch (err) {
      showToast(err.response?.data?.detail || "Failed to update profile", true);
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async () => {
    if (passwords.new !== passwords.confirm) {
      showToast("New passwords do not match", true);
      return;
    }
    try {
      setSaving(true);
      setError("");
      await API.put("/auth/password", {
        current_password: passwords.current,
        new_password: passwords.new,
      });
      setPasswords({ current: "", new: "", confirm: "" });
      showToast("Password changed successfully");
    } catch (err) {
      showToast(err.response?.data?.detail || "Failed to change password", true);
    } finally {
      setSaving(false);
    }
  };

  const handleClearHistory = async () => {
    if (!window.confirm("Clear all saved forecast history?")) return;
    try {
      await clearHistory();
      showToast("Forecast history cleared");
    } catch (err) {
      showToast(err.response?.data?.detail || "Failed to clear history", true);
    }
  };

  if (loading || !form) {
    return (
      <AppLayout>
        <div className="settings-page">
          <div className="panel settings-loading">Loading settings...</div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="settings-page">
        <header className="settings-page-header">
          <div>
            <h1>Settings</h1>
            <p>Manage your account, forecasts, alerts, and workspace preferences.</p>
          </div>
        </header>

        {(message || error) && (
          <div className={`settings-toast ${error ? "error" : "success"}`}>
            {error || message}
          </div>
        )}

        <div className="settings-layout">
          <nav className="settings-tabs">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`settings-tab${activeTab === tab.id ? " active" : ""}`}
                onClick={() => setActiveTab(tab.id)}
              >
                <span className="settings-tab-icon">{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            ))}
          </nav>

          <div className="settings-content">
            {activeTab === "profile" && (
              <SettingsCard
                title="Profile"
                description="Update how your name appears across the application."
              >
                <div className="profile-hero">
                  <div className="profile-hero-avatar">{profile.name?.[0] || "U"}</div>
                  <div>
                    <strong>{profile.name || "User"}</strong>
                    <p>{profile.email}</p>
                  </div>
                </div>

                <SettingRow label="Display name" hint="Shown in sidebar and dashboard">
                  <input
                    className="input setting-input"
                    value={profile.name}
                    onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                  />
                </SettingRow>

                <SettingRow label="Email" hint="Account email (read-only)">
                  <input className="input setting-input" value={profile.email} disabled />
                </SettingRow>

                <div className="settings-actions">
                  <button type="button" className="button btn-inline" onClick={handleSaveProfile} disabled={saving}>
                    {saving ? "Saving..." : "Save Profile"}
                  </button>
                </div>
              </SettingsCard>
            )}

            {activeTab === "forecast" && (
              <SettingsCard
                title="Forecast Defaults"
                description="These values are used when you open the dashboard and run new predictions."
              >
                <SettingRow label="Forecast horizon" hint="Number of days to predict ahead (7–365)">
                  <input
                    className="input setting-input"
                    type="number"
                    min="7"
                    max="365"
                    value={form.forecast_days}
                    onChange={(e) => updateForm("forecast_days", e.target.value)}
                  />
                </SettingRow>

                <SettingRow label="Forecast engine" hint="Auto tries ARIMA first, then falls back to linear regression">
                  <select
                    className="input setting-input"
                    value={form.forecast_method}
                    onChange={(e) => updateForm("forecast_method", e.target.value)}
                  >
                    <option value="auto">Auto (ARIMA → Linear)</option>
                    <option value="linear">Linear Regression</option>
                    <option value="arima">ARIMA</option>
                  </select>
                </SettingRow>

                <SettingRow label="AI Assistant API Key" hint="Used for smart SRE insights (requires Google Gemini free tier API key)">
                  <input
                    className="input setting-input"
                    type="password"
                    placeholder="Enter GEMINI_API_KEY..."
                    value={form.api_key || ""}
                    onChange={(e) => updateForm("api_key", e.target.value)}
                  />
                </SettingRow>

                <div className="settings-preview-box">
                  <span>Current default</span>
                  <strong>{form.forecast_days} days · {form.forecast_method}</strong>
                </div>

                <div className="settings-actions">
                  <button type="button" className="button btn-inline" onClick={handleSavePreferences} disabled={saving}>
                    {saving ? "Saving..." : "Save Forecast Settings"}
                  </button>
                </div>
              </SettingsCard>
            )}

            {activeTab === "alerts" && (
              <SettingsCard
                title="Alert Thresholds"
                description="Set capacity warning levels used by health score and live alerts on the dashboard."
              >
                <ThresholdRow
                  label="CPU"
                  color="#2563eb"
                  value={form.alert_thresholds.cpu_usage}
                  onChange={(v) => updateThreshold("cpu_usage", v)}
                />
                <ThresholdRow
                  label="Memory"
                  color="#7c3aed"
                  value={form.alert_thresholds.memory_usage}
                  onChange={(v) => updateThreshold("memory_usage", v)}
                />
                <ThresholdRow
                  label="Disk"
                  color="#ea580c"
                  value={form.alert_thresholds.disk_usage}
                  onChange={(v) => updateThreshold("disk_usage", v)}
                />

                <div className="settings-actions">
                  <button type="button" className="button btn-inline" onClick={handleSavePreferences} disabled={saving}>
                    {saving ? "Saving..." : "Save Alert Thresholds"}
                  </button>
                </div>
              </SettingsCard>
            )}

            {activeTab === "appearance" && (
              <SettingsCard
                title="Appearance"
                description="Customize the look and feel. Theme changes preview instantly."
              >
                <Toggle
                  label="Dark mode"
                  hint="Switch between light and dark workspace theme"
                  checked={form.theme === "dark"}
                  onChange={(checked) => {
                    const theme = checked ? "dark" : "light";
                    updateForm("theme", theme);
                    applyThemePreview(theme);
                  }}
                />
                <Toggle
                  label="Compact dashboard"
                  hint="Hide overview chart and use a tighter layout"
                  checked={form.compact_mode}
                  onChange={(checked) => updateForm("compact_mode", checked)}
                />
                <Toggle
                  label="Email alerts"
                  hint="Demo toggle for future email notifications"
                  checked={form.email_alerts}
                  onChange={(checked) => updateForm("email_alerts", checked)}
                />

                <div className="settings-preview-box theme-preview">
                  <span>Theme preview</span>
                  <div className={`theme-preview-chip ${form.theme}`}>
                    {form.theme === "dark" ? "Dark theme active" : "Light theme active"}
                  </div>
                </div>

                <div className="settings-actions">
                  <button type="button" className="button green btn-inline" onClick={handleSavePreferences} disabled={saving}>
                    {saving ? "Saving..." : "Save Appearance"}
                  </button>
                </div>
              </SettingsCard>
            )}

            {activeTab === "security" && (
              <SettingsCard
                title="Security"
                description="Change your password to keep your account secure."
              >
                <SettingRow label="Current password">
                  <input
                    className="input setting-input"
                    type="password"
                    value={passwords.current}
                    onChange={(e) => setPasswords({ ...passwords, current: e.target.value })}
                  />
                </SettingRow>
                <SettingRow label="New password" hint="Minimum 6 characters">
                  <input
                    className="input setting-input"
                    type="password"
                    value={passwords.new}
                    onChange={(e) => setPasswords({ ...passwords, new: e.target.value })}
                  />
                </SettingRow>
                <SettingRow label="Confirm new password">
                  <input
                    className="input setting-input"
                    type="password"
                    value={passwords.confirm}
                    onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })}
                  />
                </SettingRow>

                <div className="settings-actions">
                  <button type="button" className="button btn-inline" onClick={handleChangePassword} disabled={saving}>
                    {saving ? "Updating..." : "Change Password"}
                  </button>
                </div>
              </SettingsCard>
            )}

            {activeTab === "data" && (
              <SettingsCard
                title="Data & History"
                description="Manage saved forecast history stored on the server."
              >
                <div className="data-info-card">
                  <div>
                    <strong>Forecast history file</strong>
                    <p>Each forecast is saved automatically and shown in the dashboard sidebar.</p>
                  </div>
                  <span className="badge muted">SQLite Database</span>
                </div>

                <div className="settings-actions danger-zone">
                  <div>
                    <strong>Clear history</strong>
                    <p>Permanently remove all saved forecasts from your history file.</p>
                  </div>
                  <button type="button" className="button danger-btn" onClick={handleClearHistory}>
                    Clear History
                  </button>
                </div>
              </SettingsCard>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}

function SettingsCard({ title, description, children }) {
  return (
    <section className="settings-card panel">
      <header className="settings-card-header">
        <h2>{title}</h2>
        <p>{description}</p>
      </header>
      <div className="settings-card-body">{children}</div>
    </section>
  );
}

function SettingRow({ label, hint, children }) {
  return (
    <div className="setting-row">
      <div className="setting-row-label">
        <strong>{label}</strong>
        {hint && <span>{hint}</span>}
      </div>
      <div className="setting-row-control">{children}</div>
    </div>
  );
}

function ThresholdRow({ label, color, value, onChange }) {
  return (
    <div className="threshold-row">
      <div className="threshold-row-label">
        <span className="threshold-dot" style={{ background: color }} />
        <strong>{label}</strong>
      </div>
      <div className="threshold-row-control">
        <input
          className="input setting-input threshold-input"
          type="range"
          min="50"
          max="100"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <span className="threshold-value">{value}%</span>
      </div>
    </div>
  );
}

function Toggle({ label, hint, checked, onChange }) {
  return (
    <label className="toggle-switch">
      <div className="toggle-switch-text">
        <strong>{label}</strong>
        {hint && <span>{hint}</span>}
      </div>
      <div className="toggle-switch-ui">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="toggle-track" />
      </div>
    </label>
  );
}
