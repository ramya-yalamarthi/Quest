import { CheckResult } from "../api/mitigation";

const STATUS_COLOR: Record<string, string> = {
  PASS: "#1e7c2a",
  FAIL: "#b00020",
  PENDING: "#a16207",
};

export function PerCheckStatus({ checks }: { checks: CheckResult[] }) {
  if (!checks.length) {
    return <div style={{ color: "#888" }}>No checks reported yet.</div>;
  }
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ textAlign: "left", color: "#666", fontSize: 12 }}>
          <th style={{ padding: 6 }}>Check</th>
          <th style={{ padding: 6 }}>Status</th>
          <th style={{ padding: 6 }}>Detail</th>
          <th style={{ padding: 6 }}>Evaluated</th>
        </tr>
      </thead>
      <tbody>
        {checks.map((c) => (
          <tr key={c.name} style={{ borderTop: "1px solid #eee" }}>
            <td style={{ padding: 6, fontFamily: "monospace" }}>{c.name}</td>
            <td style={{ padding: 6, color: STATUS_COLOR[c.status] }}>
              {c.status}
            </td>
            <td style={{ padding: 6, color: "#444" }}>{c.detail ?? ""}</td>
            <td style={{ padding: 6, color: "#888", fontSize: 12 }}>
              {c.evaluated_at ?? ""}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
