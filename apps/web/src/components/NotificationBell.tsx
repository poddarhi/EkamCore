/**
 * Notification bell with dropdown panel (G-09).
 * Shows unread count badge and recent notifications.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, Check, CheckCheck, FileText, HardDrive, AlertTriangle, Zap } from "lucide-react";
import { useNotifications } from "../contexts/NotificationContext";
import { t } from "../i18n";

const ICON_MAP: Record<string, typeof Bell> = {
  INGESTION_COMPLETE: FileText,
  INGESTION_FAILED: AlertTriangle,
  BACKUP_COMPLETE: HardDrive,
  BACKUP_FAILED: AlertTriangle,
  SYSTEM_DEGRADED: Zap,
  SYSTEM_RECOVERED: Check,
};

function relativeTime(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return t("common.time.justNow");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return t("common.time.minutesAgo", { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("common.time.hoursAgo", { count: hours });
  const days = Math.floor(hours / 24);
  return t("common.time.daysAgo", { count: days });
}

export default function NotificationBell() {
  const { notifications, unreadCount, markRead, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleMarkAllRead = useCallback(async () => {
    await markAllRead();
  }, [markAllRead]);

  return (
    <div ref={ref} className="relative">
      {/* Bell button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded-[var(--radius-md)] text-[var(--color-neutral-500)] hover:bg-[var(--color-neutral-100)] transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
        aria-label={t("notifications.ariaLabel") + (unreadCount > 0 ? t("notifications.unread", { count: unreadCount }) : "")}
        aria-expanded={open}
      >
        <Bell size={20} aria-hidden="true" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-full bg-[var(--color-error)] text-white text-[10px] font-bold">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-[28rem] bg-[var(--color-white)] border border-[var(--color-neutral-200)] rounded-[var(--radius-lg)] shadow-[var(--shadow-xl)] overflow-hidden z-50">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-neutral-200)]">
            <h3 className="font-medium text-[var(--text-body-size)] text-[var(--color-neutral-900)]">
              {t("notifications.title")}
            </h3>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="inline-flex items-center gap-1 text-[var(--text-caption-size)] text-[var(--color-primary)] hover:underline cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)] rounded"
              >
                <CheckCheck size={14} aria-hidden="true" />
                {t("notifications.markAllRead")}
              </button>
            )}
          </div>

          {/* Notification list */}
          <div className="overflow-y-auto max-h-80">
            {notifications.length === 0 ? (
              <p className="px-4 py-8 text-center text-[var(--text-small-size)] text-[var(--color-neutral-400)]">
                {t("notifications.empty")}
              </p>
            ) : (
              notifications.map((n) => {
                const Icon = ICON_MAP[n.type] ?? Bell;
                const isError = n.type.includes("FAILED") || n.type === "SYSTEM_DEGRADED";

                return (
                  <div
                    key={n.id}
                    className={[
                      "flex gap-3 px-4 py-3 border-b border-[var(--color-neutral-100)] last:border-b-0",
                      "hover:bg-[var(--color-neutral-50)] transition-colors",
                      !n.is_read ? "bg-[var(--color-primary-surface)]" : "",
                    ].join(" ")}
                  >
                    <div
                      className={`shrink-0 p-1.5 rounded-[var(--radius-md)] ${
                        isError ? "bg-[var(--color-error-surface)]" : "bg-[var(--color-success-surface)]"
                      }`}
                    >
                      <Icon
                        size={16}
                        className={isError ? "text-[var(--color-error)]" : "text-[var(--color-success)]"}
                        aria-hidden="true"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[var(--text-small-size)] font-medium text-[var(--color-neutral-900)] truncate">
                        {n.title}
                      </p>
                      <p className="text-[var(--text-caption-size)] text-[var(--color-neutral-500)] truncate">
                        {n.message}
                      </p>
                      <p className="mt-0.5 text-[var(--text-caption-size)] text-[var(--color-neutral-400)]">
                        {relativeTime(n.created_at)}
                      </p>
                    </div>
                    {!n.is_read && (
                      <button
                        onClick={(e) => { e.stopPropagation(); markRead(n.id); }}
                        className="shrink-0 p-1 rounded text-[var(--color-neutral-400)] hover:text-[var(--color-primary)] cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary-light)]"
                        aria-label={t("notifications.markAsRead")}
                      >
                        <Check size={14} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
