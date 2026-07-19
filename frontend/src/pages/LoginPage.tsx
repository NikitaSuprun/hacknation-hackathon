import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/brand/Wordmark";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { dataSource } from "@/lib/data";
import { login } from "@/lib/auth";
import { FUND_EMAIL } from "@/mocks/state";

export default function LoginPage() {
  const navigate = useNavigate();
  const ds = dataSource();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (ds.requiresAuth) {
      setBusy(true);
      try {
        await login(password);
      } catch (err) {
        setError((err as Error).message);
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    navigate("/thesis");
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-paper px-gutter">
      <div className="w-full max-w-sm">
        <Wordmark />
        <h1 className="mt-8 font-display text-h1 text-ink">Sign in</h1>
        <p className="mt-2 text-small text-quiet">
          The fund's working instrument. Founders don't sign in, they get chosen.
        </p>
        <form onSubmit={handleSubmit} className="mt-8 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" defaultValue={FUND_EMAIL} readOnly className="text-quiet" />
          </div>
          {ds.requiresAuth && (
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoFocus
              />
            </div>
          )}
          {error && <p className="text-small text-danger">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy} data-demo-id="login-submit">
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        {!ds.requiresAuth && (
          <p className="mono-label mt-6">Demo data, no account needed</p>
        )}
      </div>
    </div>
  );
}
