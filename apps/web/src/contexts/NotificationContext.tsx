/**
 * Notification context (G-09) — polls for unread notifications every 60s.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { apiFetch } from "../api/client";
import { useAuth } from "./AuthContext";

interface NotificationItem {
  id: string;
  type: string;
  title: string;
  message: string;
  metadata: Record<string, unknown> | null;
  is_read: boolean;
  created_at: string;
}

interface NotificationContextValue {
  notifications: NotificationItem[];
  unreadCount: number;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  refresh: () => Promise<void>;
  /** Most recent notification ID — changes when new ones arrive */
  latestId: string | null;
}

const NotificationContext = createContext<NotificationContextValue>({
  notifications: [],
  unreadCount: 0,
  markRead: async () => {},
  markAllRead: async () => {},
  refresh: async () => {},
  latestId: null,
});

export function useNotifications() {
  return useContext(NotificationContext);
}

interface ListResponse {
  notifications: NotificationItem[];
  unread_count: number;
  total: number;
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [latestId, setLatestId] = useState<string | null>(null);
  const prevLatestRef = useRef<string | null>(null);

  const fetchNotifications = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const data = await apiFetch<ListResponse>(
        "/api/v1/notifications?unread_only=false&limit=20",
      );
      setNotifications(data.notifications);
      setUnreadCount(data.unread_count);

      // Detect new notifications
      const newLatest = data.notifications[0]?.id ?? null;
      if (newLatest && newLatest !== prevLatestRef.current) {
        setLatestId(newLatest);
      }
      prevLatestRef.current = newLatest;
    } catch {
      // Silently fail — notifications are non-critical
    }
  }, [isAuthenticated]);

  // Poll every 60 seconds
  useEffect(() => {
    if (!isAuthenticated) return;
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 60_000);
    return () => clearInterval(interval);
  }, [isAuthenticated, fetchNotifications]);

  const markRead = useCallback(
    async (id: string) => {
      await apiFetch(`/api/v1/notifications/${id}/read`, { method: "PATCH" });
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    },
    [],
  );

  const markAllRead = useCallback(async () => {
    await apiFetch("/api/v1/notifications/mark-all-read", { method: "POST" });
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
  }, []);

  return (
    <NotificationContext.Provider
      value={{ notifications, unreadCount, markRead, markAllRead, refresh: fetchNotifications, latestId }}
    >
      {children}
    </NotificationContext.Provider>
  );
}
