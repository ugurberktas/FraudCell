"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DemoShell } from "../components/DemoShell";
import { RequireSession } from "../components/RequireSession";
import { api, authHeader } from "../lib/api";
import { apiErrorText, newlyEarnedBadges, remainingSlaSeconds } from "../lib/ui-utils.mjs";
import type { AuthSession, GamificationProfile, RiskCase } from "../lib/types";

export default function AnalystPage() {
  return <RequireSession allowed={["ANALYST"]}>{(session) => <AnalystWorkspace session={session} />}</RequireSession>;
}

function AnalystWorkspace({ session }: { session: AuthSession }) {
  const [cases, setCases] = useState<RiskCase[]>([]);
  const [profile, setProfile] = useState<GamificationProfile | null>(null);
  const [caseError, setCaseError] = useState("");
  const [profileError, setProfileError] = useState("");
  const [notice, setNotice] = useState("");
  const [badgeToast, setBadgeToast] = useState("");
  const [loading, setLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [nowMs, setNowMs] = useState(() => Date.now());
  const knownBadges = useRef<string[] | null>(null);
  const knownPoints = useRef<number | null>(null);

  const loadCases = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    try {
      const data = await api<{ items: RiskCase[] }>("transactions/cases/assigned-to-me", { headers: authHeader(session.access_token) });
      setCases(data.items);
      setCaseError("");
    } catch (error) {
      setCaseError(apiErrorText(error, "Atanmış vakalar yüklenemedi"));
    } finally {
      if (showLoader) setLoading(false);
    }
  }, [session.access_token]);

  const loadProfile = useCallback(async (showLoader = false) => {
    if (showLoader) setProfileLoading(true);
    try {
      const data = await api<GamificationProfile>("game/profiles/me", { headers: authHeader(session.access_token) });
      if (knownBadges.current !== null) {
        const earned = newlyEarnedBadges(knownBadges.current, data.badges);
        if (earned.length) setBadgeToast(`Yeni rozet kazanıldı: ${earned.join(", ")}`);
      }
      if (knownPoints.current !== null && data.total_points !== knownPoints.current) {
        const difference = data.total_points - knownPoints.current;
        setNotice(`Puan güncellendi: ${difference > 0 ? "+" : ""}${difference} (toplam ${data.total_points}).`);
      }
      knownBadges.current = data.badges;
      knownPoints.current = data.total_points;
      setProfile(data);
      setProfileError("");
    } catch (error) {
      setProfileError(apiErrorText(error, "Analist profili yüklenemedi"));
    } finally {
      if (showLoader) setProfileLoading(false);
    }
  }, [session.access_token]);

  useEffect(() => {
    void loadCases(true);
    void loadProfile(true);
    const caseTimer = window.setInterval(() => void loadCases(), 5000);
    const profileTimer = window.setInterval(() => void loadProfile(), 2500);
    const slaTimer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => {
      window.clearInterval(caseTimer);
      window.clearInterval(profileTimer);
      window.clearInterval(slaTimer);
    };
  }, [loadCases, loadProfile]);

  async function action(caseId: string, path: string, body?: object, successText = "Vaka güncellendi.") {
    const actionKey = `${caseId}:${path}`;
    setPending(actionKey);
    setCaseError("");
    setNotice("");
    try {
      await api(`transactions/cases/${caseId}/${path}`, {
        method: "POST",
        headers: authHeader(session.access_token),
        body: body ? JSON.stringify(body) : "{}",
      });
      setNotice(successText);
      await loadCases();
      if (path === "decision") void loadProfile();
    } catch (error) {
      setCaseError(apiErrorText(error, "Vaka işlemi tamamlanamadı"));
    } finally {
      setPending(null);
    }
  }

  function decide(item: RiskCase, decision: "ONAYLANDI" | "BLOKLANDI") {
    const note = (notes[item.id] || "").trim();
    if (decision === "BLOKLANDI" && !note) {
      setCaseError("BLOKLANDI kararı için karar notu zorunludur (422).");
      return;
    }
    void action(
      item.id,
      "decision",
      { decision, ...(note ? { note } : {}) },
      decision === "BLOKLANDI" ? "Vaka bloklandı; puan olayı işleme alındı." : "Vaka onaylandı; puan olayı işleme alındı.",
    );
  }

  function slaText(item: RiskCase) {
    if (item.sla_exceeded) return "SLA aşıldı";
    if (["ONAYLANDI", "BLOKLANDI", "KAPANDI"].includes(item.status) && item.sla_remaining_seconds === null) return "Tamamlandı";
    const remaining = remainingSlaSeconds(item.sla_due_at, nowMs);
    if (remaining === null) return "-";
    if (remaining === 0) return "Süre doldu";
    const hours = Math.floor(remaining / 3600);
    const minutes = Math.floor((remaining % 3600) / 60);
    const seconds = remaining % 60;
    return `${hours ? `${hours} sa ` : ""}${minutes} dk ${seconds.toString().padStart(2, "0")} sn`;
  }

  return (
    <DemoShell session={session} title="Analist Vakalari">
      {badgeToast && <div className="toast">{badgeToast}<button onClick={() => setBadgeToast("")} aria-label="Kapat">x</button></div>}
      {caseError && <div role="alert" className="banner banner-error">{caseError}</div>}
      {notice && <div role="status" className="banner banner-success">{notice}</div>}

      <section className="panel profile-summary">
        <div className="section-title"><h2>Profil özeti</h2><small>Puanlar otomatik yenilenir</small></div>
        {profileLoading ? (
          <div className="loading-container compact"><span className="spinner" />Profil yükleniyor...</div>
        ) : profile ? (
          <>
            <div className="metric-grid">
              <div className="metric-card"><small>Toplam puan</small><strong>{profile.total_points}</strong></div>
              <div className="metric-card"><small>Seviye</small><strong>{profile.level}</strong></div>
              <div className="metric-card"><small>Çözülen vaka</small><strong>{profile.resolved_cases}</strong></div>
              <div className="metric-card"><small>Günlük sıra</small><strong>{profile.daily_rank ?? "-"}</strong></div>
            </div>
            <p><strong>Rozetler:</strong> {profile.badges.join(", ") || "Henüz rozet yok"}</p>
            {profile.recent_score_entries.length > 0 && (
              <div className="score-ledger"><strong>Son puan hareketleri</strong>{profile.recent_score_entries.slice(0, 5).map((entry, index) => (
                <span key={`${entry.occurred_at}:${entry.reason}:${index}`}>{entry.points > 0 ? "+" : ""}{entry.points} · {entry.reason}</span>
              ))}</div>
            )}
          </>
        ) : null}
        {profileError && <div role="alert" className="banner banner-error">{profileError}</div>}
      </section>

      <section className="panel">
        <div className="section-title"><h2>Bana atanan vakalar</h2><button className="refresh-btn" disabled={pending !== null} onClick={() => void loadCases(true)}>Yenile</button></div>
        {loading ? (
          <div className="loading-container"><span className="spinner" />Vakalar yükleniyor...</div>
        ) : caseError && cases.length === 0 ? (
          <p className="empty-state">Vaka verisi şu anda gösterilemiyor.</p>
        ) : cases.length === 0 ? (
          <p className="empty-state">Atanmış vaka bulunmuyor.</p>
        ) : cases.map((item) => {
          const reasons = item.risk_reasons || item.transaction?.risk_reasons || [];
          return (
            <article className="case-item" key={item.id}>
              <div className="section-title">
                <div>
                  <strong>{item.transaction?.transaction_number || item.id}</strong>
                  <p>{item.transaction?.amount} TL · {item.transaction?.city} · Öncelik: {item.transaction?.risk_level || "-"} · {item.status}</p>
                </div>
                <span className={item.sla_exceeded ? "badge badge-unavailable" : "badge badge-healthy"}>SLA: {slaText(item)}</span>
              </div>
              <div className="details-grid">
                <span><small>Risk skoru</small><strong>{item.transaction?.risk_score ?? "-"}</strong></span>
                <span><small>Fraud türü</small><strong>{item.transaction?.fraud_type || "-"}</strong></span>
                <span><small>AI durumu</small><strong>{item.transaction?.ai_status || "-"}</strong></span>
                <span><small>Model</small><strong>{item.transaction?.model_version || "-"}</strong></span>
                <span><small>Müşteri yanıtı</small><strong>{item.customer_response || "YANIT_YOK"}</strong></span>
                <span><small>Atanan analyst</small><strong>{item.assigned_analyst_id || "-"}</strong></span>
              </div>
              <div>
                <h3>Risk nedenleri</h3>
                {reasons.length ? <ul className="risk-reasons">{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <p className="empty-state compact">Servis yanıtında risk nedeni bulunmuyor.</p>}
              </div>
              {item.history && item.history.length > 0 && (
                <div className="timeline"><h3>Vaka geçmişi</h3><ol>{item.history.map((entry) => (
                  <li key={entry.id}><strong>{entry.from_status || "BAŞLANGIÇ"} → {entry.to_status}</strong><span>{new Date(entry.created_at).toLocaleString("tr-TR")}</span></li>
                ))}</ol></div>
              )}
              {item.decision_note && <p><strong>Karar notu:</strong> {item.decision_note}</p>}
              {item.status === "INCELENIYOR" && (
                <label>Karar notu<textarea disabled={pending !== null} value={notes[item.id] || ""} onChange={(event) => setNotes({ ...notes, [item.id]: event.target.value })} placeholder="Karar gerekçesini yazın" maxLength={4000} /></label>
              )}
              <div className="button-row">
                {item.status === "ATANDI" && <button disabled={pending !== null} onClick={() => void action(item.id, "start", undefined, "Vaka incelemeye alındı.")}>{pending === `${item.id}:start` ? "Başlatılıyor..." : "Başlat"}</button>}
                {item.status === "INCELENIYOR" && <button disabled={pending !== null} onClick={() => void action(item.id, "request-verification", undefined, "Müşteri doğrulaması istendi.")}>Müşteri doğrula</button>}
                {item.status === "INCELENIYOR" && <button disabled={pending !== null} onClick={() => decide(item, "ONAYLANDI")}>Onayla</button>}
                {item.status === "INCELENIYOR" && <button disabled={pending !== null} className="danger" onClick={() => decide(item, "BLOKLANDI")}>Blokla</button>}
              </div>
            </article>
          );
        })}
      </section>
    </DemoShell>
  );
}
