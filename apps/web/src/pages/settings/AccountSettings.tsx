/**
 * Account Settings (G-03) — email display, password change placeholder.
 */

import { User, Lock } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { Button, Card } from "../../design-system/components";

export default function AccountSettings() {
  const { user } = useAuth();

  return (
    <div className="space-y-[var(--space-6)]">
      <h2 className="font-[var(--text-h2-weight)] text-[var(--text-h2-size)] text-[var(--color-neutral-900)]">
        Account
      </h2>

      <Card>
        <div className="flex items-center gap-[var(--space-4)]">
          <div className="p-[var(--space-3)] rounded-full bg-[var(--color-primary-surface)]">
            <User size={20} className="text-[var(--color-primary)]" aria-hidden="true" />
          </div>
          <div>
            <p className="text-[var(--text-body-size)] font-medium text-[var(--color-neutral-900)]">
              {user?.id ? "Admin" : "User"}
            </p>
            <p className="text-[var(--text-small-size)] text-[var(--color-neutral-500)]">
              Local account
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-[var(--space-3)]">
            <Lock size={18} className="text-[var(--color-neutral-500)]" aria-hidden="true" />
            <div>
              <p className="text-[var(--text-body-size)] font-medium text-[var(--color-neutral-900)]">Password</p>
              <p className="text-[var(--text-caption-size)] text-[var(--color-neutral-400)]">Last changed: unknown</p>
            </div>
          </div>
          <Button variant="secondary" size="sm" disabled>
            Change Password
          </Button>
        </div>
      </Card>
    </div>
  );
}
