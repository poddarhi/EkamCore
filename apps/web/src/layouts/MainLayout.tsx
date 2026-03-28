import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Sun,
  History,
  Search,
  Users,
  Image,
  FileText,
  Settings,
  LogOut,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Avatar } from "../design-system/components";
import { useAuth } from "../contexts/AuthContext";

interface NavItemDef {
  to: string;
  icon: LucideIcon;
  label: string;
  disabled?: boolean;
}

const NAV_ITEMS: (NavItemDef | "divider")[] = [
  { to: "/today", icon: Sun, label: "Today" },
  { to: "/recap", icon: History, label: "Recap" },
  { to: "/search", icon: Search, label: "Search" },
  "divider",
  { to: "/people", icon: Users, label: "People", disabled: true },
  { to: "/photos", icon: Image, label: "Photos", disabled: true },
  { to: "/files", icon: FileText, label: "Files", disabled: true },
  "divider",
  { to: "/settings", icon: Settings, label: "Settings" },
];

const PAGE_TITLES: Record<string, string> = {
  "/today": "Today",
  "/recap": "Recap",
  "/search": "Search",
  "/people": "People",
  "/photos": "Photos",
  "/files": "Files",
  "/settings": "Settings",
};

function NavItem({
  to,
  icon: Icon,
  label,
  disabled,
  active,
}: NavItemDef & { active: boolean }) {
  const navigate = useNavigate();

  if (disabled) {
    return (
      <div
        className="group relative flex items-center gap-3 px-3 py-2 rounded-[var(--radius-md)] opacity-40 cursor-not-allowed select-none"
        title="Coming in a future update"
      >
        <Icon size={20} />
        <span className="text-[var(--text-body-size)] leading-[var(--text-body-height)]">
          {label}
        </span>
      </div>
    );
  }

  return (
    <button
      onClick={() => navigate(to)}
      className={[
        "flex items-center gap-3 w-full px-3 py-2 rounded-[var(--radius-md)]",
        "text-left transition-colors duration-[var(--duration-normal)] ease-[var(--easing-default)]",
        "cursor-pointer",
        active
          ? "bg-[var(--color-primary-surface)] text-[var(--color-primary)] font-medium"
          : "text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)] hover:text-[var(--color-neutral-900)]",
      ].join(" ")}
    >
      <Icon size={20} />
      <span className="text-[var(--text-body-size)] leading-[var(--text-body-height)]">
        {label}
      </span>
    </button>
  );
}

export default function MainLayout() {
  const location = useLocation();
  const { user, logout } = useAuth();

  const pageTitle =
    PAGE_TITLES[location.pathname] ??
    location.pathname.slice(1).charAt(0).toUpperCase() +
      location.pathname.slice(2);

  return (
    <div className="flex h-screen bg-[var(--color-neutral-50)]">
      {/* ── Sidebar ── */}
      <aside className="w-60 shrink-0 bg-[var(--color-white)] border-r border-[var(--color-neutral-200)] flex flex-col">
        {/* Logo */}
        <div className="h-14 flex items-center px-5">
          <span
            className="font-bold text-[var(--text-h2-size)] leading-[var(--text-h2-height)] text-[var(--color-primary)]"
          >
            EkamCore
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-2 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map((item, i) =>
            item === "divider" ? (
              <div
                key={`div-${i}`}
                className="my-2 border-t border-[var(--color-neutral-200)]"
              />
            ) : (
              <NavItem
                key={item.to}
                {...item}
                active={location.pathname === item.to}
              />
            ),
          )}
        </nav>

        {/* Bottom: logout */}
        <div className="px-3 py-3 border-t border-[var(--color-neutral-200)]">
          <button
            onClick={logout}
            className="flex items-center gap-3 w-full px-3 py-2 rounded-[var(--radius-md)] text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)] hover:text-[var(--color-error)] transition-colors duration-[var(--duration-normal)] cursor-pointer"
          >
            <LogOut size={20} />
            <span className="text-[var(--text-body-size)]">Sign out</span>
          </button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 shrink-0 bg-[var(--color-white)] border-b border-[var(--color-neutral-200)] flex items-center justify-between px-8">
          <h1
            className="font-[var(--text-h1-weight)] text-[var(--text-h1-size)] leading-[var(--text-h1-height)] text-[var(--color-neutral-900)]"
          >
            {pageTitle}
          </h1>
          <Avatar name={user?.id ? "User" : undefined} size="sm" />
        </header>

        {/* Content */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-[960px] mx-auto px-8 py-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
