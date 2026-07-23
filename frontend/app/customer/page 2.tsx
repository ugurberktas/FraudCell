"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DemoShell } from "../components/DemoShell";
import { RequireSession } from "../components/RequireSession";
import { activeVerificationCases, highRiskQuickFill, normalQuickFill, unseenVerificationIds } from "../demo-utils.mjs";
import { api, authHeader } from "../lib/api";
import type { QuickFill, TransactionItem } from "../lib/types";

export default function CustomerPage() {
  return <RequireSession allowed={["CUSTOMER"]}>{(session) => <CustomerWorkspace session={session} />}</RequireSession>;
}

function CustomerWorkspace({ session }: { session: import("../lib/types").AuthSession }) {
  const [items, setItems] = useState<TransactionItem[]>([]);
  const [form, setForm] = useState<QuickFill>(highRiskQuickFill());
  const [toast, setToast] = useState("");
  const [message, setMessage] = useState("");
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const seenNotifications = useRef(new Set<string>());

  const loadTransactions = useCallback(async () => {
    const data = await api<{ items: TransactionItem[] }>("transactions/transactions/me", { headers: authHeader(session.access_token) });
    const nextItems = data.items;
    const unseen = unseenVerificationIds(nextItems, seenNotifications.current);
    if (unseen.length) {
      unseen.forEach((id: string) => seenNotifications.current.add(id));
      setToast("Supheli islem dogrulamasi gerekiyor.");
    }
    setItems(nextItems);
  }, [session.access_token]);

  useEffect(() => {
    loadTransactions().catch((error) => setMessage(error.message));
    const timer = window.setInterval(() => loadTransactions().catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  }, [loadTransactions]);

  async function createTransaction() {
    try {
      const data = await api<TransactionItem>("transactions/transactions", {
        method: "POST",
        headers: authHeader(session.access_token),
        body: JSON.stringify({ ...form, amount: Number(form.amount) }),
      });
      setMessage(`${data.transaction.transaction_number}: ${data.transaction.risk_level} / ${data.transaction.decision}`);
      await loadTransactions();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Islem basarisiz");
    }
  }

  async function respond(caseId: string, response: "BEN_YAPTIM" | "BEN_YAPMADIM") {
    await api(`transactions/cases/${caseId}/customer-response`, {
      method: "POST",
      headers: authHeader(session.access_token),
      body: JSON.stringify({ response }),
    });
    setToast("");
    await loadTransactions();
  }

  async function submitFeedback(caseId: string) {
    await api(`transactions/cases/${caseId}/feedback`, {
      method: "POST",
      headers: authHeader(session.access_token),
      body: JSON.stringify({ rating: ratings[caseId] || 5 }),
    });
    setMessage("Geri bildiriminiz icin tesekkurler.");
    await loadTransactions();
  }

  const verifications = activeVerificationCases(items);

  return (
    <DemoShell session={session} title="Musteri Demo">
      {toast && <div className="toast">{toast}<button onClick={() => setToast("")} aria-label="Kapat">x</button></div>}
      {verifications.map((item: TransactionItem) => (
        <section className="verification" key={item.case!.id}>
          <strong>Supheli islem dogrulamasi gerekiyor.</strong>
          <p>{item.transaction.transaction_number} · {item.transaction.amount} TL · {item.transaction.city} · {new Date(item.transaction.occurred_at).toLocaleString("tr-TR")}</p>
          <div>
            <button onClick={() => respond(item.case!.id, "BEN_YAPTIM")}>Bu islemi ben yaptim</button>
            <button className="danger" onClick={() => respond(item.case!.id, "BEN_YAPMADIM")}>Bu islemi ben yapmadim</button>
          </div>
        </section>
      ))}

      <section className="panel">
        <div className="section-title">
          <h2>Yeni islem</h2>
          <div>
            <button onClick={() => setForm(highRiskQuickFill())}>Yuksek risk hizli doldur</button>
            <button onClick={() => setForm(normalQuickFill())}>Normal islem</button>
          </div>
        </div>
        <div className="form-grid transaction-form">
          <input aria-label="Tutar" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} />
          <select value={form.transaction_type} onChange={(event) => setForm({ ...form, transaction_type: event.target.value })}><option>TRANSFER</option><option>FATURA</option><option>ODEME</option><option>CEKIM</option></select>
          <input aria-label="Alici" value={form.recipient} onChange={(event) => setForm({ ...form, recipient: event.target.value })} />
          <input aria-label="Cihaz" value={form.source_device} onChange={(event) => setForm({ ...form, source_device: event.target.value })} />
          <input aria-label="Sehir" value={form.city} onChange={(event) => setForm({ ...form, city: event.target.value })} />
          <input aria-label="Zaman" value={form.occurred_at} onChange={(event) => setForm({ ...form, occurred_at: event.target.value })} />
          <button onClick={createTransaction}>Islemi gonder</button>
        </div>
      </section>

      <section className="panel">
        <h2>Islem gecmisi</h2>
        {items.map((item) => (
          <article className="transaction" key={item.transaction.id}>
            <div>
              <strong>{item.transaction.transaction_number}</strong>
              <p>{item.transaction.amount} TL · {item.transaction.city} · {item.transaction.risk_level} · {item.transaction.decision}</p>
              <small>{item.case?.status || "Vaka yok"}</small>
            </div>
            {item.case?.status === "KAPANDI" && !item.case.feedback && (
              <div className="feedback">
                <select aria-label="Yildiz" value={ratings[item.case.id] || 5} onChange={(event) => setRatings({ ...ratings, [item.case!.id]: Number(event.target.value) })}>{[1,2,3,4,5].map((rating) => <option key={rating} value={rating}>{"*".repeat(rating)}</option>)}</select>
                <button onClick={() => submitFeedback(item.case!.id)}>Gonder</button>
              </div>
            )}
            {item.case?.feedback && <span>Tesekkurler · {item.case.feedback.rating}/5</span>}
          </article>
        ))}
      </section>
      {message && <div className="banner banner-warning">{message}</div>}
    </DemoShell>
  );
}
