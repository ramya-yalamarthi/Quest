/* MS-25: snapshot of how many actions are in each state.
 *
 * In a real wiring this reads a dedicated dashboard endpoint; for the MVP we
 * accept the counts from the parent so the panel can be exercised with the
 * existing 6-route surface (no new endpoint needed). */

export interface StateCountsProps {
  counts: Record<string, number>;
}

const ORDER = [
  "DRAFTED",
  "APPROVED",
  "STAGED",
  "VALIDATING",
  "PROMOTED",
  "FAILED",
  "EXPIRED",
  "REVERTED",
  "ROLLEDBACK",
  "CLOSED",
  "REJECTED",
];

export function StateCounts({ counts }: StateCountsProps) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8 }}>
      {ORDER.map((state) => (
        <div
          key={state}
          style={{
            border: "1px solid #e2e2e2",
            borderRadius: 8,
            padding: 12,
            background: counts[state] ? "#fafafa" : "#fff",
          }}
        >
          <div style={{ fontSize: 11, textTransform: "uppercase", color: "#888" }}>
            {state}
          </div>
          <div style={{ fontSize: 24, fontWeight: 600 }}>{counts[state] ?? 0}</div>
        </div>
      ))}
    </div>
  );
}
