//! ContainerRuntime — abstraction over Docker/OrbStack lifecycle (S15-001).
//!
//! Trait: `ContainerRuntime` with start/stop/restart/health/logs/stats.
//! Impl: `DockerRuntime` backed by bollard (Docker Engine API).
//!
//! Per Architecture TechSpec AD-06: the trait boundary lets tests
//! inject a mock runtime without touching Docker at all.

use async_trait::async_trait;
use bollard::container::{
    InspectContainerOptions, ListContainersOptions, LogsOptions, StatsOptions,
};
use bollard::Docker;
use serde::Serialize;
use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Command as StdCommand;
use std::sync::Arc;

// ── Public types ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum HealthState {
    Healthy,
    Unhealthy,
    Starting,
    NotRunning,
}

#[derive(Debug, Clone, Serialize)]
pub struct ServiceHealth {
    pub name: String,
    pub state: HealthState,
    pub uptime_seconds: Option<u64>,
    pub memory_mb: Option<f64>,
    pub cpu_percent: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ContainerStats {
    pub name: String,
    pub memory_usage_mb: f64,
    pub memory_limit_mb: f64,
    pub cpu_percent: f64,
    pub network_rx_mb: f64,
    pub network_tx_mb: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PullProgress {
    pub image: String,
    pub status: String,
    pub progress_pct: Option<f64>,
}

#[derive(Debug, thiserror::Error)]
pub enum RuntimeError {
    #[error("Docker not available: {0}")]
    DockerUnavailable(String),
    #[error("Container operation failed: {0}")]
    OperationFailed(String),
    #[error("Bollard error: {0}")]
    Bollard(#[from] bollard::errors::Error),
}

impl Serialize for RuntimeError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

// ── Trait ─────────────────────────────────────────────────────────────────

#[async_trait]
pub trait ContainerRuntime: Send + Sync {
    async fn start_stack(&self) -> Result<(), RuntimeError>;
    async fn stop_stack(&self) -> Result<(), RuntimeError>;
    async fn restart_service(&self, service: &str) -> Result<(), RuntimeError>;
    async fn get_service_health(&self) -> Result<Vec<ServiceHealth>, RuntimeError>;
    async fn get_service_logs(
        &self,
        service: &str,
        lines: usize,
    ) -> Result<String, RuntimeError>;
    async fn get_container_stats(&self) -> Result<Vec<ContainerStats>, RuntimeError>;
}

// ── Docker implementation ────────────────────────────────────────────────

pub struct DockerRuntime {
    client: Docker,
    compose_dir: PathBuf,
}

impl DockerRuntime {
    /// Connect to the local Docker daemon via the default socket.
    pub fn new(compose_dir: PathBuf) -> Result<Self, RuntimeError> {
        let client = Docker::connect_with_local_defaults()
            .map_err(|e| RuntimeError::DockerUnavailable(e.to_string()))?;
        Ok(Self {
            client,
            compose_dir,
        })
    }

    fn compose_cmd(&self) -> StdCommand {
        let mut cmd = StdCommand::new("docker");
        cmd.args(["compose", "-f"])
            .arg(self.compose_dir.join("docker-compose.yml"))
            .arg("--project-name")
            .arg("ekamcore");
        cmd
    }

    fn run_compose(&self, args: &[&str]) -> Result<(), RuntimeError> {
        let mut cmd = self.compose_cmd();
        cmd.args(args);
        let output = cmd
            .output()
            .map_err(|e| RuntimeError::OperationFailed(e.to_string()))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(RuntimeError::OperationFailed(stderr.to_string()));
        }
        Ok(())
    }

    async fn list_ekamcore_containers(
        &self,
    ) -> Result<Vec<bollard::models::ContainerSummary>, RuntimeError> {
        let mut filters = HashMap::new();
        filters.insert(
            "label",
            vec!["com.docker.compose.project=ekamcore"],
        );
        let opts = ListContainersOptions {
            all: true,
            filters,
            ..Default::default()
        };
        Ok(self.client.list_containers(Some(opts)).await?)
    }
}

#[async_trait]
impl ContainerRuntime for DockerRuntime {
    async fn start_stack(&self) -> Result<(), RuntimeError> {
        self.run_compose(&["up", "-d"])
    }

    async fn stop_stack(&self) -> Result<(), RuntimeError> {
        self.run_compose(&["down"])
    }

    async fn restart_service(&self, service: &str) -> Result<(), RuntimeError> {
        self.run_compose(&["restart", service])
    }

    async fn get_service_health(&self) -> Result<Vec<ServiceHealth>, RuntimeError> {
        let containers = self.list_ekamcore_containers().await?;
        let mut results = Vec::with_capacity(containers.len());

        for c in &containers {
            let name = c
                .names
                .as_ref()
                .and_then(|n| n.first())
                .map(|n| n.trim_start_matches('/').to_string())
                .unwrap_or_default();

            let running = c.state.as_deref() == Some("running");
            let health = if !running {
                HealthState::NotRunning
            } else {
                match c.status.as_deref().unwrap_or("") {
                    s if s.contains("healthy") => HealthState::Healthy,
                    s if s.contains("starting") => HealthState::Starting,
                    s if s.contains("unhealthy") => HealthState::Unhealthy,
                    _ if running => HealthState::Healthy, // no health check defined
                    _ => HealthState::NotRunning,
                }
            };

            results.push(ServiceHealth {
                name,
                state: health,
                uptime_seconds: None, // computed from created_at if needed
                memory_mb: None,
                cpu_percent: None,
            });
        }

        Ok(results)
    }

    async fn get_service_logs(
        &self,
        service: &str,
        lines: usize,
    ) -> Result<String, RuntimeError> {
        use futures_util::StreamExt;

        let opts = LogsOptions::<String> {
            stdout: true,
            stderr: true,
            tail: lines.to_string(),
            ..Default::default()
        };
        let mut stream = self.client.logs(service, Some(opts));
        let mut output = String::new();
        while let Some(Ok(chunk)) = stream.next().await {
            output.push_str(&chunk.to_string());
        }
        Ok(output)
    }

    async fn get_container_stats(&self) -> Result<Vec<ContainerStats>, RuntimeError> {
        use futures_util::StreamExt;

        let containers = self.list_ekamcore_containers().await?;
        let mut results = Vec::new();

        for c in &containers {
            let id = match &c.id {
                Some(id) => id.clone(),
                None => continue,
            };
            let name = c
                .names
                .as_ref()
                .and_then(|n| n.first())
                .map(|n| n.trim_start_matches('/').to_string())
                .unwrap_or_default();

            let opts = StatsOptions {
                stream: false,
                one_shot: true,
            };
            let mut stream = self.client.stats(&id, Some(opts));
            if let Some(Ok(stats)) = stream.next().await {
                let mem_usage = stats.memory_stats.usage.unwrap_or(0) as f64 / 1_048_576.0;
                let mem_limit = stats.memory_stats.limit.unwrap_or(1) as f64 / 1_048_576.0;

                let cpu_delta = stats
                    .cpu_stats
                    .cpu_usage
                    .total_usage
                    .saturating_sub(
                        stats
                            .precpu_stats
                            .cpu_usage
                            .total_usage,
                    ) as f64;
                let sys_delta = stats
                    .cpu_stats
                    .system_cpu_usage
                    .unwrap_or(0)
                    .saturating_sub(
                        stats.precpu_stats.system_cpu_usage.unwrap_or(0),
                    ) as f64;
                let num_cpus = stats
                    .cpu_stats
                    .online_cpus
                    .unwrap_or(1) as f64;
                let cpu_pct = if sys_delta > 0.0 {
                    (cpu_delta / sys_delta) * num_cpus * 100.0
                } else {
                    0.0
                };

                let (rx, tx) = stats
                    .networks
                    .as_ref()
                    .map(|nets| {
                        nets.values().fold((0u64, 0u64), |(r, t), n| {
                            (r + n.rx_bytes, t + n.tx_bytes)
                        })
                    })
                    .unwrap_or((0, 0));

                results.push(ContainerStats {
                    name,
                    memory_usage_mb: (mem_usage * 100.0).round() / 100.0,
                    memory_limit_mb: (mem_limit * 100.0).round() / 100.0,
                    cpu_percent: (cpu_pct * 100.0).round() / 100.0,
                    network_rx_mb: (rx as f64 / 1_048_576.0 * 100.0).round() / 100.0,
                    network_tx_mb: (tx as f64 / 1_048_576.0 * 100.0).round() / 100.0,
                });
            }
        }

        Ok(results)
    }
}
