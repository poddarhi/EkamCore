import { type FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Card, Input } from "../design-system/components";
import { useAuth } from "../contexts/AuthContext";
import { ApiError, getUserMessage } from "../api/client";
import { t } from "../i18n";

/** Default lockout countdown when the server doesn't provide one. */
const DEFAULT_LOCKOUT_SECS = 60;

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lockoutRemaining, setLockoutRemaining] = useState(0);
  const lockoutTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const returnTo = searchParams.get("returnTo") ?? "/today";

  // If already authenticated (e.g. navigated back to /login), redirect
  useEffect(() => {
    if (isAuthenticated) {
      navigate(returnTo, { replace: true });
    }
  }, [isAuthenticated, navigate, returnTo]);

  // Countdown timer for account lockout
  useEffect(() => {
    if (lockoutRemaining <= 0) {
      if (lockoutTimer.current) {
        clearInterval(lockoutTimer.current);
        lockoutTimer.current = null;
      }
      return;
    }
    lockoutTimer.current = setInterval(() => {
      setLockoutRemaining((prev) => {
        if (prev <= 1) {
          setError(null);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (lockoutTimer.current) clearInterval(lockoutTimer.current);
    };
  }, [lockoutRemaining]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLockoutRemaining(0);
    setLoading(true);

    try {
      await login(email, password);
      navigate(returnTo, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.errorCode === "AUTH_ACCOUNT_LOCKED") {
          setLockoutRemaining(DEFAULT_LOCKOUT_SECS);
          setError(getUserMessage(err.errorCode));
        } else {
          setError(getUserMessage(err.errorCode));
        }
      } else {
        setError(t("login.connectionError"));
      }
    } finally {
      setLoading(false);
    }
  }

  const isLocked = lockoutRemaining > 0;

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-neutral-50)] px-4">
      <div className="w-full max-w-[400px]">
        <Card className="shadow-[var(--shadow-lg)] !p-[var(--space-6)]">
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Header */}
            <div className="text-center space-y-1">
              <h1 className="text-[var(--text-h1-size)] leading-[var(--text-h1-height)] font-[var(--text-h1-weight)] text-[var(--color-primary)]">
                {t("login.title")}
              </h1>
              <p className="text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-500)]">
                {t("login.subtitle")}
              </p>
            </div>

            {/* Error banner */}
            {error && (
              <div
                role="alert"
                className="px-3 py-2 rounded-[var(--radius-md)] bg-[var(--color-error-surface)] text-[var(--color-error)] text-[var(--text-small-size)] leading-[var(--text-small-height)]"
              >
                {error}
                {isLocked && (
                  <span className="ml-1 font-medium">
                    {t("login.lockout", { seconds: lockoutRemaining })}
                  </span>
                )}
              </div>
            )}

            {/* Fields */}
            <Input
              label={t("login.email.label")}
              type="email"
              required
              placeholder={t("login.email.placeholder")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              disabled={loading || isLocked}
            />

            <Input
              label={t("login.password.label")}
              type="password"
              required
              placeholder={t("login.password.placeholder")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              disabled={loading || isLocked}
            />

            {/* Submit */}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={loading}
              disabled={isLocked}
              className="w-full"
            >
              {t("login.submit")}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
