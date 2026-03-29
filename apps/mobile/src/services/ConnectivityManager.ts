/**
 * ConnectivityManager — polls /health every 10s and emits one of 6 states.
 *
 * States:
 *   CONNECTED           — API healthy, latency normal
 *   DEGRADED            — API responds but latency 2–10s
 *   RECONNECTING        — API unreachable for < 5 min, retrying
 *   DISCONNECTED_CACHED — API unreachable for >= 5 min, cached data available
 *   DISCONNECTED_EMPTY  — API unreachable for >= 5 min, no cache
 *   HUB_SLEEPING        — Tailscale reachable but API port closed (connection refused)
 */

import {HEALTH_URL} from '../api/client';

export type ConnectivityState =
  | 'CONNECTED'
  | 'DEGRADED'
  | 'RECONNECTING'
  | 'DISCONNECTED_CACHED'
  | 'DISCONNECTED_EMPTY'
  | 'HUB_SLEEPING';

export type ConnectivityListener = (state: ConnectivityState) => void;

const POLL_INTERVAL_MS = 10_000;
const DEGRADED_LATENCY_LOW_MS = 2_000;
const DEGRADED_LATENCY_HIGH_MS = 10_000;
const DISCONNECT_CACHE_THRESHOLD_MS = 5 * 60 * 1_000; // 5 min

class ConnectivityManagerClass {
  private state: ConnectivityState = 'CONNECTED';
  private listeners: Set<ConnectivityListener> = new Set();
  private timerId: ReturnType<typeof setInterval> | null = null;
  private unreachableSince: number | null = null;
  private hasCachedData = false;

  start(): void {
    if (this.timerId !== null) return;
    void this.poll();
    this.timerId = setInterval(() => void this.poll(), POLL_INTERVAL_MS);
  }

  stop(): void {
    if (this.timerId !== null) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
  }

  /** Call when cache has data (so DISCONNECTED_CACHED can be used instead of DISCONNECTED_EMPTY). */
  setCacheAvailable(available: boolean): void {
    this.hasCachedData = available;
  }

  getState(): ConnectivityState {
    return this.state;
  }

  subscribe(listener: ConnectivityListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(next: ConnectivityState): void {
    if (next === this.state) return;
    this.state = next;
    this.listeners.forEach(l => l(next));
  }

  private async poll(): Promise<void> {
    const t0 = Date.now();
    try {
      const controller = new AbortController();
      const timeout = setTimeout(
        () => controller.abort(),
        DEGRADED_LATENCY_HIGH_MS + 500,
      );

      const res = await fetch(HEALTH_URL, {
        method: 'GET',
        signal: controller.signal,
      });
      clearTimeout(timeout);

      const latencyMs = Date.now() - t0;

      if (!res.ok) {
        this.handleUnreachable();
        return;
      }

      this.unreachableSince = null;

      if (latencyMs >= DEGRADED_LATENCY_LOW_MS) {
        this.emit('DEGRADED');
      } else {
        this.emit('CONNECTED');
      }
    } catch (err: unknown) {
      const isConnRefused =
        err instanceof TypeError &&
        (err.message.includes('ECONNREFUSED') ||
          err.message.includes('Network request failed'));

      if (isConnRefused) {
        // Could be HUB_SLEEPING (Tailscale up, port closed) — emit that before
        // falling through to unreachable logic after threshold.
        if (
          this.unreachableSince === null ||
          Date.now() - this.unreachableSince < DISCONNECT_CACHE_THRESHOLD_MS
        ) {
          this.emit('HUB_SLEEPING');
          if (this.unreachableSince === null) {
            this.unreachableSince = Date.now();
          }
          return;
        }
      }

      this.handleUnreachable();
    }
  }

  private handleUnreachable(): void {
    if (this.unreachableSince === null) {
      this.unreachableSince = Date.now();
    }

    const elapsed = Date.now() - this.unreachableSince;

    if (elapsed < DISCONNECT_CACHE_THRESHOLD_MS) {
      this.emit('RECONNECTING');
    } else if (this.hasCachedData) {
      this.emit('DISCONNECTED_CACHED');
    } else {
      this.emit('DISCONNECTED_EMPTY');
    }
  }
}

export const ConnectivityManager = new ConnectivityManagerClass();
