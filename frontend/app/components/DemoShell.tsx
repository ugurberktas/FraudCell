"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AuthSession } from "../lib/types";
import { api } from "../lib/api";
import { clearSession, routeForRole } from "../lib/auth";

export function DemoShell({ session, title, children }: { session: AuthSession; title: string; children: React.ReactNode }) {
  const router = useRouter();
  async function logout() {
    try {
      await api("auth/tokens/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: session.refresh_token }),
      });
    } finally {
      clearSession();
      router.replace("/login");
    }
  }

  return (
    <main className="container wide">
      <header className="header">
        <div>
          <h1 className="title">{title}</h1>
          <p className="service-id">{session.user.first_name} {session.user.last_name} · {session.user.role}</p>
        </div>
        <nav className="nav-actions">
          <Link href={routeForRole(session.user.role)}>Calisma alani</Link>
          {session.user.role !== "CUSTOMER" && <Link href="/leaderboard">Leaderboard</Link>}
          <button onClick={() => void logout()}>Cikis</button>
        </nav>
      </header>
      {children}
    </main>
  );
}
