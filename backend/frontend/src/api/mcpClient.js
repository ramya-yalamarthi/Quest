const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options = {}) {
  const mergedHeaders = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: mergedHeaders
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function login(email, password) {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
}

export async function fetchTickets(token, query = "") {
  const qs = query ? `?q=${encodeURIComponent(query)}` : "";
  return request(`/tickets${qs}`, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });
}

export async function analyzeTicket(token, ticketId) {
  return request("/mcp/analyze", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ ticket_id: ticketId })
  });
}

export async function updateDraft(token, emailId, subject, body) {
  return request("/mcp/update-draft", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({
      email_id: emailId,
      subject,
      body
    })
  });
}

export async function approveEmail(token, emailId) {
  return request("/mcp/approve-email", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ email_id: emailId })
  });
}
