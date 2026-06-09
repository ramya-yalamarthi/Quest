import React from "react";
// Escalation Timer Component
function EscalationTimer({ ticket }) {
  // Always base SLA on ticket creation time
  const startAt = ticket.created_at ? new Date(ticket.created_at) : null;
  const totalSLAHours = 3;
  const now = new Date();
  let elapsedMs = 0;
  if (startAt) {
    elapsedMs = Math.max(0, now - startAt);
  }
  const elapsedHours = Math.floor(elapsedMs / 3600000);
  const elapsedMinutes = Math.floor((elapsedMs % 3600000) / 60000);
  const slaMs = totalSLAHours * 60 * 60 * 1000;
  const isOverdue = elapsedMs > slaMs;
  return (
    <div style={{ background: '#fff3e0', border: '1px solid #ffb300', borderRadius: '8px', padding: '16px', minHeight: '120px', display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
      <h4 style={{ margin: 0, fontWeight: 700, color: '#ff6f00', fontSize: '18px' }}>Escalation Timer</h4>
      <div style={{ fontSize: '16px', fontWeight: 600, color: isOverdue ? '#d32f2f' : '#388e3c', marginTop: '8px' }}>{isOverdue ? 'OVERDUE' : 'On time'}</div>
      <div style={{ fontSize: '15px', marginTop: '4px' }}>Escalate to L2 in</div>
      <div style={{ fontSize: '15px', marginTop: '4px' }}>SLA: {totalSLAHours}h total · {elapsedHours}h {elapsedMinutes}m elapsed</div>
    </div>
  );
}

// EscalationJourney: SVG timeline with milestones, arrows, and dynamic progress bar
function EscalationJourney({ ticket, slaMs }) {
  const createdAt = ticket?.created_at ? new Date(ticket.created_at) : null;
  const now = new Date();
  const sla = slaMs || 3 * 60 * 60 * 1000; // 3 hours in ms

  // Always active for now
  const llmActive = true;
  const ackActive = true;
  // Use status for resolvedActive
  const resolvedActive = ticket?.status === 'RESOLVED';

  // Progress calculation (from Acknowledged to Resolved)
  let progress = 0;
  if (createdAt) {
    if (resolvedActive) {
      progress = 1;
    } else {
      progress = Math.min(1, (now - createdAt) / sla);
    }
  }
  // Progress color logic
  let progressColor = '#43a047'; // green
  if (!resolvedActive && progress >= 0.8) progressColor = '#e53935'; // red if overdue and not resolved

  // SVG layout
  const width = 420;
  const height = 70;
  const milestones = [
    { label: 'LLM Reasoning', x: 40, active: llmActive, icon: '🤖' },
    { label: 'Acknowledged', x: 210, active: ackActive, icon: '📩' },
    {
      label: 'Resolved',
      x: 380,
      active: resolvedActive,
      icon: resolvedActive ? '✅' : '',
      fill: resolvedActive ? '#7c4dff' : '#fff',
      stroke: resolvedActive ? '#7c4dff' : '#bdbdbd',
      iconFill: resolvedActive ? '#43a047' : '#bdbdbd',
    },
  ];

  // Progress line (from Acknowledged to Resolved)
  const progressStart = milestones[1].x;
  const progressEnd = milestones[2].x;
  const progressLineLength = progressEnd - progressStart;
  const filledLength = Math.max(0, Math.min(progressLineLength, progress * progressLineLength));

  return (
    <div style={{ width: width, margin: '0 auto', padding: '12px 0' }}>
      <svg width={width} height={height}>
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,4 L0,8 Z" fill="#888" />
          </marker>
        </defs>
        {/* Main line */}
        <line x1={milestones[0].x} y1={35} x2={milestones[2].x} y2={35} stroke="#e0e0e0" strokeWidth={6} />
        {/* Progress line */}
        <line x1={progressStart} y1={35} x2={progressStart + filledLength} y2={35} stroke={progressColor} strokeWidth={6} />
        {/* Milestone circles */}
        {milestones.map((m, idx) => (
          <circle
            key={m.label}
            cx={m.x}
            cy={35}
            r={18}
            fill={idx === 2 ? m.fill : m.active ? '#7c4dff' : '#fff'}
            stroke={idx === 2 ? m.stroke : m.active ? '#7c4dff' : '#bdbdbd'}
            strokeWidth={m.active ? 4 : 2}
          />
        ))}
        {/* Milestone icons */}
        <text x={milestones[0].x} y={40} textAnchor="middle" fontSize="20" fill="#fff">🤖</text>
        <text x={milestones[1].x} y={40} textAnchor="middle" fontSize="20" fill="#fff">📩</text>
        {/* Only show green check if resolved, else gray circle */}
        {resolvedActive ? (
          <text x={milestones[2].x} y={40} textAnchor="middle" fontSize="20" fill="#43a047">✅</text>
        ) : (
          <circle cx={milestones[2].x} cy={35} r={10} fill="#fff" stroke="#bdbdbd" strokeWidth={2} />
        )}
        {/* Arrows */}
        <line x1={milestones[0].x + 18} y1={35} x2={milestones[1].x - 18} y2={35} stroke="#888" strokeWidth={2} markerEnd="url(#arrow)" />
        <line x1={milestones[1].x + 18} y1={35} x2={milestones[2].x - 18} y2={35} stroke="#888" strokeWidth={2} markerEnd="url(#arrow)" />
        {/* Labels */}
        {milestones.map((m, idx) => (
          <text
            key={m.label + '-label'}
            x={m.x}
            y={65}
            textAnchor="middle"
            fontSize="13"
            fill="#333"
            fontWeight={m.active ? 700 : 400}
          >
            {m.label}
          </text>
        ))}
      </svg>
      {/* Progress percent and time info */}
      {createdAt && (
        <div style={{ textAlign: 'center', fontSize: 13, marginTop: 4, color: progressColor }}>
          {resolvedActive
            ? `Resolved (${Math.round(progress * 100)}%)`
            : `Elapsed: ${Math.floor((now - createdAt) / 3600000)}h ${Math.floor(((now - createdAt) % 3600000) / 60000)}m (${Math.round(progress * 100)}%)`}
        </div>
      )}
      <div style={{ textAlign: 'center', fontSize: 11, color: '#888', marginTop: 2 }}>
        SLA: 3h
      </div>
    </div>
  );
}

// IcM-style Incident Brief component — auto-loads when a ticket is opened
function IncidentBrief({ brief, loading }) {
  const containerStyle = {
    background: '#ffffff',
    border: '1px solid #e0e0e0',
    borderRadius: '4px',
    padding: '20px 24px 16px',
    marginBottom: '20px',
    fontFamily: '"Segoe UI", system-ui, sans-serif',
  };

  if (loading) {
    return (
      <div style={containerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span style={{ fontSize: '16px', color: '#5c6bc0', fontWeight: 700 }}>✦</span>
          <span style={{ fontSize: '15px', fontWeight: 600, color: '#1a1a1a' }}>AI summary by IcM Assistant</span>
        </div>
        <div style={{ color: '#888', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', marginTop: '10px' }}>
          <span className="spinner" style={{ width: '13px', height: '13px', borderWidth: '2px' }} />
          Generating AI summary...
        </div>
      </div>
    );
  }

  if (!brief) return null;

  const fmtTime = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', timeZoneName: 'short'
    });
  };

  return (
    <div style={containerStyle}>
      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '2px' }}>
        <span style={{ fontSize: '16px', color: '#5c6bc0', fontWeight: 700 }}>✦</span>
        <span style={{ fontSize: '15px', fontWeight: 600, color: '#1a1a1a' }}>AI summary by IcM Assistant</span>
      </div>

      {/* ── Timestamp ── */}
      {brief.generated_at && (
        <div style={{ fontSize: '12px', color: '#888', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '5px' }}>
          <span style={{ fontSize: '13px' }}>⊙</span>
          <span>Last updated at {fmtTime(brief.generated_at)}</span>
        </div>
      )}

      {/* ── Horizontal rule ── */}
      <div style={{ borderTop: '1px solid #e8e8e8', marginBottom: '16px' }} />

      {/* ── Two-column body ── */}
      <div style={{ display: 'flex', gap: '0', alignItems: 'flex-start' }}>

        {/* Left column */}
        <div style={{ flex: '0 0 62%', paddingRight: '32px' }}>

          {/* What we know */}
          <div style={{ marginBottom: '18px' }}>
            <p style={{ margin: '0 0 8px', fontWeight: 700, fontSize: '14px', color: '#1a1a1a' }}>
              What we know:
            </p>
            <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.75 }}>
              {(brief.what_we_know || []).map((item, i) => {
                const colonIdx = item.indexOf(':');
                const hasLabel = colonIdx > 0 && colonIdx < 30;
                return (
                  <li key={i} style={{ fontSize: '13.5px', color: '#222', marginBottom: '2px' }}>
                    {hasLabel ? (
                      <><strong>{item.slice(0, colonIdx)}</strong>:{item.slice(colonIdx + 1)}</>
                    ) : item}
                  </li>
                );
              })}
            </ul>
          </div>

          {/* What has been done */}
          <div>
            <p style={{ margin: '0 0 8px', fontWeight: 700, fontSize: '14px', color: '#1a1a1a' }}>
              What has been done so far:
            </p>
            <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.75 }}>
              {(brief.what_has_been_done || []).map((item, i) => (
                <li key={i} style={{ fontSize: '13.5px', color: '#222', marginBottom: '2px' }}>{item}</li>
              ))}
            </ul>
          </div>
        </div>

        {/* Vertical divider */}
        <div style={{ width: '1px', background: '#e0e0e0', alignSelf: 'stretch', flexShrink: 0 }} />

        {/* Right column */}
        <div style={{ flex: '0 0 38%', paddingLeft: '28px' }}>
          <p style={{
            margin: '0 0 12px',
            fontSize: '14px',
            fontWeight: 600,
            color: '#1a1a1a',
            borderBottom: '1px dashed #aaa',
            paddingBottom: '4px',
            display: 'inline-block',
          }}>
            Recommended actions
          </p>
          <ol style={{ margin: 0, paddingLeft: '16px', lineHeight: 1.75 }}>
            {(brief.recommended_actions || []).map((action, i) => (
              <li key={i} style={{ fontSize: '13.5px', color: '#222', marginBottom: '10px' }}>
                <strong>{action.title}:</strong>{' '}
                <span style={{ color: '#333' }}>{action.detail}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>

      {/* ── Footer ── */}
      <div style={{ borderTop: '1px solid #e8e8e8', marginTop: '16px', paddingTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: '12px', color: '#aaa', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>AI-generated content may be incorrect</span>
          <button onClick={() => {}} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '15px', padding: '0 2px', color: '#555' }} title="Helpful">👍</button>
          <button onClick={() => {}} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '15px', padding: '0 2px', color: '#555' }} title="Not helpful">👎</button>
        </div>
        <div style={{ fontSize: '12px', color: '#888', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>Are these actions useful?</span>
          <button onClick={() => {}} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '15px', padding: '0 2px', color: '#555' }} title="Yes">👍</button>
          <button onClick={() => {}} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '15px', padding: '0 2px', color: '#555' }} title="No">👎</button>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { Bar } from "react-chartjs-2";
