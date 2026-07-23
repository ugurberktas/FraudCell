"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  activeVerificationCases,
  highRiskQuickFill,
  normalQuickFill,
  unseenVerificationIds,
} from "./demo-utils.mjs";

interface ServiceStatus { name: string; displayName: string; status: "healthy" | "unavailable"; }
interface PlatformHealthResponse { services: ServiceStatus[]; }
interface QuickFill {
  amount: string;
  transaction_type: string;
  recipient: string;
  source_device: string;
  city: string;
  occurred_at: string;
  transaction_frequency_24h: number;
  is_new_device: boolean;
  home_city: string;
}
interface TransactionItem {
  transaction: { id: string; transaction_number: string; amount: string; city: string; occurred_at: string; risk_score: string | null; risk_level: string; decision: string; };
  case: null | { id: string; status: string; feedback: null | { rating: number } };
}

async function api(path: string, options: RequestInit = {}) {
  const response = await fetch(`/api/gateway/${path}`, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) }, cache: "no-store" });
  const body = await response.json();
  if (!response.ok || !body.success) throw new Error(body.error?.code || `HTTP_${response.status}`);
  return body.data;
}

export default function Home() {
  const [health, setHealth] = useState<PlatformHealthResponse | null>(null);
  const [gsm, setGsm] = useState("05550000001");
  const [otp, setOtp] = useState("");
  const [token, setToken] = useState("");
  const [items, setItems] = useState<TransactionItem[]>([]);
  const [form, setForm] = useState<QuickFill>(highRiskQuickFill());
  const [toast, setToast] = useState("");
  const [message, setMessage] = useState("");
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const seenNotifications = useRef(new Set<string>());

  useEffect(() => { fetch("/api/platform-health", { cache: "no-store" }).then((r) => r.json()).then(setHealth).catch(() => setHealth(null)); }, []);

  const loadTransactions = useCallback(async () => {
    if (!token) return;
    const data = await api("transactions/transactions/me", { headers: { Authorization: `Bearer ${token}` } });
    const nextItems: TransactionItem[] = data.items;
    const unseen: string[] = unseenVerificationIds(nextItems, seenNotifications.current);
    if (unseen.length) {
      unseen.forEach((id) => seenNotifications.current.add(id));
      setToast("Şüpheli işlem doğrulaması gerekiyor.");
    }
    setItems(nextItems);
  }, [token]);

  useEffect(() => {
    if (!token) return;
    loadTransactions();
    const timer = window.setInterval(loadTransactions, 5000);
    return () => window.clearInterval(timer);
  }, [token, loadTransactions]);

  async function requestOtp() {
    try { await api("auth/customers/login/otp/request", { method: "POST", body: JSON.stringify({ gsm }) }); setMessage("OTP isteği oluşturuldu."); }
    catch (error) { setMessage(String(error)); }
  }

  async function login() {
    try { const data = await api("auth/customers/login", { method: "POST", body: JSON.stringify({ gsm, otp_code: otp }) }); setToken(data.access_token); setMessage("Demo müşteri girişi başarılı."); }
    catch (error) { setMessage(String(error)); }
  }

  async function createTransaction() {
    try {
      const data = await api("transactions/transactions", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify({ ...form, amount: Number(form.amount) }) });
      setMessage(`${data.transaction.transaction_number}: ${data.transaction.risk_level} / ${data.transaction.decision}`);
      await loadTransactions();
    } catch (error) { setMessage(String(error)); }
  }

  async function respond(caseId: string, response: "BEN_YAPTIM" | "BEN_YAPMADIM") {
    await api(`transactions/cases/${caseId}/customer-response`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify({ response }) });
    setToast("");
    await loadTransactions();
  }

  async function submitFeedback(caseId: string) {
    await api(`transactions/cases/${caseId}/feedback`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify({ rating: ratings[caseId] || 5 }) });
    setMessage("Geri bildiriminiz için teşekkürler.");
    await loadTransactions();
  }

  const verifications: TransactionItem[] = activeVerificationCases(items);

  return (
    <main className="container wide">
      <header className="header"><div><h1 className="title">FraudCell Golden Demo</h1><p className="service-id">Gerçek servisler, AI ve RabbitMQ akışı</p></div></header>
      {toast && <div className="toast">{toast}<button onClick={() => setToast("")} aria-label="Kapat">×</button></div>}
      <section className="panel"><h2>Platform</h2><div className="status-row">{health?.services.map((service) => <span key={service.name} className={`badge ${service.status === "healthy" ? "badge-healthy" : "badge-unavailable"}`}>{service.displayName}</span>)}</div></section>

      <section className="panel"><h2>Demo müşteri girişi</h2><div className="form-grid"><input aria-label="GSM" value={gsm} onChange={(e) => setGsm(e.target.value)} /><input aria-label="OTP" value={otp} onChange={(e) => setOtp(e.target.value)} placeholder="OTP" /><button onClick={requestOtp}>OTP iste</button><button onClick={login}>Giriş yap</button></div></section>

      {verifications.map((item) => <section className="verification" key={item.case!.id}><strong>Şüpheli işlem doğrulaması gerekiyor.</strong><p>{item.transaction.transaction_number} · {item.transaction.amount} TL · {item.transaction.city} · {new Date(item.transaction.occurred_at).toLocaleString("tr-TR")}</p><div><button onClick={() => respond(item.case!.id, "BEN_YAPTIM")}>Bu işlemi ben yaptım</button><button className="danger" onClick={() => respond(item.case!.id, "BEN_YAPMADIM")}>Bu işlemi ben yapmadım</button></div></section>)}

      {token && <>
        <section className="panel"><div className="section-title"><h2>Yeni işlem</h2><div><button onClick={() => setForm(highRiskQuickFill())}>Yüksek risk hızlı doldur</button><button onClick={() => setForm(normalQuickFill())}>Normal işlem</button></div></div><div className="form-grid transaction-form"><input aria-label="Tutar" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /><select value={form.transaction_type} onChange={(e) => setForm({ ...form, transaction_type: e.target.value })}><option>TRANSFER</option><option>FATURA</option><option>ODEME</option><option>CEKIM</option></select><input value={form.recipient} onChange={(e) => setForm({ ...form, recipient: e.target.value })} /><input value={form.source_device} onChange={(e) => setForm({ ...form, source_device: e.target.value })} /><input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /><input value={form.occurred_at} onChange={(e) => setForm({ ...form, occurred_at: e.target.value })} /><button onClick={createTransaction}>İşlemi gönder</button></div></section>
        <section className="panel"><h2>İşlem geçmişi</h2>{items.map((item) => <article className="transaction" key={item.transaction.id}><div><strong>{item.transaction.transaction_number}</strong><p>{item.transaction.amount} TL · {item.transaction.city} · {item.transaction.risk_level}</p><small>{item.case?.status || "Vaka yok"}</small></div>{item.case?.status === "KAPANDI" && !item.case.feedback && <div className="feedback"><select aria-label="Yıldız" value={ratings[item.case.id] || 5} onChange={(e) => setRatings({ ...ratings, [item.case!.id]: Number(e.target.value) })}>{[1,2,3,4,5].map((rating) => <option key={rating} value={rating}>{"★".repeat(rating)}</option>)}</select><button onClick={() => submitFeedback(item.case!.id)}>Gönder</button></div>}{item.case?.feedback && <span>Teşekkürler · {item.case.feedback.rating}/5</span>}</article>)}</section>
      </>}
      {message && <div className="banner banner-warning">{message}</div>}
    </main>
  );
}
