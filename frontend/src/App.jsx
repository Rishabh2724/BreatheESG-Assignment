import { useEffect, useState } from "react";
import { api, clearToken, getToken } from "./api";
import Dashboard from "./Dashboard";
import Login from "./Login";
import Review from "./Review";

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [me, setMe] = useState(null);
  const [view, setView] = useState({ name: "dashboard" });

  useEffect(() => {
    if (!authed) return;
    api.me().then(setMe).catch(() => { clearToken(); setAuthed(false); });
  }, [authed]);

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand" onClick={() => setView({ name: "dashboard" })}>Breathe ESG</div>
        <nav>
          <button className="link" onClick={() => setView({ name: "dashboard" })}>Dashboard</button>
          <button className="link" onClick={() => setView({ name: "review", batch: null })}>All records</button>
        </nav>
        <div className="who">
          {me && <span className="muted small">{me.org} · {me.username} ({me.role})</span>}
          <button className="link" onClick={() => { clearToken(); setAuthed(false); }}>Sign out</button>
        </div>
      </header>
      <main className="content">
        {view.name === "dashboard" && (
          <Dashboard onOpenBatch={(batch) => setView({ name: "review", batch })} />
        )}
        {view.name === "review" && (
          <Review batch={view.batch} onBack={() => setView({ name: "dashboard" })} />
        )}
      </main>
    </div>
  );
}
