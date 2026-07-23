"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredSession, routeForRole } from "./lib/auth";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const session = getStoredSession();
    router.replace(session ? routeForRole(session.user.role) : "/login");
  }, [router]);

  return <main className="container"><div className="loading-container">Yönlendiriliyor...</div></main>;
}
