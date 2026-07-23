"use client";

import { useCallback, useEffect, useState } from "react";
import { DemoShell } from "../components/DemoShell";
import { RequireSession } from "../components/RequireSession";
import { api, authHeader } from "../lib/api";
import { apiErrorText } from "../lib/ui-utils.mjs";
import type { AuthSession } from "../lib/types";

interface LeaderboardRow {
  rank: number;
  analyst_id: string;
  period_points: number;
  total_points: number;
  level: string;
  resolved_cases: number;
  badges: string[];
}

export default function LeaderboardPage() {
  return <RequireSession allowed={["ANALYST", "SUPERVISOR", "ADMIN"]}>{(session) => <Leaderboard session={session} />}</RequireSession>;
}

function Leaderboard({ session }: { session: AuthSession }) {
  const [period, setPeriod] = useState<"daily" | "weekly">("daily");
  const [items, setItems] = useState<LeaderboardRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const loadLeaderboard = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<{ items: LeaderboardRow[] }>(`game/leaderboard?period=${period}&limit=10`, { headers: authHeader(session.access_token) });
      setItems(data.items);
      setError("");
    } catch (requestError) {
      setError(apiErrorText(requestError, "Leaderboard yüklenemedi"));
    } finally {
      setLoading(false);
    }
  }, [period, session.access_token]);

  useEffect(() => {
    void loadLeaderboard();
  }, [loadLeaderboard]);

  return (
    <DemoShell session={session} title="Leaderboard">
      <section className="panel">
        <div className="section-title">
          <div className="tabs">
            <button disabled={loading} className={period === "daily" ? "tab active" : "tab"} onClick={() => setPeriod("daily")}>Gunluk</button>
            <button disabled={loading} className={period === "weekly" ? "tab active" : "tab"} onClick={() => setPeriod("weekly")}>Haftalik</button>
          </div>
          <button className="refresh-btn" disabled={loading} onClick={() => void loadLeaderboard()}>Yenile</button>
        </div>
        {loading ? (
          <div className="loading-container"><span className="spinner" />Leaderboard yükleniyor...</div>
        ) : error && items.length === 0 ? (
          <p className="empty-state">Leaderboard verisi şu anda gösterilemiyor.</p>
        ) : items.length === 0 ? (
          <p className="empty-state">Bu dönem için leaderboard verisi yok.</p>
        ) : items.map((row) => (
          <article className="transaction" key={row.analyst_id}>
            <div><strong>#{row.rank} {row.analyst_id}</strong><p>{row.period_points} donem puani · {row.total_points} toplam · {row.level}</p></div>
            <small>{row.resolved_cases} vaka · {row.badges.join(", ") || "Rozet yok"}</small>
          </article>
        ))}
      </section>
      {error && <div role="alert" className="banner banner-error">{error}</div>}
    </DemoShell>
  );
}
