"use client";

import { useEffect, useState } from "react";
import { DemoShell } from "../components/DemoShell";
import { RequireSession } from "../components/RequireSession";
import { api, authHeader } from "../lib/api";
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
  const [message, setMessage] = useState("");

  useEffect(() => {
    api<{ items: LeaderboardRow[] }>(`game/leaderboard?period=${period}&limit=10`, { headers: authHeader(session.access_token) })
      .then((data) => setItems(data.items))
      .catch((error) => setMessage(error.message));
  }, [period, session.access_token]);

  return (
    <DemoShell session={session} title="Leaderboard">
      <section className="panel">
        <div className="tabs">
          <button className={period === "daily" ? "tab active" : "tab"} onClick={() => setPeriod("daily")}>Gunluk</button>
          <button className={period === "weekly" ? "tab active" : "tab"} onClick={() => setPeriod("weekly")}>Haftalik</button>
        </div>
        {items.map((row) => (
          <article className="transaction" key={row.analyst_id}>
            <div><strong>#{row.rank} {row.analyst_id}</strong><p>{row.period_points} donem puani · {row.total_points} toplam · {row.level}</p></div>
            <small>{row.resolved_cases} vaka · {row.badges.join(", ") || "Rozet yok"}</small>
          </article>
        ))}
      </section>
      {message && <div className="banner banner-warning">{message}</div>}
    </DemoShell>
  );
}
