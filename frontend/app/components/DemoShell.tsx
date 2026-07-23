"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AuthSession } from "../lib/types";
import { clearSession } from "../lib/auth";

export function DemoShell({ session, title, children }: { session: AuthSession; title: string; children: React.ReactNode }) {
  const router = useRouter();
  return (
    <main className="container wide">
      <header className="header">
        <div>
          <h1 className="title">{title}</h1>
          <p className="service-id">{session.user.first_name} {session.user.last_name} · {session.user.role}</p>
        </div>
        <nav className="nav-actions">
          {session.user.role !== "CUSTOMER" && <Link href="/leaderboard">Leaderboard</Link>}
          <button onClick={() => { clearSession(); router.replace("/login"); }}>Cikis</button>
        </nav>
      </header>
      {children}
    </main>
  );
}
