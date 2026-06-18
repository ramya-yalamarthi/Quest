import { useState } from "react";
import { mutateSafeMode, SafeModeView } from "../api/mitigation";

/* Exit a held scope. MS-22 enforces human-only at the server too, so a user
 * who lacks the `mitigation:safemode` scope will get a 403 here. */
export function SafeModeToggle({
  data,
  onChange,
}: {
  data: SafeModeView | null;
  onChange: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!data) return null;
  const scopes: { scope: string; active: boolean; label: string }[] = [
    { scope: "system", active: data.system.active, label: "system" },
    ...Object.entries(data.categories).map(([scope, v]) => ({
      scope,
      active: v.active,
      label: scope,
    })),
  ];

  async function toggle(scope: string, currentlyActive: boolean) {
    if (!reason.trim()) {
      setError("reason is required");
      return;
    }
    if (!confirm(`${currentlyActive ? "Exit" : "Enter"} Safe Mode for ${scope}?`)) {
      return;
    }
    setBusy(scope);
    setError(null);
    try {
      await mutateSafeMode(scope, !currentlyActive, reason);
      onChange();
      setReason("");
    } catch (e: any) {
      setError(e?.body?.detail?.msg ?? e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input
          type="text"
          placeholder="reason (required)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          style={{ flex: 1, padding: "6px 8px", border: "1px solid #ccc", borderRadius: 4 }}
        />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
        {scopes.map((s) => (
          <div
            key={s.scope}
            style={{
              border: "1px solid #e2e2e2",
              borderRadius: 6,
              padding: 8,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontFamily: "monospace" }}>{s.label}</span>
            <button
              onClick={() => toggle(s.scope, s.active)}
              disabled={busy === s.scope}
              style={{
                padding: "4px 10px",
                borderRadius: 4,
                border: "1px solid #999",
                background: s.active ? "#fee2e2" : "#dcfce7",
                cursor: "pointer",
              }}
            >
              {busy === s.scope
                ? "…"
                : s.active
                  ? "Exit"
                  : "Enter"}
            </button>
          </div>
        ))}
      </div>
      {error && (
        <div style={{ marginTop: 8, color: "#b00020", fontSize: 13 }}>{error}</div>
      )}
    </div>
  );
}
