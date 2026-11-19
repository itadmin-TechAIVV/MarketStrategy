import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Workspace } from "../api";
import TopBar from "../components/TopBar";

export default function WorkspacesPage() {
  const [items, setItems] = useState<Workspace[] | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.listWorkspaces().then(setItems).catch((e) => setError(e.message));
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const ws = await api.createWorkspace(name, url);
      navigate(`/w/${ws.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create workspace");
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <TopBar />
      <main className="container">
        <section className="card new-ws">
          <h1>New strategy workspace</h1>
          <p className="muted">One workspace per product. Paste the product's website and the agent will study it first.</p>
          <form onSubmit={create} className="row-form">
            <input required placeholder="Product name" value={name} onChange={(e) => setName(e.target.value)} />
            <input required placeholder="https://yourproduct.com" value={url} onChange={(e) => setUrl(e.target.value)} />
            <button className="btn primary" disabled={busy}>
              {busy ? "Creating…" : "Start"}
            </button>
          </form>
          {error && <div className="error">{error}</div>}
        </section>

        <h2>Your workspaces</h2>
        {items === null ? (
          <p className="muted">Loading…</p>
        ) : items.length === 0 ? (
          <p className="muted">No workspaces yet.</p>
        ) : (
          <ul className="ws-list">
            {items.map((w) => (
              <li key={w.id} className="card ws-item">
                <Link to={`/w/${w.id}`}>
                  <strong>{w.product_name}</strong>
                  <span className="muted">{w.website_url}</span>
                </Link>
                <span className="pill">{w.current_stage}</span>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
