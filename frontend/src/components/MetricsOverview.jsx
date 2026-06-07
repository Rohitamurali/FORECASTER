import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function MetricsOverview({ trends }) {
  if (!trends) return null;

  const dates = trends.cpu_usage?.map((d) => d.date) || [];
  const chartData = dates.map((date, i) => ({
    date,
    cpu: trends.cpu_usage[i]?.value,
    memory: trends.memory_usage[i]?.value,
    disk: trends.disk_usage[i]?.value,
  }));

  return (
    <div className="chart-wrap overview-chart">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="cpu" name="CPU" stroke="#2563eb" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="memory" name="Memory" stroke="#7c3aed" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="disk" name="Disk" stroke="#ea580c" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
