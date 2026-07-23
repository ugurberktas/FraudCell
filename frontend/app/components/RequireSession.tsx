"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getStoredSession, routeForRole } from "../lib/auth";
import type { AuthSession, Role } from "../lib/types";

export function RequireSession({ allowed, children }: { allowed: Role[]; children: (session: AuthSession) => React.ReactNode }) {
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null>(null);
  const allowedKey = allowed.join(",");

  useEffect(() => {
    const current = getStoredSession();
    if (!current) {
      router.replace("/login");
      return;
    }
    if (!allowedKey.split(",").includes(current.user.role)) {
      router.replace(routeForRole(current.user.role));
      return;
    }
    setSession(current);
  }, [allowedKey, router]);

  if (!session) return <main className="container"><div className="loading-container">Yukleniyor...</div></main>;
  return <>{children(session)}</>;
}
