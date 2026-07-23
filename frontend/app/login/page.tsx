"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../lib/api";
import { routeForRole, storeSession } from "../lib/auth";
import type { AuthSession } from "../lib/types";

function errorText(error: unknown) {
  if (error instanceof Error) return error.message;
  return "Islem basarisiz";
}

export default function LoginPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"customer" | "staff">("customer");
  const [gsm, setGsm] = useState("05550000001");
  const [otp, setOtp] = useState("");
  const [email, setEmail] = useState("demo.analyst.card@fraudcell.com");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE !== "false";

  async function requestOtp() {
    try {
      await api("auth/customers/login/otp/request", { method: "POST", body: JSON.stringify({ gsm }) });
      setMessage("OTP istegi alindi.");
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  async function completeLogin(sessionPromise: Promise<AuthSession>) {
    try {
      const session = await sessionPromise;
      storeSession(session);
      router.replace(routeForRole(session.user.role));
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  return (
    <main className="container auth-container">
      <section className="panel auth-panel">
        <h1 className="title">FraudCell Demo Girisi</h1>
        <div className="tabs">
          <button className={tab === "customer" ? "tab active" : "tab"} onClick={() => setTab("customer")}>Musteri</button>
          <button className={tab === "staff" ? "tab active" : "tab"} onClick={() => setTab("staff")}>Personel</button>
        </div>

        {tab === "customer" ? (
          <div className="stack">
            <label>GSM<input value={gsm} onChange={(event) => setGsm(event.target.value)} placeholder="05551234567" /></label>
            <button onClick={requestOtp}>OTP iste</button>
            {demoMode && <p className="hint">Demo kodu: 1234</p>}
            <label>OTP<input value={otp} onChange={(event) => setOtp(event.target.value)} placeholder="1234" /></label>
            <button onClick={() => completeLogin(api("auth/customers/login", { method: "POST", body: JSON.stringify({ gsm, otp_code: otp }) }))}>Giris yap</button>
          </div>
        ) : (
          <div className="stack">
            <label>Email<input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="demo.analyst.card@fraudcell.com" /></label>
            <label>Parola<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <button onClick={() => completeLogin(api("auth/staff/login", { method: "POST", body: JSON.stringify({ email, password }) }))}>Giris yap</button>
          </div>
        )}

        {message && <div className="banner banner-warning">{message}</div>}
      </section>
    </main>
  );
}
