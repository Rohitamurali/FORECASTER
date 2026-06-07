import { useCallback, useEffect, useState } from "react";
import API from "../services/api";

export function useSettings() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadSettings = useCallback(async () => {
    try {
      const res = await API.get("/settings");
      setSettings(res.data);
      document.documentElement.setAttribute("data-theme", res.data.theme || "light");
    } catch {
      document.documentElement.setAttribute("data-theme", "light");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const saveSettings = async (updates) => {
    const res = await API.put("/settings", updates);
    setSettings(res.data.settings);
    if (updates.theme) {
      document.documentElement.setAttribute("data-theme", updates.theme);
    }
    return res.data;
  };

  return { settings, loading, saveSettings, reload: loadSettings };
}
