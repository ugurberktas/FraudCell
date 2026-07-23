"use client";

import { useCallback, useEffect, useState } from "react";
import { DemoShell } from "../components/DemoShell";
import { RequireSession } from "../components/RequireSession";
import { api, authHeader } from "../lib/api";
import type { AuthSession, RiskCase } from "../lib/types";

export default function AnalystPage() {
  return <RequireSession allowed={["ANALYST"]}>{(session) => <AnalystWorkspace session={session} />}</RequireSession>;
}

function AnalystWorkspace({ session }: { session: AuthSession }) {
  const [cases, setCases] = useState<RiskCase[]>([]);
  const [message, setMessage] = useState("");

  const loadCases = useCallback(async () => {
    const data = await api<{ items: RiskCase[] }>("transactions/cases/assigned-to-me", { headers: authHeader(session.access_token) });
    setCases(data.items);
  }, [session.access_token]);

  useEffect(() => { loadCases().catch((error) => setMessage(error.message)); }, [loadCases]);

  async function action(caseId: string, path: string, body?: object) {
    try {
      await api(`transactions/cases/${caseId}/${path}`, {
        method: "POST",
        headers: authHeader(session.access_token),
        body: body ? JSON.stringify(body) : "{}",
      });
      await loadCases();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Islem basarisiz");
    }
  }

  return (
    <DemoShell session={session} title="Analist Vakalari">
      <section className="panel"><h2>Bana atanan vakalar</h2>{cases.map((item) => (
        <article className="transaction" key={item.id}>
          <div>
            <strong>{item.transaction?.transaction_number || item.id}</strong>
            <p>{item.transaction?.amount} TL · {item.transaction?.city} · {item.transaction?.risk_level} · {item.status}</p>
            <small>SLA: {item.sla_remaining_seconds ?? "-"} sn</small>
          </div>
          <div className="button-row">
            {item.status === "ATANDI" && <button onClick={() => action(item.id, "start")}>Baslat</button>}
            {item.status === "INCELENIYOR" && <button onClick={() => action(item.id, "request-verification")}>Musteri dogrula</button>}
            {item.status === "INCELENIYOR" && <button onClick={() => action(item.id, "decision", { decision: "ONAYLANDI" })}>Onayla</button>}
            {item.status === "INCELENIYOR" && <button className="danger" onClick={() => action(item.id, "decision", { decision: "BLOKLANDI", note: "Demo supheli islem bloklandi" })}>Blokla</button>}
          </div>
        </article>
      ))}</section>
      {message && <div className="banner banner-warning">{message}</div>}
    </DemoShell>
  );
}