import { Chart, BarElement, CategoryScale, LinearScale, Tooltip, Legend } from "chart.js";
Chart.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);
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
    const [trendRange, setTrendRange] = useState(7);
    const [resolution, setResolution] = useState(null);
    const [outcomeWithDates, setOutcomeWithDates] = useState([]);

    // Helper to get similar incident trend data (now uses outcomeWithDates and groups by created_at)
    const getIncidentTrendData = () => {
      if (!outcomeWithDates || !Array.isArray(outcomeWithDates) || !outcomeWithDates.length) {
        return { labels: [], data: [] };
      }
      const now = new Date();
      const rangeDays = trendRange;
      // Filter tickets by date range
      const filtered = outcomeWithDates.filter(
        t => t.created_at && (now - new Date(t.created_at)) <= rangeDays * 24 * 60 * 60 * 1000
      );
      // Group by day
      const dayCounts = {};
      filtered.forEach(t => {
        const d = new Date(t.created_at);
        const day = d.toLocaleDateString();
        dayCounts[day] = (dayCounts[day] || 0) + 1;
      });
      // Sort days
      const sortedDays = Object.keys(dayCounts).sort((a, b) => new Date(a) - new Date(b));
      return {
        labels: sortedDays,
        data: sortedDays.map(day => dayCounts[day])
      };
    };
  const [{ token, user }, setAuth] = useState(initialAuth);
  const [tickets, setTickets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [incidentBrief, setIncidentBrief] = useState(null);
  const [briefLoading, setBriefLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [draft, setDraft] = useState(null);
  const [draftOriginal, setDraftOriginal] = useState(null);
  const [emailTab, setEmailTab] = useState("ai"); // "ai" or "custom"
  const [customDraft, setCustomDraft] = useState({ subject: "", body: "" });
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

  // Auto-load cached analysis when ticket is selected
  useEffect(() => {
    if (!selected || !token) return;
    
    // Fetch cached analysis for the selected ticket
    fetch(`${API_BASE}/tickets/${selected.ticket_id}/analysis`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch cached analysis');
        return res.json();
      })
      .then(data => {
        if (data) {
          // If cached analysis exists, populate the UI
          setAnalysis({
            root_cause: data.root_cause,
            recommendation: data.recommendation,
            // web_solutions: data.web_solutions,
            similar_count: 0,
            similar_resolutions: []
          });
          
          if (data.draft_email_id) {
            setDraft({
              email_id: data.draft_email_id,
              subject: data.draft_email_subject,
              body: data.draft_email_body
            });
            setDraftOriginal({
              subject: data.draft_email_subject,
              body: data.draft_email_body
            });
          }
        }
      })
      .catch(err => {
        // Silently fail if no cached analysis - user can click "Analyze Ticket"
        console.debug('No cached analysis found:', err);
      });
  }, [selected, token]);

  // Auto-load incident brief when ticket is selected
  useEffect(() => {
    if (!selected || !token) return;
    setBriefLoading(true);
    setIncidentBrief(null);
    fetch(`${API_BASE}/tickets/${selected.ticket_id}/incident-brief`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(res => {
        if (!res.ok) throw new Error('brief fetch failed');
        return res.json();
      })
      .then(data => setIncidentBrief(data))
      .catch(err => console.debug('Incident brief unavailable:', err))
      .finally(() => setBriefLoading(false));
  }, [selected, token]);

  // Auto-clear message after 2 seconds
  useEffect(() => {
    if (message) {
      const timer = setTimeout(() => {
        setMessage("");
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [message]);

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
    setIncidentBrief(null);
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
    "Searching Microsoft resources",
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
      setMessage("Email sent successfully.");
    } catch (err) {
      setMessage(err.message || "Failed to approve email. Please try again.");
    } finally {
      setBusy(false);
      setActivity(null);
    }
  };

  const handleImproveEmail = async () => {
    if (!customDraft.body) {
      setMessage("Please enter email body");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const res = await fetch(`${API_BASE}/mcp/improve-email`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          subject: customDraft.subject,
          body: customDraft.body,
        }),
      });
      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`Failed to improve email: ${errorText}`);
      }
      const data = await res.json();
      setCustomDraft({
        subject: data.subject,
        body: data.body,
      });
      setMessage("Email improved successfully!");
    } catch (err) {
      setMessage(err.message || "Failed to improve email. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const handleSendCustom = async () => {
    if (!customDraft.subject || !customDraft.body || !selected) return;
    setBusy(true);
    setActivity("send");
    setMessage("");
    try {
      // Create a draft email from the custom draft
      const draftRes = await fetch(`${API_BASE}/mcp/draft-email`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ticket_id: selected.ticket_id,
          subject: customDraft.subject,
          body: customDraft.body,
        }),
      });
      if (!draftRes.ok) throw new Error("Failed to create draft");
      const draftData = await draftRes.json();
      
      // Approve and send the email
      await approveEmail(token, draftData.email_id);
      setMessage("Email sent successfully.");
      
      // Clear custom draft after sending
      setCustomDraft({ subject: "", body: "" });
    } catch (err) {
      setMessage(err.message || "Failed to send email. Please try again.");
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



  useEffect(() => {
    if (!selected || !token) return;
    // Fetch resolution for the selected ticket
    fetch(`${API_BASE}/resolutions?ticket_id=${selected.ticket_id}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch resolution');
        return res.json();
      })
      .then(async data => {
        if (data && data.length > 0) {
          setResolution(data[0]);
          // If outcome exists, check for missing created_at and fetch as needed
          if (data[0].outcome && Array.isArray(data[0].outcome)) {
            const outcome = data[0].outcome;
            // Find which items are missing created_at
            const needsFetch = outcome.filter(item => !item.created_at && item.ticket_id);
            if (needsFetch.length === 0) {
              setOutcomeWithDates(outcome);
            } else {
              // Fetch created_at for each missing ticket_id
              const fetches = await Promise.all(
                outcome.map(async item => {
                  if (item.created_at || !item.ticket_id) return item;
                  try {
                    const res = await fetch(`${API_BASE}/tickets/${item.ticket_id}`, {
                      headers: { Authorization: `Bearer ${token}` }
                    });
                    if (!res.ok) throw new Error('Failed to fetch ticket');
                    const ticket = await res.json();
                    return { ...item, created_at: ticket.created_at };
                  } catch {
                    return item;
                  }
                })
              );
              setOutcomeWithDates(fetches);
            }
          } else {
            setOutcomeWithDates([]);
          }
        } else {
          setResolution(null);
          setOutcomeWithDates([]);
        }
      })
      .catch(err => {
        setResolution(null);
        setOutcomeWithDates([]);
        console.debug('No resolution found:', err);
      });
  }, [selected, token]);

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
          <label className="search-field">
            Search tickets
            <input
              type="text"
              value={ticketSearch}
              onChange={(e) => setTicketSearch(e.target.value)}
              placeholder="Search by ID, title, or description"
            />
          </label>
          <section className="panel">
            <div className="panel-header">
              <h2>Assigned Tickets</h2>
              <span className="pill">{assignedTickets.length}</span>
            </div>
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
                      // Clear current state, auto-load will fetch cached analysis
                      setAnalysis(null);
                      setDraft(null);
                      setDraftOriginal(null);
                    }}
                  >
                    <div className="title">{ticket.title}</div>
                    <div className="meta">
                      {ticket.ticket_id} • {formatRelative(ticket.last_email_at)}
                    </div>
                    {/* SLA status based on created_at and 3h SLA */}
                    {ticket.created_at ? (() => {
                      const createdAt = new Date(ticket.created_at);
                      const now = new Date();
                      const elapsedMs = Math.max(0, now - createdAt);
                      const slaMs = 3 * 60 * 60 * 1000;
                      const isOverdue = elapsedMs > slaMs;
                      return (
                        <div className={`sla-flag ${isOverdue ? "overdue" : "on-time"}`}>
                          {isOverdue ? "Overdue" : "On time"}
                        </div>
                      );
                    })() : null}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {user?.role === "SUPPORT_MANAGER" ? (
            <section className="panel">
              <div className="panel-header">
                <h2>Escalated Tickets</h2>
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
                        // Clear current state, auto-load will fetch cached analysis
                        setAnalysis(null);
                        setDraft(null);
                        setDraftOriginal(null);
                      }}
                    >
                      <div className="title">{ticket.title}</div>
                      <div className="meta">
                        {ticket.ticket_id} • {formatDue(ticket.manager_next_update_due_at)}
                      </div>
                      {ticket.manager_sla_status ? (
                        <div
                          className={`sla-flag ${
                            ticket.manager_sla_status === "overdue" ? "overdue" : "on-time"
                          }`}
                        >
                          {ticket.manager_sla_status === "overdue"
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

        <section className="panel detail-panel">
          {!selected ? (
            <div className="empty">Select a ticket to view details.</div>
          ) : (
            <div className="ticket-detail">
              <div className="ticket-header">
                <div>
                  {/* Product, Env, Region section */}
                  <div className="ticket-header">
                    <div>
                      {/* Priority, Service Status, Product, Env, Region section */}
                      <h2>{selected.title}</h2>
                      <p>{selected.description}</p>
                      {/* <span className="status-row detail">
                        ...existing code...
                      </span> */}
                    </div>
                    {/* <div className="status-chip">
                      <span className="status-label">Next update</span>
                      <span className="status-value">
                        {user?.role === "SUPPORT_MANAGER" && selected.manager_next_update_due_at
                          ? formatDue(selected.manager_next_update_due_at)
                          : formatDue(selected.next_update_due_at)}
                      </span>
                    </div> */}
                    {/* {user?.role === "SUPPORT_MANAGER" && selected.manager_sla_status ? (
                      <div
                        className={`sla-flag ${
                          selected.manager_sla_status === "overdue" ? "overdue" : "on-time"
                        }`}
                      >
                        {selected.manager_sla_status === "overdue"
                          ? "Overdue"
                          : "On time"}
                      </div>
                    ) : selected.sla_status && selected.sla_status !== "pending" ? (
                      <div
                        className={`sla-flag ${
                          selected.sla_status === "overdue" ? "overdue" : "on-time"
                        }`}
                      >
                        {selected.sla_status === "overdue"
                          ? "Overdue"
                          : "On time"}
                      </div>
                    ) : null} */}
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
                      : analysis
                      ? "Refresh Analysis"
                      : "Analyze Ticket"}
                  </button>
                  {busy && activity === "analysis" ? (
                    <div className="loading-inline">
                      <span className="spinner" />
                      <span>{loadingStep || "Working..."}</span>
                    </div>
                  ) : null}
                </div>
              </div>

              {/* Incident Brief — shown immediately on ticket open */}
              <IncidentBrief brief={incidentBrief} loading={briefLoading} />

              {analysis ? (
                <div className="analysis">
                  {/* Ticket Summary Section */}
                  <div className="card accent-info">
                    <h3>AI Summary & Contextual Analysis</h3>
                    <div className="ticket-summary">
                      <div style={{ marginTop: '8px' }}>
                        <div className="rich-text" style={{ marginTop: '4px' }}
                          dangerouslySetInnerHTML={{
                            __html: renderPreview(
                              selected.ticket_summary || (analysis && analysis.ticket_summary) || "No summary available."
                            )
                          }}
                        />
                        {/* Visually clear meta section below summary */}
                        <div className="ticket-meta-summary" style={{
                          display: 'flex',
                          flexWrap: 'wrap',
                          gap: '12px',
                          margin: '16px 0',
                          padding: '12px',
                          background: '#f7f7fa',
                          borderRadius: '8px',
                          fontSize: '1rem',
                          fontWeight: 500
                        }}>
                          {selected.priority && (
                            <span><span style={{ color: '#888'}}>Priority:</span>{selected.priority}</span>
                          )}
                          {selected.service && (
                            <span><span style={{ color: '#888' }}>Product:</span> {selected.service}</span>
                          )}
                          {selected.env && (
                            <span><span style={{ color: '#888' }}>Env:</span> {selected.env}</span>
                          )}
                          {selected.region && (
                            <span><span style={{ color: '#888' }}>Region:</span> {selected.region}</span>
                          )}
                        </div>
                        {analysis.error_codes && analysis.error_codes.length > 0 && (
                          <div style={{ marginTop: '8px' }}>
                            <strong>Error Codes:</strong>
                            <ul style={{ marginTop: '4px' }}>
                              {analysis.error_codes.map((code, idx) => (
                                <li key={idx}>{code}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                    {/* Two-column row: left = EscalationTimer, right = EscalationJourney */}
                    <div style={{ display: 'flex', flexDirection: 'row', gap: '24px', marginTop: '32px' }}>
                      <div style={{ flex: 1, minWidth: '220px', maxWidth: '320px', display: 'flex', alignItems: 'stretch' }}>
                        <EscalationTimer ticket={selected} />
                      </div>
                      <div style={{ flex: 2, minWidth: '220px', maxWidth: '600px', display: 'flex', alignItems: 'center' }}>
                        <EscalationJourney ticket={selected} slaMs={3 * 60 * 60 * 1000} />
                      </div>
                    </div>
                  </div>
                  <div className="analysis-grid">
                    {/* <div className="card accent-mint">
                      <h3>Possible Root Cause</h3>
                      <div
                        className="rich-text"
                        dangerouslySetInnerHTML={{
                          __html: renderPreview(analysis.root_cause)
                        }}
                      />
                    </div> */}
                    <div className="card accent-sun">
                      <h3>Recommended Steps</h3>
                      {resolution && Array.isArray(resolution.recommendedsteps) && resolution.recommendedsteps.length > 0 ? (
                        <div style={{ margin: '12px 0', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          {resolution.recommendedsteps.map((stepObj, idx) => (
                            <div key={idx} style={{ background: idx % 2 === 0 ? '#f7f7fa' : '#ede7f6', borderRadius: '6px', padding: '10px 14px', fontSize: '15px', color: '#222', border: '1px solid #e0e0e0', marginBottom: '2px', minHeight: '48px', display: 'flex', flexDirection: 'column' }}>
                              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                                <span style={{ fontWeight: 600, fontSize: '15px', marginRight: '12px' }}>{stepObj.title}</span>
                                <span
                                  style={{
                                    display: 'inline-block',
                                    marginLeft: '6px',
                                    cursor: 'pointer',
                                    color: '#1976d2',
                                    fontSize: '16px',
                                    fontWeight: 700
                                  }}
                                  title={stepObj.justification}
                                >&#9432;</span>
                                <span style={{ marginLeft: 'auto', fontWeight: 600, color: '#388e3c', fontSize: '15px' }}>{stepObj.confidence_score}% Confidence</span>
                              </div>
                              <div style={{ fontWeight: 400, fontSize: '16px', marginBottom: '4px', color: '#888', fontFamily: 'Segoe UI, Roboto, Arial, sans-serif' }}> {stepObj.description}</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="rich-text">No recommended steps available.</div>
                      )}
                    </div>
                  </div>

                  {/*<div className="card bordered-card web-solutions">
                      <h3>Web Solutions</h3>
                      {analysis.web_solutions?.length ? (
                        <div className="web-solution-list">
                          {analysis.web_solutions.map((item, index) => (
                            <div key={`${item.url}-${index}`} className="web-solution-item">
                              <div className="web-solution-title">{item.title}</div>
                              <a className="web-solution-link" href={item.url} target="_blank" rel="noreferrer">
                                {item.url}
                              </a>
                              {item.summary && (
                                <div className="web-solution-summary">{item.summary}</div>
                              )}
                              {item.steps?.length > 0 && (
                                <ol className="web-solution-steps">
                                  {item.steps.map((step, stepIndex) => (
                                    <li key={`${item.url}-step-${stepIndex}`}>{step}</li>
                                  ))}
                                </ol>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : null} 
                      <div className="empty">
                        No web solutions found.
                        <div className="empty-note">
                          Try analyzing the ticket again or check your search configuration.
                        </div>
                      </div>
                  </div> */}

                  <div className="card bordered-card">
                                        {/* Incident Trends Bar Graph */}
                                        <div style={{ marginBottom: '18px', padding: '8px 0' }}>
                                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                                            <strong>Similar Incident Trends</strong>
                                            <select value={trendRange} onChange={e => setTrendRange(Number(e.target.value))} style={{ fontSize: '15px', marginLeft: '8px' }}>
                                              <option value={1}>24 hrs</option>
                                              <option value={7}>7 days</option>
                                              <option value={15}>15 days</option>
                                              <option value={30}>30 days</option>
                                            </select>
                                          </div>
                                          <Bar
                                            data={{
                                              labels: getIncidentTrendData().labels,
                                              datasets: [{
                                                label: 'Similar Incidents',
                                                data: getIncidentTrendData().data,
                                                backgroundColor: '#7c4dff',
                                                barPercentage: 0.15,
                                                categoryPercentage: 0.3
                                              }]
                                            }}
                                            options={{
                                              responsive: true,
                                              plugins: {
                                                legend: { display: false },
                                                tooltip: { enabled: true }
                                              },
                                              layout: { padding: 10 },
                                              scales: {
                                                x: {
                                                  title: { display: true, text: 'Date' },
                                                  barPercentage: 0.15,
                                                  categoryPercentage: 0.3
                                                },
                                                y: {
                                                  title: { display: true, text: 'Count' },
                                                  beginAtZero: true,
                                                  ticks: {
                                                    stepSize: 1,
                                                    precision: 0
                                                  }
                                                }
                                              }
                                            }}
                                            height={100}
                                          />
                                        </div>
                    <h3>
                      Historical Match Analysis
                      {resolution && typeof resolution.total_similar_tickets_above70 === 'number' ? (
                        <span style={{ fontSize: '15px', fontWeight: 500, color: '#7c4dff', marginLeft: '16px' }}>
                          {`${resolution.total_similar_tickets_above70} matches found (>=70% similarity)`}
                        </span>
                      ) : null}
                    </h3>
                    {/* Display each outcome record as a subtle, professional block, showing user name/email and creation date */}
                    {resolution && resolution.outcome && Array.isArray(resolution.outcome) && resolution.outcome.length > 0 ? (
                      <div style={{ margin: '12px 0', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {resolution.outcome.map((item, idx) => (
                          <div key={item.ticket_id || idx} style={{ background: idx % 2 === 0 ? '#f7f7fa' : '#ede7f6', borderRadius: '6px', padding: '10px 14px', fontSize: '15px', color: '#222', border: '1px solid #e0e0e0', marginBottom: '2px', minHeight: '48px', display: 'flex', flexDirection: 'column' }}>
                            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                              <span style={{ fontWeight: 600, fontSize: '15px', marginRight: '12px' }}>{item.ticket_id}</span>
                              <span style={{ fontWeight: 600, color: '#388e3c', fontSize: '15px', marginLeft: '24px' }}>{item.similarity}% match</span>
                            </div>
                            <div style={{ fontWeight: 400, fontSize: '16px', marginBottom: '4px' }}>{item.title}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="empty">No similar tickets found.</div>
                    )}
                  </div>

                  {/* <div className="card bordered-card">
                    <div className="email-header">
                      <h3>Draft Email</h3>
                      <div className="email-tabs">
                        <button
                          className={emailTab === "ai" ? "tab-active" : "tab-inactive"}
                          onClick={() => setEmailTab("ai")}
                        >
                          AI-Generated
                        </button>
                        <button
                          className={emailTab === "custom" ? "tab-active" : "tab-inactive"}
                          onClick={() => setEmailTab("custom")}
                        >
                          Draft Own Email
                        </button>
                      </div>
                    </div>

                    {emailTab === "ai" ? (
                      <>
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
                      </>
                    ) : (
                      <>
                        <div className="email-actions">
                          <button
                            className="ghost"
                            onClick={() =>
                              setCustomDraft({ subject: "", body: "" })
                            }
                          >
                            Clear
                          </button>
                          <button
                            className="primary"
                            onClick={handleImproveEmail}
                            disabled={busy || !customDraft.body}
                            title={!customDraft.body ? "Please enter email body" : ""}
                          >
                            {busy ? "Improving..." : "Improve with AI"}
                          </button>
                        </div>
                        <label>
                          Subject
                          <input
                            type="text"
                            value={customDraft.subject}
                            onChange={(e) =>
                              setCustomDraft({ ...customDraft, subject: e.target.value })
                            }
                            placeholder="Enter email subject..."
                          />
                        </label>
                        <label>
                          Body
                          <textarea
                            rows="8"
                            value={customDraft.body}
                            onChange={(e) =>
                              setCustomDraft({ ...customDraft, body: e.target.value })
                            }
                            placeholder="Write your email here..."
                          />
                        </label>
                        <div className="email-preview">
                          <div className="preview-title">Preview</div>
                          <div
                            className="preview-body"
                            dangerouslySetInnerHTML={{
                              __html: renderPreview(customDraft.body || "")
                            }}
                          />
                        </div>
                        <button className="primary" onClick={handleSendCustom} disabled={busy || !customDraft.subject || !customDraft.body} title={!customDraft.subject || !customDraft.body ? "Please enter both subject and body to send" : ""}>
                          {busy ? "Sending..." : "Send Email"}
                        </button>
                      </>
                    )}
                  </div> */}
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
