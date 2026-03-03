import { useEffect, useMemo, useRef, useState } from "react";
import {
  login,
  fetchTickets,
  updateDraft,
  approveEmail
} from "./api/mcpClient";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const initialAuth = () => {
  try {
    const token = localStorage.getItem("token");
    const user = JSON.parse(localStorage.getItem("user") || "null");
    return { token, user };
  } catch {
    return { token: null, user: null };
  }
};

export default function App() {
  const [{ token, user }, setAuth] = useState(initialAuth);
  const [tickets, setTickets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [draft, setDraft] = useState(null);
  const [draftOriginal, setDraftOriginal] = useState(null);
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState(null);
  const [loadingStep, setLoadingStep] = useState("");
  const [loadingStepIndex, setLoadingStepIndex] = useState(0);
  const [message, setMessage] = useState("");
  const [loginForm, setLoginForm] = useState({ email: "", password: "" });
  const [ticketSearch, setTicketSearch] = useState("");
  const streamRef = useRef(null);

  const assignedTickets = useMemo(() => {
    if (!user?.user_id) return [];
    return tickets.filter((t) => t.assigned_to === user.user_id);
  }, [tickets, user]);

  const managerQueue = useMemo(() => {
    if (!user?.user_id || user?.role !== "SUPPORT_MANAGER") return [];
    return tickets.filter(
      (t) =>
        t.escalated_manager_id1 === user.user_id ||
        t.escalated_manager_id2 === user.user_id
    );
  }, [tickets, user]);

  useEffect(() => {
    if (!token) return;
    setBusy(true);
    setActivity("fetch");
    const timer = setTimeout(() => {
      fetchTickets(token, ticketSearch.trim())
        .then((data) => {
          setTickets(data || []);
        })
        .catch((err) => setMessage(err.message))
        .finally(() => {
          setBusy(false);
          setActivity(null);
        });
    }, 300);
    return () => clearTimeout(timer);
  }, [token, ticketSearch]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setMessage("");
    setBusy(true);
    setActivity("login");
    try {
      const res = await login(loginForm.email, loginForm.password);
      localStorage.setItem("token", res.access_token);
      localStorage.setItem("user", JSON.stringify(res.user));
      setAuth({ token: res.access_token, user: res.user });
    } catch (err) {
      setMessage(err.message || "Login failed");
    } finally {
      setBusy(false);
      setActivity(null);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setAuth({ token: null, user: null });
    setTickets([]);
    setSelected(null);
    setAnalysis(null);
    setDraft(null);
    setDraftOriginal(null);
    setActivity(null);
    setLoadingStep("");
    setLoadingStepIndex(0);
    if (streamRef.current) {
      streamRef.current.close();
      streamRef.current = null;
    }
  };

  const analysisSteps = [
    "Computing ticket embedding",
    "Finding similar tickets",
    "Fetching historical resolutions",
    "Ranking resolutions by similarity",
    "Summarizing what worked and what did not",
    "Drafting customer email"
  ];

  const startAnalysisSteps = () => {
    setLoadingStep(analysisSteps[0]);
    setLoadingStepIndex(0);
  };

  const runAnalysis = () => {
    if (!selected) return;
    setBusy(true);
    setActivity("analysis");
    setMessage("");
    startAnalysisSteps();
    if (streamRef.current) {
      streamRef.current.close();
    }
    const streamUrl = `${API_BASE}/mcp/analyze/stream?ticket_id=${selected.ticket_id}&token=${encodeURIComponent(
      token
    )}`;
    const stream = new EventSource(streamUrl);
    streamRef.current = stream;

    stream.addEventListener("step", (event) => {
      const step = event.data;
      setLoadingStep(step);
      const idx = analysisSteps.indexOf(step);
      if (idx >= 0) {
        setLoadingStepIndex(idx);
      }
    });

    stream.addEventListener("done", (event) => {
      try {
        const res = JSON.parse(event.data);
        setAnalysis(res);
        setDraft({
          email_id: res.draft_email_id,
          subject: res.draft_email_subject,
          body: res.draft_email_body
        });
        setDraftOriginal({
          subject: res.draft_email_subject,
          body: res.draft_email_body
        });
      } catch {
        setMessage("Analysis completed with invalid response");
      }
      setLoadingStepIndex(analysisSteps.length);
      setLoadingStep("Done");
      setBusy(false);
      setActivity(null);
      stream.close();
      streamRef.current = null;
    });

    stream.addEventListener("error", () => {
      setMessage("Analysis failed");
      setBusy(false);
      setActivity(null);
      stream.close();
      streamRef.current = null;
    });
  };

  const handleSend = async () => {
    if (!draft?.email_id) return;
    setBusy(true);
    setActivity("send");
    setMessage("");
    try {
      await updateDraft(token, draft.email_id, draft.subject, draft.body);
      await approveEmail(token, draft.email_id);
      setMessage("Email sent and logged.");
    } catch (err) {
      setMessage(err.message || "Send failed");
    } finally {
      setBusy(false);
      setActivity(null);
    }
  };

  const renderPreview = (text) => {
    if (!text) return "";
    const escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const bolded = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    return bolded.replace(/\n/g, "<br />");
  };

  const formatRelative = (iso) => {
    if (!iso) return "Not sent yet";
    const then = new Date(iso);
    const now = new Date();
    const diffMs = now - then;
    if (diffMs < 0) return "just now";
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min${mins === 1 ? "" : "s"} ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
    const days = Math.floor(hours / 24);
    return `${days} day${days === 1 ? "" : "s"} ago`;
  };

  const formatDue = (iso) => {
    if (!iso) return "Not scheduled";
    const due = new Date(iso);
    const now = new Date();
    const diffMs = due - now;
    const absMins = Math.floor(Math.abs(diffMs) / 60000);
    const hours = Math.floor(absMins / 60);
    const mins = absMins % 60;
    const parts = [];
    if (hours) parts.push(`${hours} hour${hours === 1 ? "" : "s"}`);
    if (mins || !parts.length) parts.push(`${mins} min${mins === 1 ? "" : "s"}`);
    const label = parts.join(" ");
    return diffMs >= 0 ? `due in ${label}` : `overdue by ${label}`;
  };

  if (!token) {
    return (
      <div className="page">
        <div className="login-card">
          <div className="logo">
            <span>Support</span>
            <strong>AI</strong>
          </div>
          <h1>Engineer Console</h1>
          <p>Sign in with your SUPPORT or MANAGER credentials to review tickets.</p>
          <form onSubmit={handleLogin}>
            <label>
              Email
              <input
                type="email"
                value={loginForm.email}
                onChange={(e) =>
                  setLoginForm({ ...loginForm, email: e.target.value })
                }
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={loginForm.password}
                onChange={(e) =>
                  setLoginForm({ ...loginForm, password: e.target.value })
                }
                required
              />
            </label>
            <button className="primary" type="submit" disabled={busy}>
              {busy ? "Signing in..." : "Login"}
            </button>
          </form>
          {message ? <div className="alert">{message}</div> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="top-bar">
        <div>
          <div className="logo">
            <span>Support</span>
            <strong>AI</strong>
          </div>
          <div className="sub">Signed in as {user?.display_name}</div>
        </div>
        <button className="ghost" onClick={handleLogout}>
          Logout
        </button>
      </header>

      {busy && activity === "analysis" ? (
        <div className="loading-overlay" role="status" aria-live="polite">
          <div className="loading-card">
            <div className="loading-title">Working on your ticket</div>
            <div className="loading-subtitle">
              {loadingStep || "Processing"}
            </div>
            <div className="loading-steps">
              {analysisSteps.map((step, index) => {
                const allDone = loadingStepIndex >= analysisSteps.length;
                const status = allDone
                  ? "done"
                  : index < loadingStepIndex
                  ? "done"
                  : index === loadingStepIndex
                  ? "active"
                  : "pending";
                return (
                  <div key={step} className={`loading-step ${status}`}>
                    <span className="step-icon" aria-hidden="true" />
                    <span className="step-text">{step}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}

      <main className="grid">
        <div className="stack">
          <section className="panel">
            <div className="panel-header">
              <h2>Assigned Tickets</h2>
              <span className="pill">{assignedTickets.length}</span>
            </div>
            <label className="search-field">
              Search tickets
              <input
                type="text"
                value={ticketSearch}
                onChange={(e) => setTicketSearch(e.target.value)}
                placeholder="Search by ID, title, or description"
              />
            </label>
            {assignedTickets.length === 0 ? (
              <div className="empty">No tickets assigned to you.</div>
            ) : (
              <ul className="ticket-list">
                {assignedTickets.map((ticket) => (
                  <li
                    key={ticket.ticket_id}
                    className={
                      selected?.ticket_id === ticket.ticket_id ? "active" : ""
                    }
                    onClick={() => {
                      setSelected(ticket);
                      setAnalysis(null);
                      setDraft(null);
                      setDraftOriginal(null);
                    }}
                  >
                    <div className="title">{ticket.title}</div>
                    <div className="meta">{ticket.ticket_id}</div>
                    {ticket.sla_status && ticket.sla_status !== "pending" ? (
                      <div
                        className={`sla-flag ${
                          ticket.sla_status === "overdue" ? "overdue" : "on-time"
                        }`}
                      >
                        {ticket.sla_status === "overdue"
                          ? "Overdue"
                          : "On time"}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {user?.role === "SUPPORT_MANAGER" ? (
            <section className="panel">
              <div className="panel-header">
                <h2>Manager Queue</h2>
                <span className="pill">{managerQueue.length}</span>
              </div>
              {managerQueue.length === 0 ? (
                <div className="empty">No escalations for you.</div>
              ) : (
                <ul className="ticket-list">
                  {managerQueue.map((ticket) => (
                    <li
                      key={ticket.ticket_id}
                      className={
                        selected?.ticket_id === ticket.ticket_id ? "active" : ""
                      }
                      onClick={() => {
                        setSelected(ticket);
                        setAnalysis(null);
                        setDraft(null);
                        setDraftOriginal(null);
                      }}
                    >
                      <div className="title">{ticket.title}</div>
                      <div className="meta">{ticket.ticket_id}</div>
                      {ticket.sla_status && ticket.sla_status !== "pending" ? (
                        <div
                          className={`sla-flag ${
                            ticket.sla_status === "overdue" ? "overdue" : "on-time"
                          }`}
                        >
                          {ticket.sla_status === "overdue"
                            ? "Overdue"
                            : "On time"}
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}
        </div>

        <section className="panel">
          {!selected ? (
            <div className="empty">Select a ticket to view details.</div>
          ) : (
            <div className="ticket-detail">
              <div className="ticket-header">
                <div>
                  <h2>{selected.title}</h2>
                  <p>{selected.description}</p>
                  <div className="status-row detail">
                    <div className="status-chip">
                      <span className="status-label">Last Updated</span>
                      <span className="status-value">
                        {formatRelative(selected.last_email_at)}
                      </span>
                    </div>
                    <div className="status-chip">
                      <span className="status-label">Next update</span>
                      <span className="status-value">
                        {formatDue(selected.next_update_due_at)}
                      </span>
                    </div>
                    {selected.sla_status && selected.sla_status !== "pending" ? (
                      <div
                        className={`sla-flag ${
                          selected.sla_status === "overdue" ? "overdue" : "on-time"
                        }`}
                      >
                        {selected.sla_status === "overdue"
                          ? "Overdue"
                          : "On time"}
                      </div>
                    ) : null}
                  </div>
                </div>
                <div className="action-stack">
                  <button
                    className="primary"
                    onClick={runAnalysis}
                    disabled={busy}
                  >
                    {busy && activity === "analysis"
                      ? "Running..."
                      : "Check Past Resolutions"}
                  </button>
                  {busy && activity === "analysis" ? (
                    <div className="loading-inline">
                      <span className="spinner" />
                      <span>{loadingStep || "Working..."}</span>
                    </div>
                  ) : null}
                </div>
              </div>

              {analysis ? (
                <div className="analysis">
                  <div className="analysis-grid">
                    <div className="card">
                      <h3>Possible Root Cause</h3>
                      <div
                        className="rich-text"
                        dangerouslySetInnerHTML={{
                          __html: renderPreview(analysis.root_cause)
                        }}
                      />
                    </div>
                    <div className="card">
                      <h3>Recommended Steps</h3>
                      <div
                        className="rich-text"
                        dangerouslySetInnerHTML={{
                          __html: renderPreview(analysis.recommendation)
                        }}
                      />
                    </div>
                  </div>

                  <div className="card">
                    <h3>Similar Tickets</h3>
                    {analysis.similar_resolutions?.length ? (
                      <ul className="similar-list">
                        {analysis.similar_resolutions.map((item) => (
                          <li key={item.resolution_id}>
                            <div className="meta">Ticket: {item.ticket_id}</div>
                            <div className="body">{item.resolution_text}</div>
                            {item.root_cause ? (
                              <div className="meta">Cause: {item.root_cause}</div>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="empty">No similar resolutions found.</div>
                    )}
                  </div>

                  <div className="card">
                    <div className="email-header">
                      <h3>Draft Email</h3>
                      <div className="email-actions">
                        <button
                          className="ghost"
                          onClick={() =>
                            setDraft({ ...draft, subject: "", body: "" })
                          }
                        >
                          Clear
                        </button>
                        <button
                          className="ghost"
                          onClick={() => setDraft({ ...draftOriginal, email_id: draft.email_id })}
                          disabled={!draftOriginal}
                        >
                          Reset to draft
                        </button>
                      </div>
                    </div>
                    <label>
                      Subject
                      <input
                        type="text"
                        value={draft?.subject || ""}
                        onChange={(e) =>
                          setDraft({ ...draft, subject: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Body
                      <textarea
                        rows="8"
                        value={draft?.body || ""}
                        onChange={(e) =>
                          setDraft({ ...draft, body: e.target.value })
                        }
                      />
                    </label>
                    <div className="email-preview">
                      <div className="preview-title">Preview</div>
                      <div
                        className="preview-body"
                        dangerouslySetInnerHTML={{
                          __html: renderPreview(draft?.body || "")
                        }}
                      />
                    </div>
                    <button className="primary" onClick={handleSend} disabled={busy}>
                      {busy ? "Sending..." : "Send Email"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="empty">Run analysis to see similar tickets.</div>
              )}
            </div>
          )}
        </section>
      </main>

      {message ? <div className="toast">{message}</div> : null}
    </div>
  );
}
