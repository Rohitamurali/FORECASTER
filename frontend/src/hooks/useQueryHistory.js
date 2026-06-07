import { useCallback, useEffect, useState } from "react";
import API from "../services/api";

export function useQueryHistory() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fileName, setFileName] = useState("");

  const loadHistory = useCallback(async () => {
    try {
      const res = await API.get("/history");
      setItems(res.data.items || []);
      setFileName(res.data.file || "");
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const clearHistory = async () => {
    await API.delete("/history");
    setItems([]);
  };

  const removeItem = async (id) => {
    await API.delete(`/history/${id}`);
    setItems((prev) => prev.filter((item) => item.id !== id));
  };

  return {
    items,
    loading,
    fileName,
    reload: loadHistory,
    clearHistory,
    removeItem,
  };
}
