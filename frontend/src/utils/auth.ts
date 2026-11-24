import type { AuthUser } from "../types";

const TOKEN_KEY = "sip-analyzer-token";

// localStorage can throw (private windows, blocked site data), so every access is guarded.
export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* token then lives only until reload */ }
}

/** Fired when the server rejects the token (expired, user disabled) so the app can show the login screen. */
export const AUTH_EXPIRED_EVENT = "sip-analyzer-auth-expired";

export function can(user: AuthUser | null, permission: string): boolean {
  if (!user) return false;
  return user.permissions.includes("*") || user.permissions.includes(permission);
}
