/* MS-25: rollback rate over the rolling window.
 *
 * Receives the precomputed rate from the parent so this component is purely
 * presentational. */
export function RollbackRate({ rate, threshold }: { rate: number; threshold: number }) {
  const breached = rate >= threshold && threshold > 0;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 8,
        padding: "8px 12px",
        border: "1px solid #e2e2e2",
        borderRadius: 8,
        background: breached ? "#fff5f5" : "#fff",
      }}
    >
      <div style={{ fontSize: 11, color: "#888", textTransform: "uppercase" }}>
        rollback rate
      </div>
      <div style={{ fontSize: 20, fontWeight: 600 }}>
        {(rate * 100).toFixed(1)}%
      </div>
      <div style={{ fontSize: 12, color: "#888" }}>
        / threshold {(threshold * 100).toFixed(0)}%
      </div>
    </div>
  );
}
