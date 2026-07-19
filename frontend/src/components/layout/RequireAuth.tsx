import { Navigate } from "react-router-dom";
import { dataSource } from "@/lib/data";
import { getSessionToken } from "@/lib/auth";

/**
 * Gates the investor branch. Mock mode bypasses by construction
 * (requiresAuth === false); live mode requires the bearer session from
 * POST /v1/login, a stale token surfaces as a 401 on first fetch, which
 * clears it and the next navigation lands back here.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const ds = dataSource();
  if (ds.requiresAuth && !getSessionToken()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
