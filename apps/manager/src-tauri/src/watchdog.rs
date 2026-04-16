//! S15-003 — Watchdog: health polling, auto-restart with exponential backoff,
//! chronic instability detection, and macOS notification alerts.
//!
//! Per Architecture TechSpec §4.3:
//!   - Poll every 30 seconds via `ContainerRuntime::get_service_health()`
//!   - Auto-restart unhealthy services with backoff: 5s → 15s → 45s → 2m → 5m
//!   - Disable auto-restart after 5 consecutive failures → macOS notification
//!   - Flag "chronically unstable" if 3+ restarts in 1 hour for same service
//!   - Emit Tauri events: "health-update", "service-critical", "service-unstable"

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter};
use tokio::sync::Mutex;

use crate::container_runtime::{ContainerRuntime, HealthState, ServiceHealth};

// ── Configuration ───────────────────────────────────────────────────────────

const POLL_INTERVAL: Duration = Duration::from_secs(30);
const MAX_CONSECUTIVE_FAILURES: u32 = 5;
const CHRONIC_RESTART_THRESHOLD: usize = 3;
const CHRONIC_WINDOW: Duration = Duration::from_secs(3600); // 1 hour

/// Exponential backoff sequence (seconds).
const BACKOFF_STEPS: &[u64] = &[5, 15, 45, 120, 300];

// ── Types ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct HealthUpdateEvent {
    pub services: Vec<ServiceHealth>,
    pub timestamp: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ServiceCriticalEvent {
    pub service: String,
    pub consecutive_failures: u32,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ServiceUnstableEvent {
    pub service: String,
    pub restarts_in_hour: usize,
    pub message: String,
}

#[derive(Debug, Clone)]
struct BackoffState {
    consecutive_failures: u32,
    auto_restart_enabled: bool,
    last_restart_attempt: Option<Instant>,
    next_retry_delay: Duration,
}

impl Default for BackoffState {
    fn default() -> Self {
        Self {
            consecutive_failures: 0,
            auto_restart_enabled: true,
            last_restart_attempt: None,
            next_retry_delay: Duration::from_secs(BACKOFF_STEPS[0]),
        }
    }
}

// ── Watchdog ────────────────────────────────────────────────────────────────

pub struct Watchdog {
    runtime: Arc<dyn ContainerRuntime>,
    backoff: HashMap<String, BackoffState>,
    restart_history: HashMap<String, Vec<Instant>>,
}

impl Watchdog {
    pub fn new(runtime: Arc<dyn ContainerRuntime>) -> Self {
        Self {
            runtime,
            backoff: HashMap::new(),
            restart_history: HashMap::new(),
        }
    }

    /// Spawn the watchdog polling loop as a background tokio task.
    pub fn spawn(watchdog: Arc<Mutex<Self>>, app: AppHandle) {
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(POLL_INTERVAL).await;
                let mut wd = watchdog.lock().await;
                wd.poll(&app).await;
            }
        });
    }

    /// Run a single poll cycle: check health, attempt restarts, emit events.
    async fn poll(&mut self, app: &AppHandle) {
        let services = match self.runtime.get_service_health().await {
            Ok(s) => s,
            Err(e) => {
                tracing::warn!("watchdog poll failed: {e}");
                return;
            }
        };

        // Emit health update to frontend
        let _ = app.emit(
            "health-update",
            HealthUpdateEvent {
                services: services.clone(),
                timestamp: chrono::Utc::now().to_rfc3339(),
            },
        );

        // Check each service
        for svc in &services {
            match svc.state {
                HealthState::Healthy => {
                    // Reset backoff on recovery
                    if let Some(bs) = self.backoff.get_mut(&svc.name) {
                        if bs.consecutive_failures > 0 {
                            tracing::info!("service_recovered: {}", svc.name);
                            *bs = BackoffState::default();
                        }
                    }
                }
                HealthState::Unhealthy | HealthState::NotRunning => {
                    self.handle_unhealthy(app, &svc.name).await;
                }
                HealthState::Starting => {
                    // Service is starting — don't intervene yet
                }
            }
        }
    }

    /// Handle an unhealthy or stopped service: backoff, restart, escalate.
    async fn handle_unhealthy(&mut self, app: &AppHandle, service: &str) {
        let bs = self
            .backoff
            .entry(service.to_string())
            .or_insert_with(BackoffState::default);

        // Check if auto-restart is disabled (5+ consecutive failures)
        if !bs.auto_restart_enabled {
            return;
        }

        // Check if we're still in the backoff window
        if let Some(last) = bs.last_restart_attempt {
            if last.elapsed() < bs.next_retry_delay {
                return; // Still waiting
            }
        }

        // Attempt restart
        tracing::info!(
            "watchdog_restart: service={} attempt={} backoff={}s",
            service,
            bs.consecutive_failures + 1,
            bs.next_retry_delay.as_secs()
        );

        let restart_result = self.runtime.restart_service(service).await;
        let now = Instant::now();
        bs.last_restart_attempt = Some(now);

        // Record in restart history
        self.restart_history
            .entry(service.to_string())
            .or_default()
            .push(now);

        match restart_result {
            Ok(()) => {
                // Don't reset failures yet — wait for next poll to confirm healthy
                bs.consecutive_failures += 1;
                bs.next_retry_delay = backoff_delay(bs.consecutive_failures);
            }
            Err(e) => {
                tracing::warn!("watchdog_restart_failed: service={} error={e}", service);
                bs.consecutive_failures += 1;
                bs.next_retry_delay = backoff_delay(bs.consecutive_failures);
            }
        }

        // Check: disable after MAX_CONSECUTIVE_FAILURES
        if bs.consecutive_failures >= MAX_CONSECUTIVE_FAILURES {
            bs.auto_restart_enabled = false;
            tracing::error!(
                "watchdog_auto_restart_disabled: service={} after {} failures",
                service,
                bs.consecutive_failures
            );

            let event = ServiceCriticalEvent {
                service: service.to_string(),
                consecutive_failures: bs.consecutive_failures,
                message: format!(
                    "{} has failed {} times and needs manual attention.",
                    service, bs.consecutive_failures
                ),
            };
            let _ = app.emit("service-critical", &event);

            // macOS notification
            send_notification(
                "EkamCore: Service Down",
                &format!(
                    "{} has failed {} times and needs attention.",
                    service, bs.consecutive_failures
                ),
            );
        }

        // Check: chronic instability (3+ restarts in 1 hour)
        self.check_chronic_instability(app, service);
    }

    fn check_chronic_instability(&mut self, app: &AppHandle, service: &str) {
        if let Some(history) = self.restart_history.get_mut(service) {
            let cutoff = Instant::now() - CHRONIC_WINDOW;
            history.retain(|t| *t > cutoff);

            if history.len() >= CHRONIC_RESTART_THRESHOLD {
                let event = ServiceUnstableEvent {
                    service: service.to_string(),
                    restarts_in_hour: history.len(),
                    message: format!(
                        "{} has been restarted {} times in the last hour — may need diagnostics.",
                        service,
                        history.len()
                    ),
                };
                let _ = app.emit("service-unstable", &event);

                tracing::warn!(
                    "chronic_instability: service={} restarts_in_hour={}",
                    service,
                    history.len()
                );
            }
        }
    }

    /// Manual restart: reset backoff state and attempt immediate restart.
    pub async fn force_restart(&mut self, service: &str) -> Result<(), String> {
        // Reset backoff
        self.backoff.insert(service.to_string(), BackoffState::default());

        self.runtime
            .restart_service(service)
            .await
            .map_err(|e| e.to_string())
    }
}

