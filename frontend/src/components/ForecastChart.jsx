import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function ForecastChart({ history, forecast, threshold, metric }) {
  const historyData = (history || []).map((item) => ({
    date: item.date,
    actual: item.usage,
    predicted: null,
  }));

  const forecastData = (forecast || []).map((item) => ({
    date: item.date,
    actual: null,
    predicted: item.predicted_usage,
  }));

  const chartData = [...historyData, ...forecastData];

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11 }}
            tickFormatter={(value) => value.slice(5)}
          />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
          <Tooltip
            contentStyle={{
              borderRadius: 12,
              border: "1px solid #e2e8f0",
              boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
            }}
          />
          <Legend />
          <ReferenceLine
            y={threshold}
            stroke="#ef4444"
            strokeDasharray="6 4"
            label={`Threshold ${threshold}%`}
          />
          <Line
            type="monotone"
            dataKey="actual"
            name={`Historical ${metric}`}
            stroke="#2563eb"
            strokeWidth={2.5}
            dot={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="predicted"
            name="Forecast"
            stroke="#16a34a"
            strokeWidth={2.5}
            strokeDasharray="6 4"
            dot={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
