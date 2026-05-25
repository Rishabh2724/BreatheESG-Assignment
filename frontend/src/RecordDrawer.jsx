import { useEffect, useState } from "react";
import { api } from "./api";
import { FLAG_HELP, FlagBadge, ScopeTag, StatusPill, fmt } from "./ui";

// Side drawer for one record. Shows the RAW source row next to the NORMALIZED values so
// an analyst can see exactly what we did to the data, lets them correct fields, and shows
// the full audit trail. This is where the "source of truth" story is visible to a human.
export default function RecordDrawer({ id, onClose, onChanged }) {
  const [rec, setRec] = useState(null);
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function load() {
    setRec(await api.record(id));
    setEdits({});
  }
  useEffect(() => { load(); }, [id]);

  if (!rec) return <div className="drawer"><div className="drawer-body">Loading…</div></div>;

  const locked = rec.status === "locked";
  const setField = (f, v) => setEdits((e) => ({ ...e, [f]: v }));
  const val = (f) => (edits[f] !== undefined ? edits[f] : rec[f] ?? "");

  async function save() {
    if (!Object.keys(edits).length) return;
    setBusy(true); setErr("");
    try { await api.editRecord(id, edits); await load(); onChanged?.(); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }
  async function doAction(action) {
    setBusy(true); setErr("");
    try { await api.act(id, action); await load(); onChanged?.(); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div>
            <ScopeTag scope={rec.scope} /> <StatusPill status={rec.status} />
            <h2>{rec.category_display}</h2>
            <div className="muted small">{rec.source_type} · batch #{rec.batch} · record #{rec.id}</div>
          </div>
          <button className="link" onClick={onClose}>✕</button>
        </div>

        <div className="drawer-body">
          {rec.flags.length > 0 && (
            <div className="flag-explain">
              {rec.flags.map((f) => (
                <div key={f}><FlagBadge flag={f} /> <span className="muted small">{FLAG_HELP[f]}</span></div>
              ))}
            </div>
          )}

          <div className="two-col">
            <div>
              <h3>Raw source row</h3>
              <table className="kv">
                <tbody>
                  {Object.entries(rec.raw_record?.payload || {}).map(([k, v]) => (
                    <tr key={k}><td className="muted">{k}</td><td>{String(v)}</td></tr>
                  ))}
                </tbody>
              </table>
              {rec.raw_record?.parse_error && <div className="error">{rec.raw_record.parse_error}</div>}
            </div>

            <div>
              <h3>Normalized {locked && <span className="muted small">(locked — read only)</span>}</h3>
              <div className="field">
                <label>Quantity</label>
                <input disabled={locked} value={val("quantity")} onChange={(e) => setField("quantity", e.target.value)} />
                <span className="muted small">was: {rec.original_quantity || "—"} {rec.original_unit}</span>
              </div>
              <div className="field">
                <label>Unit</label>
                <input disabled={locked} value={val("unit")} onChange={(e) => setField("unit", e.target.value)} />
              </div>
              <div className="field">
                <label>Scope</label>
                <select disabled={locked} value={val("scope")} onChange={(e) => setField("scope", e.target.value)}>
                  <option value={1}>Scope 1</option><option value={2}>Scope 2</option><option value={3}>Scope 3</option>
                </select>
              </div>
              <div className="field">
                <label>Period</label>
                <span>{rec.period_start || "—"} → {rec.period_end || "—"}</span>
              </div>
              <div className="field">
                <label>Facility</label>
                <span>{rec.facility ? `${rec.facility.code} — ${rec.facility.name} (${rec.facility.country})` : "—"}</span>
              </div>
              <div className="field">
                <label>Emission factor</label>
                <span>{rec.emission_factor ? `${rec.emission_factor.factor_value} ${rec.emission_factor.factor_unit} · ${rec.emission_factor.source}` : "none"}</span>
              </div>
              <div className="field">
                <label>CO₂e (kg)</label>
                <strong>{fmt(rec.co2e_kg)}</strong>
              </div>
              {!locked && <button onClick={save} disabled={busy || !Object.keys(edits).length}>Save changes</button>}
            </div>
          </div>

          {err && <div className="error">{err}</div>}

          {!locked && (
            <div className="actions">
              {(rec.status === "pending" || rec.status === "flagged" || rec.status === "rejected") &&
                <button className="ok" onClick={() => doAction("approve")} disabled={busy}>Approve</button>}
              {(rec.status === "pending" || rec.status === "flagged") &&
                <button className="danger" onClick={() => doAction("reject")} disabled={busy}>Reject</button>}
              {rec.status === "approved" &&
                <button className="lock" onClick={() => doAction("lock")} disabled={busy}>Lock for audit</button>}
            </div>
          )}

          <h3>Audit trail</h3>
          <table className="grid">
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Field</th><th>From → To</th></tr></thead>
            <tbody>
              {rec.audit_events.map((e) => (
                <tr key={e.id}>
                  <td className="muted small">{new Date(e.created_at).toLocaleString()}</td>
                  <td>{e.actor || "—"}</td>
                  <td>{e.action}</td>
                  <td>{e.field || "—"}</td>
                  <td className="muted small">{e.old_value || "—"} → {e.new_value || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
