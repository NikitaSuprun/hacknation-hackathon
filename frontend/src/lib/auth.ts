/**
 * Live-mode auth against the in-repo app: POST /v1/login {password} → bearer
 * token, held in localStorage and attached by LiveDataSource. Sessions are
 * in-memory server-side (single-process demo scope), a 401 means re-login.
 */

const SESSION_KEY = "chosen.session";

/**
 * The API origin, read lazily so tests can stub VITE_API_BASE after module
 * load (vi.stubEnv). Empty string = same-origin (production / dev proxy).
 */
export function apiBase(): string {
  return ((import.meta.env.VITE_API_BASE as string | undefined) ?? "").replace(/\/$/, "");
}

/** Snapshot at module load, kept for import stability; prefer apiBase(). */
export const API_BASE = apiBase();

export function getSessionToken(): string | null {
  return localStorage.getItem(SESSION_KEY);
}

export function setSessionToken(token: string): void {
  localStorage.setItem(SESSION_KEY, token);
}

export function clearSessionToken(): void {
  localStorage.removeItem(SESSION_KEY);
}

export async function login(password: string): Promise<void> {
  const response = await fetch(`${apiBase()}/v1/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null;
    throw new Error(body?.error ?? "Sign-in failed.");
  }
  const { token } = (await response.json()) as { token: string };
  setSessionToken(token);
}

export function logout(): void {
  clearSessionToken();
}
