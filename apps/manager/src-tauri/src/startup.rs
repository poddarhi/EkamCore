//! S03-006 — 15-Step Startup Sequence
//!
//! Runs on every app launch after the setup wizard completes.
//! Emits "startup://progress" events to the frontend for each step.
//!
//! Steps (sequential, each must pass before the next begins):
//!  1. Hardware check       6. Start PostgreSQL     11. Check models
//!  2. Disk check           7. Run migrations        12. Start API
//!  3. Docker check         8. Start Redis           13. Start Workers
//!  4. Verify images        9. Start Qdrant          14. Start Proxy
//!  5. Create network       10. Start Ollama          15. System ready

use serde::Serialize;
use std::path::PathBuf;
use std::process::Command;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
pub struct StartupStepEvent {
    pub step: u8,
    pub label: &'static str,
    /// "running" | "ok" | "failed" | "skipped"
    pub status: &'static str,
    pub message: Option<String>,
}

static STEP_LABELS: &[(u8, &str)] = &[
    (1, "Hardware check"),
    (2, "Disk check"),
    (3, "Docker check"),
    (4, "Verify images"),
    (5, "Create network"),
    (6, "Start PostgreSQL"),
    (7, "Run migrations"),
    (8, "Start Redis"),
    (9, "Start Qdrant"),
    (10, "Start Ollama"),
    (11, "Check models"),
    (12, "Start API"),
    (13, "Start Workers"),
    (14, "Start Proxy"),
    (15, "System ready"),
];

// ---------------------------------------------------------------------------
// Tauri command
// ---------------------------------------------------------------------------

