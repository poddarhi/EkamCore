import { useCallback, useEffect, useState } from "react";
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
  Menu,
  X,
  Activity,
  ListChecks,
  HardDrive,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Avatar } from "../design-system/components";
import { useAuth } from "../contexts/AuthContext";

// ── Nav config ──

interface NavItemDef {
  to: string;
  icon: LucideIcon;
  label: string;
  disabled?: boolean;
  badgeCount?: number;
}

const NAV_ITEMS: (NavItemDef | "divider")[] = [
  { to: "/today", icon: Sun, label: "Today" },
  { to: "/recap", icon: History, label: "Recap" },
  { to: "/search", icon: Search, label: "Search" },
  "divider",
  { to: "/people", icon: Users, label: "People", disabled: true, badgeCount: 0 },
  { to: "/photos", icon: Image, label: "Photos", disabled: true },
  { to: "/files", icon: FileText, label: "Files", disabled: true },
  "divider",
  { to: "/settings", icon: Settings, label: "Settings" },
  { to: "/admin/system", icon: Activity, label: "System Status" },
  { to: "/admin/jobs", icon: ListChecks, label: "Jobs" },
  { to: "/admin/storage", icon: HardDrive, label: "Storage" },
];

const PAGE_TITLES: Record<string, string> = {
  "/today": "Today",
  "/recap": "Recap",
  "/search": "Search",
  "/people": "People",
  "/photos": "Photos",
  "/files": "Files",
  "/settings": "Settings",
  "/admin/system": "System Status",
  "/admin/jobs": "Jobs",
  "/admin/storage": "Storage",
};

// ── NavItem ──

function NavItem({
  to,
  icon: Icon,
  label,
  disabled,
  badgeCount,
  active,
  onClick,
}: NavItemDef & { active: boolean; onClick?: () => void }) {
  const navigate = useNavigate();

  if (disabled) {
    return (
      <div
        className="group relative flex items-center gap-3 px-3 py-2 rounded-[var(--radius-md)] text-[var(--color-neutral-400)] cursor-not-allowed select-none"
        title="Coming in a future update"
        aria-disabled="true"
      >
        <Icon size={20} aria-hidden="true" />
        <span className="text-[var(--text-body-size)] leading-[var(--text-body-height)]">
          {label}
        </span>
        {typeof badgeCount === "number" && (
          <span className="ml-auto inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-[var(--radius-full)] bg-[var(--color-neutral-100)] text-[var(--text-caption-size)] font-[var(--text-caption-weight)] text-[var(--color-neutral-400)]">
            {badgeCount}
          </span>
        )}
      </div>
    );
  }

  function handleClick() {
    navigate(to);
    onClick?.();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleClick();
    }
  }

  return (
    <button
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={[
        "flex items-center gap-3 w-full px-3 py-2 rounded-[var(--radius-md)]",
        "text-left transition-colors duration-[var(--duration-normal)] ease-[var(--easing-default)]",
        "cursor-pointer outline-none",
        "focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)] focus-visible:ring-offset-1",
        active
          ? "bg-[var(--color-primary-surface)] text-[var(--color-primary)] font-medium border-l-[3px] border-l-[var(--color-primary-light)]"
          : "text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)] hover:text-[var(--color-neutral-900)] border-l-[3px] border-l-transparent",
      ].join(" ")}
      aria-current={active ? "page" : undefined}
    >
      <Icon size={20} aria-hidden="true" />
      <span className="text-[var(--text-body-size)] leading-[var(--text-body-height)]">
        {label}
      </span>
      {typeof badgeCount === "number" && badgeCount > 0 && (
        <span className="ml-auto inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-[var(--radius-full)] bg-[var(--color-primary)] text-[var(--color-white)] text-[var(--text-caption-size)] font-[var(--text-caption-weight)]">
          {badgeCount}
        </span>
      )}
    </button>
  );
}

// ── Sidebar content (shared between desktop and mobile) ──

