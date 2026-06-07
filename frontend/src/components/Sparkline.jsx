import { Line, LineChart, ResponsiveContainer } from "recharts";

export default function Sparkline({ data, color = "#2563eb" }) {
  if (!data?.length) return <div className="sparkline-empty">—</div>;

  return (
    <div className="sparkline">
      <ResponsiveContainer width="100%" height={40}>
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
