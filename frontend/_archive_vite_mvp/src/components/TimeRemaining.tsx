function fmt(seconds: number): string {
  if (seconds <= 0) return "0s";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h}h ${m}m ${s}s`;
}

export function TimeRemaining({
  elapsed,
  remaining,
}: {
  elapsed: number;
  remaining: number;
}) {
  const total = elapsed + remaining;
  const pct = total ? Math.min(100, (elapsed / total) * 100) : 0;
  return (
    <div>
      <div style={{ fontSize: 12, color: "#666" }}>
        elapsed {fmt(elapsed)} · remaining {fmt(remaining)}
      </div>
      <div
        style={{
          marginTop: 4,
          height: 6,
          background: "#eee",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            background: pct > 90 ? "#b00020" : "#1976d2",
            height: "100%",
          }}
        />
      </div>
    </div>
  );
}