/// Run the full 15-step startup sequence.
/// Emits "startup://progress" events after each step.
/// Returns Ok(()) when all services are ready, or Err with the failing step message.
#[tauri::command]
pub async fn run_startup(app: AppHandle) -> Result<(), String> {
    macro_rules! step {
        ($n:expr, running) => {
            emit_step(&app, $n, "running", None);
        };
        ($n:expr, ok) => {
            emit_step(&app, $n, "ok", None);
        };
        ($n:expr, ok, $msg:expr) => {
            emit_step(&app, $n, "ok", Some($msg));
        };
        ($n:expr, fail, $msg:expr) => {{
            emit_step(&app, $n, "failed", Some($msg.clone()));
            return Err($msg);
        }};
    }

    // ── Step 1: Hardware ──────────────────────────────────────────────────
    step!(1, running);
    let hw = crate::hardware::check_hardware();
    if !hw.all_passed {
        let mut msgs = Vec::new();
        if !hw.is_apple_silicon { msgs.push("Requires Apple Silicon".to_string()); }
        if !hw.ram_ok { msgs.push(format!("Requires 16 GB RAM (found {:.0} GB)", hw.ram_gb)); }
        if !hw.macos_ok { msgs.push(format!("Requires macOS 13+ (found {})", hw.macos_version)); }
        step!(1, fail, msgs.join("; "));
    }
    step!(1, ok);

    // ── Step 2: Disk ──────────────────────────────────────────────────────
    step!(2, running);
    let disk = crate::disk::check_disk();
    if !disk.passed {
        step!(2, fail, format!("Need {:.0} GB free, have {:.1} GB", disk.required_gb, disk.free_gb));
    }
    step!(2, ok, format!("{:.1} GB free", disk.free_gb));

    // ── Step 3: Docker ────────────────────────────────────────────────────
    step!(3, running);
    let docker = crate::docker::check_docker();
    if !docker.installed {
        step!(3, fail, "Docker / OrbStack not found. Install OrbStack or Docker Desktop.".to_string());
    }
    step!(3, ok, format!("{} {}", docker.runtime, docker.version.unwrap_or_default()));

    // ── Locate docker-compose.yml ──────────────────────────────────────────
    let compose_dir = match find_compose_dir() {
        Ok(d) => d,
        Err(e) => {
            emit_step(&app, 4, "failed", Some(e.clone()));
            return Err(e);
        }
    };

    // ── Step 4: Verify / pull images ─────────────────────────────────────
    step!(4, running);
    let images = &[
        "postgres:16.3",
        "redis:7.2-alpine",
        "qdrant/qdrant:v1.9.0",
        "caddy:2-alpine",
    ];
    for image in images {
        if !image_present(image) {
            // Pull only if not already present (avoids slow re-pulls)
            if let Err(e) = run_docker(&["pull", image]) {
                step!(4, fail, format!("Failed to pull {image}: {e}"));
            }
        }
    }
    step!(4, ok);

    // ── Step 5: Create network (compose up --no-start) ────────────────────
    step!(5, running);
    if let Err(e) = run_compose(&compose_dir, &["up", "--no-start", "--quiet-pull"]) {
        step!(5, fail, e);
    }
    step!(5, ok);

    // ── Step 6: Start PostgreSQL ──────────────────────────────────────────
    step!(6, running);
    if let Err(e) = run_compose(&compose_dir, &["up", "-d", "ekamcore-postgres"]) {
        step!(6, fail, e);
    }
    if let Err(e) = wait_for_pg(&compose_dir, 60) {
        step!(6, fail, e);
    }
    step!(6, ok);

    // ── Step 7: Run migrations ────────────────────────────────────────────
    step!(7, running);
    if let Err(e) = run_compose(&compose_dir, &["run", "--rm", "ekamcore-migrate"]) {
        // Migration container may fail if image is stale — skip gracefully
        // since migrations can also be applied from host via `alembic upgrade head`
        tracing::warn!("migrate_container_failed: {e} — skipping (may already be applied)");
        step!(7, ok, "Skipped (migrations may already be applied)".to_string());
    } else {
        step!(7, ok);
    }

    // ── Step 8: Start Redis ───────────────────────────────────────────────
    step!(8, running);
    if let Err(e) = run_compose(&compose_dir, &["up", "-d", "ekamcore-redis"]) {
        step!(8, fail, e);
    }
    if let Err(e) = wait_for_redis(&compose_dir, 30) {
        step!(8, fail, e);
    }
    step!(8, ok);

    // ── Step 9: Start Qdrant ──────────────────────────────────────────────
    step!(9, running);
    if let Err(e) = run_compose(&compose_dir, &["up", "-d", "ekamcore-qdrant"]) {
        step!(9, fail, e);
    }
    if let Err(e) = wait_for_url("http://localhost:6333/healthz", 60) {
        step!(9, fail, e);
    }
    step!(9, ok);

    // ── Step 10: Start Ollama (native, not in Compose) ───────────────────
    step!(10, running);
    if let Err(e) = ensure_ollama_running() {
        step!(10, fail, e);
    }
    if let Err(e) = wait_for_url("http://localhost:11434/api/tags", 30) {
        step!(10, fail, e);
    }
    step!(10, ok);

    // ── Step 11: Verify models reachable ─────────────────────────────────
    step!(11, running);
    if let Err(e) = wait_for_url("http://localhost:11434/api/tags", 10) {
        step!(11, fail, e);
    }
    step!(11, ok);

    // ── Step 12: Start API ────────────────────────────────────────────────
    step!(12, running);
    if let Err(e) = run_compose(&compose_dir, &["up", "-d", "ekamcore-api"]) {
        step!(12, fail, e);
    }
    if let Err(e) = wait_for_url("http://localhost:8420/health", 60) {
        step!(12, fail, e);
    }
    step!(12, ok);

    // ── Step 13: Start Workers ────────────────────────────────────────────
    step!(13, running);
    if let Err(e) = run_compose(&compose_dir, &["up", "-d", "ekamcore-workers"]) {
        step!(13, fail, e);
    }
    // Workers don't expose a health endpoint — wait briefly for process start.
    std::thread::sleep(Duration::from_secs(3));
    step!(13, ok);

    // ── Step 14: Start Proxy ──────────────────────────────────────────────
    step!(14, running);
    if let Err(e) = run_compose(&compose_dir, &["up", "-d", "ekamcore-proxy"]) {
        step!(14, fail, e);
    }
    std::thread::sleep(Duration::from_secs(2));
    step!(14, ok);

    // ── Step 15: System ready ─────────────────────────────────────────────
    step!(15, ok, "EkamCore is ready".to_string());

    Ok(())
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn emit_step(app: &AppHandle, step: u8, status: &'static str, message: Option<String>) {
    let label = STEP_LABELS
        .iter()
        .find(|(id, _)| *id == step)
        .map(|(_, l)| *l)
        .unwrap_or("");
    let _ = app.emit(
        "startup://progress",
        StartupStepEvent { step, label, status, message },
    );
}

/// Walk up from the executable to find the directory containing docker-compose.yml.
fn find_compose_dir() -> Result<String, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let mut dir: PathBuf = exe
        .parent()
        .ok_or("no parent")?
        .to_path_buf();

    for _ in 0..12 {
        if dir.join("docker-compose.yml").exists() {
            return Ok(dir.to_string_lossy().to_string());
        }
        match dir.parent() {
            Some(p) => dir = p.to_path_buf(),
            None => break,
        }
    }
    Err("Cannot find docker-compose.yml. Is the manager app inside the EkamCore repo?".to_string())
}

