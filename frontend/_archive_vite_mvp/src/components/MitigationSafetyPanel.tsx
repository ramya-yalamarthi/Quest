import { useState } from "react";
import { promote, revert } from "../api/mitigation";
import { useSafeMode } from "../hooks/useSafeMode";
import { useValidation } from "../hooks/useValidation";
import { PerCheckStatus } from "./PerCheckStatus";
import { RollbackRate } from "./RollbackRate";
import { SafeModeBanner } from "./SafeModeBanner";
import { SafeModeToggle } from "./SafeModeToggle";
import { StateCounts } from "./StateCounts";
import { TimeRemaining } from "./TimeRemaining";

/* MS-25: top-level panel.
 *
 * Inputs:
 *   - ticketId / actionId  -- user picks which mitigation to inspect
 *   - state counts + rollback rate are read from props that the surrounding
 *     app populates (in this MVP we accept manual entry to keep the surface
 *     limited to the 6 ratified endpoints).
 */

export function MitigationSafetyPanel() {
  const [ticketId, setTicketId] = useState<string>("");
  const [actionId, setActionId] = useState<string>("");
  const { data: validation, error: vError } = useValidation(ticketId || null);
  const { data: safeMode, refresh: refreshSafeMode } = useSafeMode();

  // Counts + rate are operator-supplied in this MVP. Wire to a future
  // /mitigation/health endpoint when it lands.
  const [counts] = useState<Record<string, number>>({
    DRAFTED: 0,
    APPROVED: 0,
    STAGED: 0,
    VALIDATING: validation && validation.overall_status === "PENDING" ? 1 : 0,
    PROMOTED: 0,
    FAILED: validation?.overall_status === "FAIL" ? 1 : 0,
    EXPIRED: validation?.overall_status === "EXPIRED" ? 1 : 0,
    REVERTED: 0,
    ROLLEDBACK: 0,
    CLOSED: 0,
    REJECTED: 0,
  });
  const [rollbackRate] = useState<{ rate: number; threshold: number }>({
    rate: 0,
    threshold: 0.1,
  });

  async function onPromote() {
    if (!ticketId || !actionId) return alert("ticketId + actionId required");
    try {
      const result = await promote(ticketId, actionId, true);
      alert(`promoted; rollback window ends ${result.rollback_window_end}`);
    } catch (e: any) {
      alert(`promote failed: ${e?.body?.detail?.msg ?? e.message}`);
    }
  }

  async function onRevert() {
    if (!ticketId || !actionId) return alert("ticketId + actionId required");
    const reason = prompt("revert reason?");
    if (!reason) return;
    try {
      const result = await revert(ticketId, actionId, reason);
      alert(
        `${result.state}${result.idempotent ? " (idempotent re-issue)" : ""}`,
      );
    } catch (e: any) {
      alert(`revert failed: ${e?.body?.detail?.msg ?? e.message}`);
    }
  }

  return (
    <div style={{ display: "grid", gap: 16, marginTop: 16 }}>
      <SafeModeBanner data={safeMode} />

      <section style={card("Mitigation actions by state (MS-25)")}>
        <StateCounts counts={counts} />
      </section>

      <section style={card("Pick an action")}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={ticketId}
            onChange={(e) => setTicketId(e.target.value)}
            placeholder="ticket_id (UUID)"
            style={input()}
          />
          <input
            value={actionId}
            onChange={(e) => setActionId(e.target.value)}
            placeholder="action_id (UUID)"
            style={input()}
          />
          <button onClick={onPromote} style={btn()}>
            Promote
          </button>
          <button onClick={onRevert} style={btn("#fee2e2")}>
            Revert
          </button>
        </div>
      </section>

      <section style={card("Validation window")}>
        {vError && (
          <div style={{ color: "#b00020" }}>Error: {vError}</div>
        )}
        {validation ? (
          <>
            <div style={{ marginBottom: 8 }}>
              overall_status:{" "}
              <strong>{validation.overall_status}</strong>
            </div>
            <TimeRemaining
              elapsed={validation.elapsed_seconds}
              remaining={validation.time_remaining_seconds}
            />
            <div style={{ marginTop: 12 }}>
              <PerCheckStatus checks={validation.checks} />
            </div>
          </>
        ) : (
          <div style={{ color: "#888" }}>
            Enter a ticket_id above to load validation status.
          </div>
        )}
      </section>

      <section style={card("Rollback rate")}>
        <RollbackRate rate={rollbackRate.rate} threshold={rollbackRate.threshold} />
      </section>

      <section style={card("Safe Mode (MS-19..MS-23)")}>
        <SafeModeToggle data={safeMode} onChange={refreshSafeMode} />
      </section>
    </div>
  );
}

function card(title: string): React.CSSProperties {
  return {
    border: "1px solid #e2e2e2",
    borderRadius: 8,
    padding: 16,
    background: "#fff",
  };
}

function input(): React.CSSProperties {
  return {
    flex: 1,
    padding: "6px 8px",
    border: "1px solid #ccc",
    borderRadius: 4,
    fontFamily: "monospace",
  };
}

function btn(bg = "#dcfce7"): React.CSSProperties {
  return {
    padding: "6px 14px",
    borderRadius: 4,
    border: "1px solid #999",
    background: bg,
    cursor: "pointer",
  };
}