function SidebarContent({
  currentPath,
  user,
  onLogout,
  onNavClick,
}: {
  currentPath: string;
  user: { id: string } | null;
  onLogout: () => void;
  onNavClick?: () => void;
}) {
  return (
    <>
      {/* Logo */}
      <div className="h-14 flex items-center px-5 shrink-0">
        <span className="font-bold text-[var(--text-h2-size)] leading-[var(--text-h2-height)] text-[var(--color-primary)]">
          EkamCore
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-2 space-y-0.5 overflow-y-auto" aria-label="Main navigation">
        {NAV_ITEMS.map((item, i) =>
          item === "divider" ? (
            <div
              key={`div-${i}`}
              className="my-2 border-t border-[var(--color-neutral-200)]"
              role="separator"
            />
          ) : (
            <NavItem
              key={item.to}
              {...item}
              active={currentPath === item.to}
              onClick={onNavClick}
            />
          ),
        )}
      </nav>

      {/* Bottom: user info + logout */}
      <div className="px-3 py-3 border-t border-[var(--color-neutral-200)] shrink-0">
        <div className="flex items-center gap-3 px-3 py-2">
          <Avatar name={user?.id ? "User" : undefined} size="sm" />
          <span className="flex-1 min-w-0 truncate text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-700)]">
            {user?.id ? "Admin" : "Guest"}
          </span>
          <button
            onClick={onLogout}
            className="shrink-0 p-1.5 rounded-[var(--radius-md)] text-[var(--color-neutral-500)] hover:bg-[var(--color-neutral-100)] hover:text-[var(--color-error)] transition-colors duration-[var(--duration-normal)] cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-error)]"
            aria-label="Sign out"
          >
            <LogOut size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
    </>
  );
}

// ── Main layout ──

export default function MainLayout() {
  const location = useLocation();
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const pageTitle =
    PAGE_TITLES[location.pathname] ??
    location.pathname.slice(1).charAt(0).toUpperCase() +
      location.pathname.slice(2);

  // Close sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Close sidebar on Escape
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") setSidebarOpen(false);
  }, []);

  useEffect(() => {
    if (sidebarOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [sidebarOpen, handleKeyDown]);

  return (
    <div className="flex h-screen bg-[var(--color-neutral-50)]">
      {/* ── Desktop sidebar (>= 1024px) ── */}
      <aside className="hidden lg:flex w-60 shrink-0 bg-[var(--color-white)] border-r border-[var(--color-neutral-200)] flex-col">
        <SidebarContent
          currentPath={location.pathname}
          user={user}
          onLogout={logout}
        />
      </aside>

      {/* ── Mobile sidebar overlay (< 1024px) ── */}
      {sidebarOpen && (
        <>
          {/* Backdrop */}
          <div
            className="lg:hidden fixed inset-0 z-40 bg-black/30 transition-opacity duration-[var(--duration-normal)]"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          {/* Drawer */}
          <aside className="lg:hidden fixed inset-y-0 left-0 z-50 w-60 bg-[var(--color-white)] border-r border-[var(--color-neutral-200)] flex flex-col shadow-[var(--shadow-xl)]">
            <SidebarContent
              currentPath={location.pathname}
              user={user}
              onLogout={logout}
              onNavClick={() => setSidebarOpen(false)}
            />
          </aside>
        </>
      )}

      {/* ── Main content ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 shrink-0 bg-[var(--color-white)] border-b border-[var(--color-neutral-200)] flex items-center justify-between px-4 lg:px-8 gap-4">
          {/* Left: hamburger (mobile) + title */}
          <div className="flex items-center gap-3">
            <button
              className="lg:hidden p-1.5 rounded-[var(--radius-md)] text-[var(--color-neutral-600)] hover:bg-[var(--color-neutral-100)] transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
              onClick={() => setSidebarOpen((v) => !v)}
              aria-label={sidebarOpen ? "Close menu" : "Open menu"}
              aria-expanded={sidebarOpen}
            >
              {sidebarOpen ? (
                <X size={22} aria-hidden="true" />
              ) : (
                <Menu size={22} aria-hidden="true" />
              )}
            </button>
            <h1 className="font-[var(--text-h2-weight)] text-[var(--text-h2-size)] leading-[var(--text-h2-height)] text-[var(--color-neutral-900)]">
              {pageTitle}
            </h1>
          </div>

          {/* Right: search + avatar */}
          <div className="flex items-center gap-4">
            <div className="hidden sm:block relative">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-neutral-400)] pointer-events-none"
                aria-hidden="true"
              />
              <input
                type="text"
                placeholder="Search..."
                disabled
                className="w-[280px] h-9 pl-9 pr-3 rounded-[var(--radius-md)] border border-[var(--color-neutral-200)] bg-[var(--color-neutral-50)] text-[var(--text-small-size)] leading-[var(--text-small-height)] text-[var(--color-neutral-900)] placeholder:text-[var(--color-neutral-400)] outline-none opacity-50 cursor-not-allowed"
                aria-label="Search (coming soon)"
              />
            </div>
            <Avatar name={user?.id ? "User" : undefined} size="sm" />
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
