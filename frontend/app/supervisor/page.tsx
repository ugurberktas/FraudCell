"use client";

import { useCallback, useEffect, useState } from "react";
import { DemoShell } from "../components/DemoShell";
import { RequireSession } from "../components/RequireSession";
import { api, authHeader } from "../lib/api";
import type { AuthSession, RiskCase } from "../lib/types";

export default function SupervisorPage() {
  return <RequireSession allowed={["SUPERVISOR", "ADMIN"]}>{(session) => <SupervisorWorkspace session={session} />}</RequireSession>;
}

function SupervisorWorkspace({ session }: { session: AuthSession }) {
  const [cases, setCases] = useState<RiskCase[]>([]);
  const [analystId, setAnalystId] = useState("");
  const [message, setMessage] = useState("");

  const loadCases = useCallback(async () => {
    const data = await api<{ items: RiskCase[] }>("transactions/cases", { headers: authHeader(session.access_token) });
    setCases(data.items);
  }, [session.access_token]);

  useEffect(() => { loadCases().catch((error) => setMessage(error.message)); }, [loadCases]);

  async function assign(caseId: string) {
    try {
      await api(`transactions/cases/${caseId}/assign`, {
        method: "POST",
        headers: authHeader(session.access_token),
        body: JSON.stringify({ analyst_id: analystId }),
      });
      await loadCases();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Atama basarisiz");
    }
  }

  async function close(caseId: string) {
    try {
      await api(`transactions/cases/${caseId}/close`, { method: "POST", headers: authHeader(session.access_token), body: "{}" });
      await loadCases();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Kapama basarisiz");
    }
  }

  return (
    <DemoShell session={session} title={session.user.role === "ADMIN" ? "Admin Gorunumu" : "Supervisor Paneli"}>
      <section className="panel">
        <h2>Vaka havuzu</h2>
        <label>Manuel analyst UUID<input value={analystId} onChange={(event) => setAnalystId(event.target.value)} placeholder="Analyst UUID" /></label>
        {cases.map((item) => (
          <article className="transaction" key={item.id}>
            <div>
              <strong>{item.transaction?.transaction_number || item.id}</strong>
              <p>{item.transaction?.amount} TL · {item.transaction?.city} · {item.transaction?.risk_level} · {item.status}</p>
              <small>Analyst: {item.assigned_analyst_id || "Atanmadi"}</small>
            </div>
            <div className="button-row">
              {session.user.role === "SUPERVISOR" && item.status === "YENI" && <button onClick={() => assign(item.id)}>Ata</button>}
              {session.user.role === "SUPERVISOR" && ["ONAYLANDI", "BLOKLANDI"].includes(item.status) && <button onClick={() => close(item.id)}>Kapat</button>}
            </div>
          </article>
        ))}
      </section>
      {message && <div className="banner banner-warning">{message}</div>}
    </DemoShell>
  );
}
