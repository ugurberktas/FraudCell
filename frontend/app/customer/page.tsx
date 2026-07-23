"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DemoShell } from "../components/DemoShell";
import { RequireSession } from "../components/RequireSession";
import { activeVerificationCases, highRiskQuickFill, normalQuickFill, unseenVerificationIds } from "../demo-utils.mjs";
import { api, authHeader } from "../lib/api";
import { apiErrorText } from "../lib/ui-utils.mjs";
import type { AuthSession, QuickFill, TransactionItem } from "../lib/types";

export default function CustomerPage() {
  return <RequireSession allowed={["CUSTOMER"]}>{(session) => <CustomerWorkspace session={session} />}</RequireSession>;
}

function CustomerWorkspace({ session }: { session: AuthSession }) {
  const [items, setItems] = useState<TransactionItem[]>([]);
  const [form, setForm] = useState<QuickFill>(highRiskQuickFill());
  const [toast, setToast] = useState("");
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState<{ text: string; kind: "success" | "warning" | "error" } | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [latestResult, setLatestResult] = useState<TransactionItem | null>(null);
  const seenNotifications = useRef(new Set<string>());

  const loadTransactions = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    try {
      const data = await api<{ items: TransactionItem[] }>("transactions/transactions/me", { headers: authHeader(session.access_token) });
      const nextItems = data.items;
      const unseen = unseenVerificationIds(nextItems, seenNotifications.current);
      if (unseen.length) {
        unseen.forEach((id: string) => seenNotifications.current.add(id));
        setToast("Şüpheli işlem doğrulaması gerekiyor.");
      }
      setItems(nextItems);
      setLoadError("");
    } catch (error) {
      setLoadError(apiErrorText(error, "İşlem geçmişi yüklenemedi"));
    } finally {
      if (showLoader) setLoading(false);
    }
  }, [session.access_token]);

  useEffect(() => {
    void loadTransactions(true);
    const timer = window.setInterval(() => void loadTransactions(), 5000);
    return () => window.clearInterval(timer);
  }, [loadTransactions]);

  async function createTransaction() {
    setPending("create");
    setNotice(null);
    try {
      const data = await api<TransactionItem>("transactions/transactions", {
        method: "POST",
        headers: authHeader(session.access_token),
        body: JSON.stringify({ ...form, amount: Number(form.amount) }),
      });
      setLatestResult(data);
      setNotice({
        text: `${data.transaction.transaction_number} başarıyla kaydedildi.`,
        kind: data.ai_fallback || data.transaction.ai_status === "UNAVAILABLE" ? "warning" : "success",
      });
      await loadTransactions();
    } catch (error) {
      setNotice({ text: apiErrorText(error, "İşlem oluşturulamadı"), kind: "error" });
    } finally {
      setPending(null);
    }
  }

  async function respond(caseId: string, response: "BEN_YAPTIM" | "BEN_YAPMADIM") {
    setPending(`verify:${caseId}`);
    setNotice(null);
    try {
      await api(`transactions/cases/${caseId}/customer-response`, {
        method: "POST",
        headers: authHeader(session.access_token),
        body: JSON.stringify({ response }),
      });
      setToast("");
      setNotice({ text: "Müşteri doğrulama yanıtı kaydedildi.", kind: "success" });
      await loadTransactions();
    } catch (error) {
      setNotice({ text: apiErrorText(error, "Doğrulama yanıtı kaydedilemedi"), kind: "error" });
    } finally {
      setPending(null);
    }
  }

  async function submitFeedback(caseId: string) {
    setPending(`feedback:${caseId}`);
    setNotice(null);
    try {
      await api(`transactions/cases/${caseId}/feedback`, {
        method: "POST",
        headers: authHeader(session.access_token),
        body: JSON.stringify({ rating: ratings[caseId] || 5 }),
      });
      setNotice({ text: "Geri bildiriminiz için teşekkürler.", kind: "success" });
      await loadTransactions();
    } catch (error) {
      setNotice({ text: apiErrorText(error, "Geri bildirim gönderilemedi"), kind: "error" });
    } finally {
      setPending(null);
    }
  }

  const verifications = activeVerificationCases(items);
  const latestAi = latestResult?.ai_result;
  const latestReasons = latestAi?.risk_reasons || latestResult?.transaction.risk_reasons || [];
  const latestFallback = Boolean(latestResult?.ai_fallback || latestResult?.transaction.ai_status === "UNAVAILABLE");

  return (
    <DemoShell session={session} title="Musteri Demo">
      {toast && <div className="toast">{toast}<button onClick={() => setToast("")} aria-label="Kapat">x</button></div>}
      {loadError && <div role="alert" className="banner banner-error">{loadError}</div>}
      {notice && <div role="status" className={`banner banner-${notice.kind}`}>{notice.text}</div>}

      {verifications.map((item: TransactionItem) => (
        <section className="verification" key={item.case!.id}>
          <strong>Şüpheli işlem doğrulaması gerekiyor.</strong>
          <p>{item.transaction.transaction_number} · {item.transaction.amount} TL · {item.transaction.city} · {new Date(item.transaction.occurred_at).toLocaleString("tr-TR")}</p>
          <div>
            <button disabled={pending !== null} onClick={() => respond(item.case!.id, "BEN_YAPTIM")}>Bu işlemi ben yaptım</button>
            <button disabled={pending !== null} className="danger" onClick={() => respond(item.case!.id, "BEN_YAPMADIM")}>Bu işlemi ben yapmadım</button>
          </div>
        </section>
      ))}

      <section className="panel">
        <div className="section-title">
          <h2>Yeni işlem</h2>
          <div>
            <button disabled={pending !== null} onClick={() => setForm(highRiskQuickFill())}>Yüksek risk hızlı doldur</button>
            <button disabled={pending !== null} onClick={() => setForm(normalQuickFill())}>Normal işlem</button>
          </div>
        </div>
        <div className="form-grid transaction-form">
          <input disabled={pending !== null} aria-label="Tutar" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} />
          <select disabled={pending !== null} aria-label="İşlem türü" value={form.transaction_type} onChange={(event) => setForm({ ...form, transaction_type: event.target.value })}><option>TRANSFER</option><option>FATURA</option><option>ODEME</option><option>CEKIM</option></select>
          <input disabled={pending !== null} aria-label="Alici" value={form.recipient} onChange={(event) => setForm({ ...form, recipient: event.target.value })} />
          <input disabled={pending !== null} aria-label="Cihaz" value={form.source_device} onChange={(event) => setForm({ ...form, source_device: event.target.value })} />
          <input disabled={pending !== null} aria-label="Sehir" value={form.city} onChange={(event) => setForm({ ...form, city: event.target.value })} />
          <input disabled={pending !== null} aria-label="Zaman" value={form.occurred_at} onChange={(event) => setForm({ ...form, occurred_at: event.target.value })} />
          <button disabled={pending !== null || !form.amount} onClick={createTransaction}>{pending === "create" ? "Gönderiliyor..." : "İşlemi gönder"}</button>
        </div>
      </section>

      {latestResult && (
        <section className="panel ai-result">
          <h2>Son AI değerlendirmesi</h2>
          {latestFallback && <div className="banner banner-warning">AI Service kullanılamıyor. İşlem kaydedildi ve manuel inceleme vakası oluşturuldu.</div>}
          <div className="details-grid">
            <span><small>AI durumu</small><strong>{latestResult.transaction.ai_status || latestAi?.status || "-"}</strong></span>
            <span><small>Risk skoru</small><strong>{latestAi?.risk_score ?? latestResult.transaction.risk_score ?? "-"}</strong></span>
            <span><small>Risk seviyesi</small><strong>{latestAi?.risk_level || latestResult.transaction.risk_level}</strong></span>
            <span><small>Fraud türü</small><strong>{latestAi?.fraud_type || latestResult.transaction.fraud_type}</strong></span>
            <span><small>Karar</small><strong>{latestAi?.decision || latestResult.transaction.decision}</strong></span>
            <span><small>Model</small><strong>{latestAi?.model_version || latestResult.transaction.model_version || "-"}</strong></span>
            <span><small>Atama durumu</small><strong>{latestAi?.assignment_status || (latestResult.case?.assigned_analyst_id ? "ASSIGNED" : "-")}</strong></span>
            <span><small>Atanan analyst</small><strong>{latestAi?.assigned_analyst_id || latestResult.case?.assigned_analyst_id || "-"}</strong></span>
          </div>
          <h3>Risk nedenleri</h3>
          {latestReasons.length ? <ul className="risk-reasons">{latestReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <p className="empty-state compact">Risk nedeni dönmedi.</p>}
        </section>
      )}

      <section className="panel">
        <h2>İşlem geçmişi</h2>
        {loading ? (
          <div className="loading-container"><span className="spinner" />Yükleniyor...</div>
        ) : loadError && items.length === 0 ? (
          <p className="empty-state">İşlem verisi şu anda gösterilemiyor.</p>
        ) : items.length === 0 ? (
          <p className="empty-state">Henüz işlem bulunmuyor.</p>
        ) : items.map((item) => {
          const reasons = item.transaction.risk_reasons || item.case?.risk_reasons || [];
          return (
            <article className="case-item" key={item.transaction.id}>
              <div className="section-title">
                <div>
                  <strong>{item.transaction.transaction_number}</strong>
                  <p>{item.transaction.amount} TL · {item.transaction.city} · {item.transaction.risk_level} · {item.transaction.decision}</p>
                  <small>AI: {item.transaction.ai_status || "-"} · Skor: {item.transaction.risk_score ?? "-"} · Tür: {item.transaction.fraud_type} · Model: {item.transaction.model_version || "-"}</small>
                </div>
                <div><strong>{item.case?.status || "Vaka yok"}</strong>{item.case?.assigned_analyst_id && <small>Analyst: {item.case.assigned_analyst_id}</small>}</div>
              </div>
              {item.transaction.ai_status === "UNAVAILABLE" && <p className="hint">AI kullanılamadı; manuel inceleme akışı aktiftir.</p>}
              {reasons.length > 0 && <ul className="risk-reasons">{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
              {item.case?.history && item.case.history.length > 0 && (
                <div className="timeline">
                  <h3>Vaka zaman çizelgesi</h3>
                  <ol>{item.case.history.map((entry) => (
                    <li key={entry.id}>
                      <strong>{entry.from_status || "BAŞLANGIÇ"} → {entry.to_status}</strong>
                      <span>{new Date(entry.created_at).toLocaleString("tr-TR")}{entry.note ? ` · ${entry.note}` : ""}</span>
                    </li>
                  ))}</ol>
                </div>
              )}
              {item.case?.customer_response && <p className="hint">Müşteri yanıtı: {item.case.customer_response}</p>}
              {item.case?.status === "KAPANDI" && !item.case.feedback && (
                <div className="feedback">
                  <select disabled={pending !== null} aria-label="Yildiz" value={ratings[item.case.id] || 5} onChange={(event) => setRatings({ ...ratings, [item.case!.id]: Number(event.target.value) })}>{[1,2,3,4,5].map((rating) => <option key={rating} value={rating}>{"*".repeat(rating)}</option>)}</select>
                  <button disabled={pending !== null} onClick={() => submitFeedback(item.case!.id)}>{pending === `feedback:${item.case.id}` ? "Gönderiliyor..." : "Geri bildirim gönder"}</button>
                </div>
              )}
              {item.case?.feedback && <span>Teşekkürler · {item.case.feedback.rating}/5</span>}
            </article>
          );
        })}
      </section>
    </DemoShell>
  );
}
