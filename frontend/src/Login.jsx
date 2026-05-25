import { useState } from "react";
import { api } from "./api";

export default function Login({ onLogin }) {
  const [username, setU] = useState("analyst");
  const [password, setP] = useState("analyst123");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api.login(username, password);
      onLogin();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <h1>Breathe ESG</h1>
        <p className="muted">Emissions data review console</p>
        <label>Username<input value={username} onChange={(e) => setU(e.target.value)} /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setP(e.target.value)} /></label>
        {err && <div className="error">{err}</div>}
        <button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="muted small">Demo: analyst / analyst123</p>
      </form>
    </div>
  );
}
