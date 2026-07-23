import type { AuthSession } from "./types";
export { routeForRole } from "./auth-routing.mjs";

const STORAGE_KEY = "fraudcell.demo.session";
const ROLES = new Set(["CUSTOMER", "ANALYST", "SUPERVISOR", "ADMIN"]);

export function storeSession(session: AuthSession) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function getStoredSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as AuthSession;
    if (
      !session.access_token
      || !session.refresh_token
      || !session.user?.role
      || !ROLES.has(session.user.role)
    ) return null;
    return session;
  } catch {
    return null;
  }
}

export function clearSession() {
  window.localStorage.removeItem(STORAGE_KEY);
}
