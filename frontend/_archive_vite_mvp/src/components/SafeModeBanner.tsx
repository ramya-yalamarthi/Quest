import { SafeModeView } from "../api/mitigation";

export function SafeModeBanner({ data }: { data: SafeModeView | null }) {
  if (!data) {
    return (
      <div style={banner("#888")}>Safe Mode status loading…</div>
    );
  }
  const systemOn = data.system.active;
  const heldCategories = Object.entries(data.categories).filter(
    ([, v]) => v.active,
  );
  if (!systemOn && heldCategories.length === 0) {
    return <div style={banner("#1e7c2a")}>Safe Mode: OFF</div>;
  }
  const reason = systemOn
    ? data.system.reason
    : heldCategories[0]?.[1].reason;
  const entered_by = systemOn
    ? data.system.entered_by
    : heldCategories[0]?.[1].entered_by;
  return (
    <div style={banner("#b45309", "#fff7ed")}>
      <strong>Safe Mode: ON</strong>
      <span style={{ marginLeft: 12 }}>
        {systemOn ? "system" : heldCategories.map((c) => c[0]).join(", ")}
      </span>
      <span style={{ marginLeft: 12, color: "#666" }}>
        by {entered_by} — {reason}
      </span>
    </div>
  );
}

function banner(color: string, bg: string = "#fff"): React.CSSProperties {
  return {
    padding: "10px 14px",
    border: `1px solid ${color}`,
    borderRadius: 8,
    background: bg,
    color,
  };
}
