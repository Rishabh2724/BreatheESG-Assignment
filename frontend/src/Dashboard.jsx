import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { fmt } from "./ui";

const SOURCE_LABEL = {
  SAP: "SAP — fuel & procurement",
  UTILITY: "Utility — electricity",
  TRAVEL: "Corporate travel",
};

export default function Dashboard({ onOpenBatch }) {
  const [summary, setSummary] = useState(null);
  const [batches, setBatches] = useState([]);
  const [source, setSource] = useState("SAP");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const fileRef = useRef();

  async function load() {
    const [s, b] = await Promise.all([api.summary(), api.batches()]);
    setSummary(s);
    setBatches(b.results);
  }
  useEffect(() => { load(); }, []);

  async function upload(e) {
    e.preventDefault();
    const file = fileRef.current.files[0];
    if (!file) return;
    setBusy(true);
    setMsg("");
    try {
      const batch = await api.upload(source, file);
      setMsg(`Ingested ${batch.filename}: ${batch.rows_ok} ok, ${batch.rows_flagged} flagged, ${batch.rows_failed} failed.`);
      fileRef.current.value = "";
      load();
    } catch (e) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  const co2e = summary?.co2e_by_scope_kg || {};
  return (
    <div className="stack">
      <section className="cards">
        <Card label="Total records" value={fmt(summary?.total_records)} />
        <Card label="Pending review" value={fmt(summary?.by_status?.pending || 0)} accent="#6b7280" />
        <Card label="Flagged" value={fmt(summary?.by_status?.flagged || 0)} accent="#b45309" />
        <Card label="Locked (audit-sealed)" value={fmt(summary?.by_status?.locked || 0)} accent="#1d4ed8" />
      </section>

      <section className="cards">
        <Card label="Scope 1 tCO₂e" value={fmt((co2e.scope_1 || 0) / 1000)} sub="fuel combustion" />
        <Card label="Scope 2 tCO₂e" value={fmt((co2e.scope_2 || 0) / 1000)} sub="purchased electricity" />
        <Card label="Scope 3 tCO₂e" value={fmt((co2e.scope_3 || 0) / 1000)} sub="travel + procurement" />
        <Card label="Locked tCO₂e" value={fmt((summary?.locked_co2e_kg || 0) / 1000)} sub="auditor-ready" accent="#1d4ed8" />
      </section>

      <section className="card">
        <h2>Ingest a file</h2>
        <form className="upload-row" onSubmit={upload}>
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            {Object.entries(SOURCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input type="file" ref={fileRef} accept=".csv,.json" />
          <button disabled={busy}>{busy ? "Ingesting…" : "Upload & ingest"}</button>
        </form>
        {msg && <div className="muted small">{msg}</div>}
      </section>

      <section className="card">
        <h2>Import batches</h2>
        <table className="grid">
          <thead>
            <tr><th>Source</th><th>File</th><th>OK</th><th>Flagged</th><th>Failed</th><th>When</th><th></th></tr>
          </thead>
          <tbody>
            {batches.map((b) => (
              <tr key={b.id}>
                <td>{SOURCE_LABEL[b.source_type] || b.source_type}</td>
                <td>{b.filename}</td>
                <td className="num">{b.rows_ok}</td>
                <td className="num warn">{b.rows_flagged}</td>
                <td className="num bad">{b.rows_failed}</td>
                <td className="muted small">{new Date(b.created_at).toLocaleString()}</td>
                <td><button className="link" onClick={() => onOpenBatch(b)}>Review →</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Card({ label, value, sub, accent }) {
  return (
    <div className="card stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={accent ? { color: accent } : null}>{value}</div>
      {sub && <div className="muted small">{sub}</div>}
    </div>
  );
}
