import { MitigationSafetyPanel } from "./components/MitigationSafetyPanel";

export function App() {
  return (
    <div style={{ fontFamily: "Segoe UI, Arial, sans-serif", padding: 24 }}>
      <h1 style={{ margin: 0 }}>Sentinel — Mitigation Safety</h1>
      <p style={{ color: "#666", marginTop: 4 }}>
        No approved mitigation reaches production directly. Stage → 24h
        validate → promote (only on PASS). Default-on Safe Mode.
      </p>
      <MitigationSafetyPanel />
    </div>
  );
}
