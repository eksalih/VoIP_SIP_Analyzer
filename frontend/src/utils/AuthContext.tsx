import { createContext, useContext } from "react";
import type { AuthUser } from "../types";
import { can } from "./auth";

interface AuthState {
  user: AuthUser;
  logout: () => void;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside the logged-in app");
  return { ...ctx, can: (permission: string) => can(ctx.user, permission) };
}
