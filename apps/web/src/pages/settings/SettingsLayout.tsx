/**
 * Settings layout with sidebar navigation (G-03).
 * Sub-pages render in the <Outlet />.
 */

import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Settings, FolderOpen, Brain, User, Info } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface SettingsNavItem {
  to: string;
  icon: LucideIcon;
  label: string;
}

const NAV_ITEMS: SettingsNavItem[] = [
  { to: "/settings/general", icon: Settings, label: "General" },
  { to: "/settings/sources", icon: FolderOpen, label: "Sources" },
  { to: "/settings/photo-intelligence", icon: Brain, label: "Photo Intelligence" },
  { to: "/settings/account", icon: User, label: "Account" },
  { to: "/settings/about", icon: Info, label: "About" },
];

export default function SettingsLayout() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <div className="flex gap-[var(--space-6)] min-h-[400px]">
      {/* Sidebar nav */}
      <nav className="hidden sm:block w-48 shrink-0" aria-label="Settings navigation">
        <ul className="space-y-[var(--space-1)]">
          {NAV_ITEMS.map((item) => {
            const active = location.pathname === item.to;
            return (
              <li key={item.to}>
                <button
                  onClick={() => navigate(item.to)}
                  className={[
                    "flex items-center gap-[var(--space-2)] w-full px-[var(--space-3)] py-[var(--space-2)] rounded-[var(--radius-md)]",
                    "text-[var(--text-small-size)] text-left transition-colors cursor-pointer outline-none",
                    "focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]",
                    active
                      ? "bg-[var(--color-primary-surface)] text-[var(--color-primary)] font-medium"
                      : "text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)]",
                  ].join(" ")}
                  aria-current={active ? "page" : undefined}
                >
                  <item.icon size={16} aria-hidden="true" />
                  {item.label}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <Outlet />
      </div>
    </div>
  );
}
