import { useEffect, useState } from "react";
import { api } from "./api";
import RecordDrawer from "./RecordDrawer";
import { FlagBadge, ScopeTag, StatusPill, fmt } from "./ui";

const STATUSES = ["", "pending", "flagged", "approved", "rejected", "locked"];

// The review surface: filterable table of canonical rows, bulk approve/lock, and a drawer
// for the per-row detail + edit + audit.
export default function Review({ batch, onBack }) {
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("");
  const [scope, setScope] = useState("");
  const [sel, setSel] = useState(new Set());
  const [openId, setOpenId] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const params = {};
    if (batch) params.batch = batch.id;
    if (status) params.status = status;
    if (scope) params.scope = scope;
    const data = await api.records(params);
    setRows(data.results);
    setSel(new Set());
  }
  useEffect(() => { load(); }, [batch?.id, status, scope]);

  const toggle = (id) => setSel((s) => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  async function bulk(action) {
    if (!sel.size) return;
    setBusy(true);
    try { await api.bulk([...sel], action); await load(); }
    finally { setBusy(false); }
  }

  return (
    <div className="stack">
      <div className="row between">
        <div>
          <button className="link" onClick={onBack}>← Dashboard</button>
          <h2>{batch ? `Review — ${batch.filename}` : "All records"}</h2>
        </div>
        <div className="filters">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || "all statuses"}</option>)}
          </select>
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="">all scopes</option><option value="1">Scope 1</option>
            <option value="2">Scope 2</option><option value="3">Scope 3</option>
          </select>
        </div>
      </div>

      {sel.size > 0 && (
        <div className="bulkbar">
          {sel.size} selected
          <button className="ok" onClick={() => bulk("approve")} disabled={busy}>Approve</button>
          <button className="danger" onClick={() => bulk("reject")} disabled={busy}>Reject</button>
          <button className="lock" onClick={() => bulk("lock")} disabled={busy}>Lock</button>
        </div>
      )}

      <div className="card">
        <table className="grid">
          <thead>
            <tr>
              <th></th><th>Scope</th><th>Category</th><th>Quantity</th>
              <th>CO₂e (kg)</th><th>Period</th><th>Status</th><th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={r.flags.length ? "flagged-row" : ""}>
                <td><input type="checkbox" checked={sel.has(r.id)} onChange={() => toggle(r.id)} /></td>
                <td><ScopeTag scope={r.scope} /></td>
                <td><button className="link" onClick={() => setOpenId(r.id)}>{r.category_display}</button></td>
                <td className="num">{fmt(r.quantity)} {r.unit}</td>
                <td className="num">{fmt(r.co2e_kg)}</td>
                <td className="muted small">{r.period_start || "—"}</td>
                <td><StatusPill status={r.status} /></td>
                <td>{r.flags.map((f) => <FlagBadge key={f} flag={f} />)}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan="8" className="muted">No records.</td></tr>}
          </tbody>
        </table>
      </div>

      {openId && <RecordDrawer id={openId} onClose={() => setOpenId(null)} onChanged={load} />}
    </div>
  );
}
