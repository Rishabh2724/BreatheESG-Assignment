// Thin API client. Token lives in localStorage; every call carries it. In dev, Vite
// proxies /api to the Django server (see vite.config.js); in prod they're same-origin.

const TOKEN_KEY = "breathe_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

async function req(path, { method = "GET", body, isForm } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Token ${token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export const api = {
  async login(username, password) {
    const res = await fetch("/api/auth/token/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error("Invalid credentials");
    const { token } = await res.json();
    setToken(token);
    return token;
  },
  me: () => req("/me/"),
  summary: () => req("/summary/"),
  batches: () => req("/batches/"),
  upload: (sourceType, file) => {
    const fd = new FormData();
    fd.append("source_type", sourceType);
    fd.append("file", file);
    return req("/batches/", { method: "POST", body: fd, isForm: true });
  },
  records: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return req(`/records/${q ? `?${q}` : ""}`);
  },
  record: (id) => req(`/records/${id}/`),
  editRecord: (id, changes) => req(`/records/${id}/`, { method: "PATCH", body: changes }),
  act: (id, action) => req(`/records/${id}/${action}/`, { method: "POST" }),
  bulk: (ids, action) => req(`/records/bulk_action/`, { method: "POST", body: { ids, action } }),
};