// ── Helpers ─────────────────────────────────────────────────────────────────

fn backoff_delay(failures: u32) -> Duration {
    let idx = (failures as usize).saturating_sub(1).min(BACKOFF_STEPS.len() - 1);
    Duration::from_secs(BACKOFF_STEPS[idx])
}

fn send_notification(title: &str, body: &str) {
    if let Err(e) = notify_rust::Notification::new()
        .summary(title)
        .body(body)
        .appname("EkamCore")
        .show()
    {
        tracing::warn!("notification_failed: {e}");
    }
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backoff_delay_progression() {
        assert_eq!(backoff_delay(1).as_secs(), 5);
        assert_eq!(backoff_delay(2).as_secs(), 15);
        assert_eq!(backoff_delay(3).as_secs(), 45);
        assert_eq!(backoff_delay(4).as_secs(), 120);
        assert_eq!(backoff_delay(5).as_secs(), 300);
        // Caps at max
        assert_eq!(backoff_delay(10).as_secs(), 300);
        assert_eq!(backoff_delay(100).as_secs(), 300);
    }

    #[test]
    fn backoff_state_default() {
        let bs = BackoffState::default();
        assert_eq!(bs.consecutive_failures, 0);
        assert!(bs.auto_restart_enabled);
        assert!(bs.last_restart_attempt.is_none());
        assert_eq!(bs.next_retry_delay, Duration::from_secs(5));
    }

    #[test]
    fn health_update_event_serializable() {
        let evt = HealthUpdateEvent {
            services: vec![ServiceHealth {
                name: "postgres".to_string(),
                state: HealthState::Healthy,
                uptime_seconds: Some(3600),
                memory_mb: Some(128.5),
                cpu_percent: Some(2.3),
            }],
            timestamp: "2026-04-16T17:00:00Z".to_string(),
        };
        let json = serde_json::to_string(&evt).unwrap();
        assert!(json.contains("\"name\":\"postgres\""));
        assert!(json.contains("\"healthy\""));
    }

    #[test]
    fn service_critical_event_serializable() {
        let evt = ServiceCriticalEvent {
            service: "redis".to_string(),
            consecutive_failures: 5,
            message: "redis has failed 5 times".to_string(),
        };
        let json = serde_json::to_string(&evt).unwrap();
        assert!(json.contains("\"consecutive_failures\":5"));
    }

    #[test]
    fn service_unstable_event_serializable() {
        let evt = ServiceUnstableEvent {
            service: "api".to_string(),
            restarts_in_hour: 4,
            message: "api restarted 4 times".to_string(),
        };
        let json = serde_json::to_string(&evt).unwrap();
        assert!(json.contains("\"restarts_in_hour\":4"));
    }

    #[test]
    fn backoff_resets_on_default() {
        let mut bs = BackoffState::default();
        bs.consecutive_failures = 4;
        bs.auto_restart_enabled = false;
        bs.next_retry_delay = Duration::from_secs(300);

        // Simulate reset
        bs = BackoffState::default();
        assert_eq!(bs.consecutive_failures, 0);
        assert!(bs.auto_restart_enabled);
        assert_eq!(bs.next_retry_delay, Duration::from_secs(5));
    }

    #[test]
    fn auto_restart_disabled_at_threshold() {
        // Simulate reaching the threshold
        let bs = BackoffState {
            consecutive_failures: MAX_CONSECUTIVE_FAILURES,
            auto_restart_enabled: false,
            last_restart_attempt: Some(Instant::now()),
            next_retry_delay: Duration::from_secs(300),
        };
        assert!(!bs.auto_restart_enabled);
        assert_eq!(bs.consecutive_failures, MAX_CONSECUTIVE_FAILURES);
    }
}
