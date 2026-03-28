import { type FormEvent, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Card, Input } from "../design-system/components";
import { useAuth } from "../contexts/AuthContext";
import { ApiError, getUserMessage } from "../api/client";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const returnTo = searchParams.get("returnTo") ?? "/today";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(email, password);
      navigate(returnTo, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(getUserMessage(err.errorCode));
      } else {
        setError("Unable to connect. Check that the server is running.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-neutral-50)] px-4">
      <div className="w-full max-w-[400px]">
        <Card className="shadow-[var(--shadow-lg)] !p-[var(--space-6)]">
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Header */}
            <div className="text-center space-y-1">
              <h1 className="text-[var(--text-h1-size)] leading-[var(--text-h1-height)] font-[var(--text-h1-weight)] text-[var(--color-primary)]">
                EkamCore
              </h1>
              <p className="text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-500)]">
                Sign in to your account
              </p>
            </div>

            {/* Error banner */}
            {error && (
              <div
                role="alert"
                className="px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-error-surface)] text-[var(--color-error)] text-[var(--text-small-size)] leading-[var(--text-small-height)]"
              >
                {error}
              </div>
            )}

            {/* Fields */}
            <Input
              label="Email"
              type="email"
              required
              placeholder="admin@ekamcore.dev"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />

            <Input
              label="Password"
              type="password"
              required
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />

            {/* Submit */}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={loading}
              className="w-full"
            >
              Sign in
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
