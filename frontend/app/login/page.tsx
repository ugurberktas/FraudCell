"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../lib/api";
import { routeForRole, storeSession } from "../lib/auth";
import { loginErrorText } from "../lib/ui-utils.mjs";
import type { AuthSession } from "../lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"customer" | "staff">("customer");
  const [gsm, setGsm] = useState("05550000001");
  const [otp, setOtp] = useState("");
  const [email, setEmail] = useState("demo.analyst.card@fraudcell.com");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState<{ text: string; kind: "success" | "error" } | null>(null);
  const [busy, setBusy] = useState<"otp" | "login" | null>(null);
  const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE !== "false";

  async function requestOtp() {
    setBusy("otp");
    setNotice(null);
    try {
      await api("auth/customers/login/otp/request", { method: "POST", body: JSON.stringify({ gsm }) });
      setNotice({ text: "OTP isteği alındı.", kind: "success" });
    } catch (error) {
      setNotice({ text: loginErrorText(error), kind: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function completeLogin(path: string, payload: object) {
    setBusy("login");
    setNotice(null);
    try {
      const session = await api<AuthSession>(path, { method: "POST", body: JSON.stringify(payload) });
      storeSession(session);
      router.replace(routeForRole(session.user.role));
    } catch (error) {
      setNotice({ text: loginErrorText(error), kind: "error" });
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="container auth-container">
      <section className="panel auth-panel">
        <h1 className="title">FraudCell Demo Girisi</h1>
        <div className="tabs">
          <button disabled={busy !== null} className={tab === "customer" ? "tab active" : "tab"} onClick={() => { setTab("customer"); setNotice(null); }}>Musteri</button>
          <button disabled={busy !== null} className={tab === "staff" ? "tab active" : "tab"} onClick={() => { setTab("staff"); setNotice(null); }}>Personel</button>
        </div>

        {tab === "customer" ? (
          <div className="stack">
            <label>GSM<input disabled={busy !== null} autoComplete="tel" value={gsm} onChange={(event) => setGsm(event.target.value)} placeholder="05551234567" /></label>
            <button disabled={busy !== null || !gsm.trim()} onClick={requestOtp}>{busy === "otp" ? "OTP isteniyor..." : "OTP iste"}</button>
            {demoMode && <p className="hint">Demo kodu: 1234</p>}
            <label>OTP<input disabled={busy !== null} autoComplete="one-time-code" value={otp} onChange={(event) => setOtp(event.target.value)} placeholder="1234" /></label>
            <button disabled={busy !== null || !gsm.trim() || !otp.trim()} onClick={() => completeLogin("auth/customers/login", { gsm, otp_code: otp })}>{busy === "login" ? "Giris yapiliyor..." : "Giris yap"}</button>
          </div>
        ) : (
          <div className="stack">
            <label>Email<input disabled={busy !== null} type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="demo.analyst.card@fraudcell.com" /></label>
            <label>Parola<input disabled={busy !== null} type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <button disabled={busy !== null || !email.trim() || !password} onClick={() => completeLogin("auth/staff/login", { email, password })}>{busy === "login" ? "Giris yapiliyor..." : "Giris yap"}</button>
          </div>
        )}

        {notice && <div role="status" className={`banner banner-${notice.kind}`}>{notice.text}</div>}
      </section>
    </main>
  );
}
