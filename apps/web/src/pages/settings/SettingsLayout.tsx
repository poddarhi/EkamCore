/**
 * Settings layout with sidebar navigation (G-03).
 * Sub-pages render in the <Outlet />.
 */

import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Bot, Settings, FolderOpen, Brain, User, Info } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { t } from "../../i18n";

interface SettingsNavItem {
  to: string;
  icon: LucideIcon;
  labelKey: string;
}

const NAV_ITEMS: SettingsNavItem[] = [
  { to: "/settings/general", icon: Settings, labelKey: "settings.nav.general" },
  { to: "/settings/sources", icon: FolderOpen, labelKey: "settings.nav.sources" },
  { to: "/settings/photo-intelligence", icon: Brain, labelKey: "settings.nav.photoIntelligence" },
  { to: "/settings/pack", icon: Bot, labelKey: "settings.pack.title" },
  { to: "/settings/account", icon: User, labelKey: "settings.nav.account" },
  { to: "/settings/about", icon: Info, labelKey: "settings.nav.about" },
];

export default function SettingsLayout() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <div className="flex gap-[var(--space-6)] min-h-[400px]">
      {/* Sidebar nav */}
      <nav className="hidden sm:block w-48 shrink-0" aria-label={t("settings.nav.ariaLabel")}>
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
                  {t(item.labelKey)}
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
