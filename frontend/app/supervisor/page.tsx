"use client";

import { useCallback, useEffect, useState } from "react";
import { DemoShell } from "../components/DemoShell";
import { RequireSession } from "../components/RequireSession";
import { api, authHeader } from "../lib/api";
import { apiErrorText, countBy, isUuid, summarizeCases } from "../lib/ui-utils.mjs";
import type { AuthSession, RiskCase } from "../lib/types";

export default function SupervisorPage() {
  return <RequireSession allowed={["SUPERVISOR", "ADMIN"]}>{(session) => <SupervisorWorkspace session={session} />}</RequireSession>;
}

function Distribution({ title, values }: { title: string; values: Array<{ label: string; count: number }> }) {
  return (
    <div className="distribution-card">
      <h3>{title}</h3>
      {values.length === 0 ? <p className="empty-state compact">Veri yok</p> : values.map((item) => (
        <div className="distribution-row" key={item.label}><span>{item.label}</span><strong>{item.count}</strong></div>
      ))}
    </div>
  );
}

function SupervisorWorkspace({ session }: { session: AuthSession }) {
  const [cases, setCases] = useState<RiskCase[]>([]);
  const [assignmentIds, setAssignmentIds] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);

  const loadCases = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    try {
      const data = await api<{ items: RiskCase[] }>("transactions/cases", { headers: authHeader(session.access_token) });
      setCases(data.items);
      setError("");
    } catch (requestError) {
      setError(apiErrorText(requestError, "Supervisor vaka verisi yüklenemedi"));
    } finally {
      if (showLoader) setLoading(false);
    }
  }, [session.access_token]);

  useEffect(() => {
    void loadCases(true);
    const timer = window.setInterval(() => void loadCases(), 5000);
    return () => window.clearInterval(timer);
  }, [loadCases]);

  async function assign(caseId: string) {
    const analystId = (assignmentIds[caseId] || "").trim();
    if (!isUuid(analystId)) {
      setError("Manuel atama için geçerli bir Analyst UUID girin (422).");
      return;
    }
    setPending(`assign:${caseId}`);
    setError("");
    setNotice("");
    try {
      await api(`transactions/cases/${caseId}/assign`, {
        method: "POST",
        headers: authHeader(session.access_token),
        body: JSON.stringify({ analyst_id: analystId }),
      });
      setNotice("Vaka analiste atandı.");
      setAssignmentIds((current) => ({ ...current, [caseId]: "" }));
      await loadCases();
    } catch (requestError) {
      setError(apiErrorText(requestError, "Manuel atama tamamlanamadı"));
    } finally {
      setPending(null);
    }
  }

  async function close(caseId: string) {
    setPending(`close:${caseId}`);
    setError("");
    setNotice("");
    try {
      await api(`transactions/cases/${caseId}/close`, { method: "POST", headers: authHeader(session.access_token), body: "{}" });
      setNotice("Vaka kapatıldı.");
      await loadCases();
    } catch (requestError) {
      setError(apiErrorText(requestError, "Vaka kapatılamadı"));
    } finally {
      setPending(null);
    }
  }

  const summary = summarizeCases(cases);
  const queuedCases = cases.filter((item) => item.status === "YENI" && !item.assigned_analyst_id);
  const riskDistribution = countBy(cases.map((item) => item.transaction?.risk_level));
  const fraudDistribution = countBy(cases.map((item) => item.transaction?.fraud_type));
  const statusDistribution = countBy(cases.map((item) => item.status));

  return (
    <DemoShell session={session} title={session.user.role === "ADMIN" ? "Admin Gorunumu" : "Supervisor Paneli"}>
      {error && <div role="alert" className="banner banner-error">{error}</div>}
      {notice && <div role="status" className="banner banner-success">{notice}</div>}

      <section className="panel">
        <div className="section-title"><h2>Canlı vaka özeti</h2><button className="refresh-btn" disabled={pending !== null} onClick={() => void loadCases(true)}>Yenile</button></div>
        {loading ? (
          <div className="loading-container"><span className="spinner" />Dashboard yükleniyor...</div>
        ) : error && cases.length === 0 ? (
          <p className="empty-state">Dashboard verisi şu anda gösterilemiyor.</p>
        ) : (
          <>
            <div className="metric-grid">
              <div className="metric-card"><small>Aktif vaka</small><strong>{summary.active}</strong></div>
              <div className="metric-card"><small>Kritik vaka</small><strong>{summary.critical}</strong></div>
              <div className="metric-card"><small>SLA aşımı</small><strong>{summary.slaExceeded}</strong></div>
              <div className="metric-card"><small>Bekleyen atama</small><strong>{summary.queued}</strong></div>
            </div>
            <div className="distribution-grid">
              <Distribution title="Risk dağılımı" values={riskDistribution} />
              <Distribution title="Fraud türü dağılımı" values={fraudDistribution} />
              <Distribution title="Vaka durumu dağılımı" values={statusDistribution} />
            </div>
          </>
        )}
      </section>

      <section className="panel">
        <h2>Bekleyen atama kuyruğu</h2>
        {loading || (error && cases.length === 0) ? null : queuedCases.length === 0 ? (
          <p className="empty-state">Atama bekleyen vaka yok.</p>
        ) : queuedCases.map((item) => (
          <article className="case-item" key={`queue:${item.id}`}>
            <div>
              <strong>{item.transaction?.transaction_number || item.id}</strong>
              <p>{item.transaction?.amount} TL · {item.transaction?.city} · {item.transaction?.risk_level} · {item.transaction?.fraud_type}</p>
              <small>AI durumu: {item.transaction?.ai_status || "-"}</small>
            </div>
            {session.user.role === "SUPERVISOR" && (
              <div className="manual-assignment">
                <label>Analyst UUID<input disabled={pending !== null} value={assignmentIds[item.id] || ""} onChange={(event) => setAssignmentIds({ ...assignmentIds, [item.id]: event.target.value })} placeholder="00000000-0000-0000-0000-000000000000" /></label>
                <button disabled={pending !== null || !(assignmentIds[item.id] || "").trim()} onClick={() => void assign(item.id)}>{pending === `assign:${item.id}` ? "Atanıyor..." : "Manuel ata"}</button>
              </div>
            )}
          </article>
        ))}
      </section>

      <section className="panel">
        <h2>Vaka havuzu</h2>
        {loading || (error && cases.length === 0) ? null : cases.length === 0 ? (
          <p className="empty-state">Henüz vaka bulunmuyor.</p>
        ) : cases.map((item) => (
          <article className="case-item" key={item.id}>
            <div className="section-title">
              <div>
                <strong>{item.transaction?.transaction_number || item.id}</strong>
                <p>{item.transaction?.amount} TL · {item.transaction?.city} · {item.transaction?.risk_level} · {item.status}</p>
                <small>Fraud: {item.transaction?.fraud_type || "-"} · Analyst: {item.assigned_analyst_id || "Atanmadı"}</small>
              </div>
              {item.sla_exceeded && <span className="badge badge-unavailable">SLA AŞIMI</span>}
            </div>
            {session.user.role === "SUPERVISOR" && ["ONAYLANDI", "BLOKLANDI"].includes(item.status) && <button disabled={pending !== null} onClick={() => void close(item.id)}>{pending === `close:${item.id}` ? "Kapatılıyor..." : "Vakayı kapat"}</button>}
          </article>
        ))}
      </section>
    </DemoShell>
  );
}