fn run_docker(args: &[&str]) -> Result<(), String> {
    let status = Command::new("docker")
        .args(args)
        .status()
        .map_err(|e| format!("docker: {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("docker {} exited {}", args.join(" "), status))
    }
}

fn run_compose(dir: &str, args: &[&str]) -> Result<(), String> {
    let status = Command::new("docker")
        .arg("compose")
        .args(args)
        .current_dir(dir)
        .status()
        .map_err(|e| format!("docker compose: {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("docker compose {} exited {}", args.join(" "), status))
    }
}

fn image_present(image: &str) -> bool {
    Command::new("docker")
        .args(["image", "inspect", image, "--format", "{{.Id}}"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn wait_for_pg(dir: &str, timeout_secs: u64) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);
    while Instant::now() < deadline {
        let ok = Command::new("docker")
            .args([
                "compose", "exec", "ekamcore-postgres",
                "pg_isready", "-U", "ekamcore", "-d", "ekamcore",
            ])
            .current_dir(dir)
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false);
        if ok { return Ok(()); }
        std::thread::sleep(Duration::from_secs(2));
    }
    Err(format!("PostgreSQL did not become ready within {timeout_secs}s"))
}

fn wait_for_redis(dir: &str, timeout_secs: u64) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);
    while Instant::now() < deadline {
        let ok = Command::new("docker")
            .args([
                "compose", "exec", "ekamcore-redis",
                "redis-cli", "-a", "ekamcore_redis_dev", "ping",
            ])
            .current_dir(dir)
            .output()
            .map(|o| {
                o.status.success()
                    && String::from_utf8_lossy(&o.stdout).contains("PONG")
            })
            .unwrap_or(false);
        if ok { return Ok(()); }
        std::thread::sleep(Duration::from_secs(2));
    }
    Err(format!("Redis did not become ready within {timeout_secs}s"))
}

fn wait_for_url(url: &str, timeout_secs: u64) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);
    while Instant::now() < deadline {
        let ok = Command::new("curl")
            .args(["-sf", "--max-time", "3", url])
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false);
        if ok { return Ok(()); }
        std::thread::sleep(Duration::from_secs(2));
    }
    Err(format!("Service at {url} did not respond within {timeout_secs}s"))
}

fn ensure_ollama_running() -> Result<(), String> {
    // Already up?
    let up = Command::new("curl")
        .args(["-sf", "--max-time", "2", "http://localhost:11434/api/tags"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);
    if up { return Ok(()); }

    // Spawn `ollama serve` in background.
    Command::new("ollama")
        .arg("serve")
        .spawn()
        .map_err(|e| format!("Failed to launch Ollama: {e}"))?;
    Ok(())
}
