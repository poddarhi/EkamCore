#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SupervisionSnapshot {
    source: String,
    collected_at_ms: u64,
    summary: String,
    next_integration: String,
    runtime: RuntimeSnapshot,
    setup_checks: Vec<SetupCheck>,
    services: Vec<ServiceRecord>,
    diagnostics: Vec<DiagnosticFact>,
    settings: Vec<SettingFact>,
    logs: Vec<LogEntry>,
    activity: Vec<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeSnapshot {
    context_name: String,
    docker_app_installed: bool,
    context_available: bool,
    engine_reachable: bool,
    compose_file_present: bool,
    compose_services_defined: bool,
    status: String,
    detail: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SetupCheck {
    id: String,
    label: String,
    status: String,
    detail: String,
    next_step: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ServiceRecord {
    id: String,
    label: String,
    category: String,
    status: String,
    detail: String,
    action_hint: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DiagnosticFact {
    label: String,
    value: String,
    tone: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SettingFact {
    label: String,
    value: String,
    detail: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct LogEntry {
    id: String,
    level: String,
    source: String,
    message: String,
}

#[tauri::command]
fn get_supervision_snapshot() -> SupervisionSnapshot {
    build_supervision_snapshot()
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../.."))
}

fn current_time_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis() as u64)
        .unwrap_or(0)
}

fn resolve_docker_binary() -> String {
    for candidate in ["/opt/homebrew/bin/docker", "/usr/local/bin/docker", "docker"] {
        if command_success(candidate, &["--version"]) {
            return candidate.to_string();
        }
    }

    "docker".to_string()
}

fn command_success(binary: &str, args: &[&str]) -> bool {
    Command::new(binary)
        .args(args)
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn command_output(binary: &str, args: &[String]) -> Option<String> {
    let output = Command::new(binary).args(args).output().ok()?;
    if !output.status.success() {
        return None;
    }

    String::from_utf8(output.stdout)
        .ok()
        .map(|value| value.trim().to_string())
}

fn build_supervision_snapshot() -> SupervisionSnapshot {
    let repo_root = repo_root();
    let docker_context = env::var("EKAMCORE_DOCKER_CONTEXT").unwrap_or_else(|_| "desktop-linux".to_string());
    let docker_binary = resolve_docker_binary();
    let docker_app_installed = Path::new("/Applications/Docker.app").exists();
    let compose_file = repo_root.join("infra/runtime/docker-compose.yml");
    let contract_file = repo_root.join("docs/contracts/ekamcore-api.yaml");
    let shared_types_file = repo_root.join("packages/shared-types/src/generated/ekamcore-api.ts");
    let backend_main = repo_root.join("apps/backend/app/main.py");

    let context_available = command_success(
        &docker_binary,
        &["context", "inspect", docker_context.as_str()],
    );
    let engine_reachable = command_success(
        &docker_binary,
        &["--context", docker_context.as_str(), "info"],
    );
    let compose_file_present = compose_file.is_file();
    let compose_services_defined = if compose_file_present {
        let args = vec![
            "--context".to_string(),
            docker_context.clone(),
            "compose".to_string(),
            "-f".to_string(),
            compose_file.to_string_lossy().to_string(),
            "config".to_string(),
            "--services".to_string(),
        ];

        command_output(&docker_binary, &args)
            .map(|output| !output.is_empty())
            .unwrap_or(false)
    } else {
        false
    };

    let runtime_status = if engine_reachable {
        "healthy"
    } else if docker_app_installed && context_available {
        "warning"
    } else if docker_app_installed {
        "attention"
    } else {
        "blocked"
    };

    let runtime_detail = if engine_reachable {
        format!(
            "Docker Desktop context '{}' responded successfully on this Mac.",
            docker_context
        )
    } else if docker_app_installed && context_available {
        format!(
            "Docker Desktop is installed and context '{}' exists, but the engine is not reachable yet.",
            docker_context
        )
    } else if docker_app_installed {
        format!(
            "Docker Desktop is installed, but context '{}' is not available yet.",
            docker_context
        )
    } else {
        "Docker Desktop is not installed at /Applications/Docker.app.".to_string()
    };

    let runtime = RuntimeSnapshot {
        context_name: docker_context.clone(),
        docker_app_installed,
        context_available,
        engine_reachable,
        compose_file_present,
        compose_services_defined,
        status: runtime_status.to_string(),
        detail: runtime_detail.clone(),
    };

    let setup_checks = vec![
        SetupCheck {
            id: "docker-desktop".to_string(),
            label: "Docker Desktop installed".to_string(),
            status: if docker_app_installed {
                "healthy".to_string()
            } else {
                "blocked".to_string()
            },
            detail: if docker_app_installed {
                "The accepted v1 runtime substrate is installed.".to_string()
            } else {
                "The accepted v1 runtime substrate is not installed yet.".to_string()
            },
            next_step: if docker_app_installed {
                None
            } else {
                Some("Install Docker Desktop and complete first-run setup.".to_string())
            },
        },
        SetupCheck {
            id: "docker-context".to_string(),
            label: "Local Docker context ready".to_string(),
            status: if context_available {
                "healthy".to_string()
            } else {
                "attention".to_string()
            },
            detail: format!(
                "Runtime scripts expect the local Docker context '{}' by default.",
                docker_context
            ),
            next_step: if context_available {
                None
            } else {
                Some("Open Docker Desktop once so the local context is initialized.".to_string())
            },
        },
        SetupCheck {
            id: "shared-types".to_string(),
            label: "Generated contract types present".to_string(),
            status: if shared_types_file.is_file() {
                "healthy".to_string()
            } else {
                "warning".to_string()
            },
            detail: if shared_types_file.is_file() {
                "The generated OpenAPI TypeScript artifact is present for client consumption.".to_string()
            } else {
                "The generated TypeScript artifact is missing.".to_string()
            },
            next_step: if shared_types_file.is_file() {
                None
            } else {
                Some("Run pnpm generate:shared-types from the repo root.".to_string())
            },
        },
        SetupCheck {
            id: "backend-stub".to_string(),
            label: "Backend stub service scaffolded".to_string(),
            status: if backend_main.is_file() {
                "healthy".to_string()
            } else {
                "planned".to_string()
            },
            detail: if backend_main.is_file() {
                "FastAPI stub routes are present in apps/backend/app/main.py.".to_string()
            } else {
                "Backend scaffolding has not been added yet.".to_string()
            },
            next_step: if backend_main.is_file() {
                Some("Run pnpm dev:backend when the backend virtualenv is installed.".to_string())
            } else {
                None
            },
        },
    ];

    let services = vec![
        ServiceRecord {
            id: "runtime".to_string(),
            label: "Docker Desktop runtime".to_string(),
            category: "Runtime".to_string(),
            status: runtime.status.clone(),
            detail: runtime.detail.clone(),
            action_hint: Some("Use runtime:start and runtime:stop for repo-managed lifecycle steps.".to_string()),
        },
        ServiceRecord {
            id: "manager-app".to_string(),
            label: "Manager app shell".to_string(),
            category: "Desktop".to_string(),
            status: "healthy".to_string(),
            detail: "Tauri shell is running and invoking the supervision adapter.".to_string(),
            action_hint: None,
        },
        ServiceRecord {
            id: "api-contract".to_string(),
            label: "API contract and shared types".to_string(),
            category: "Contract".to_string(),
            status: if contract_file.is_file() && shared_types_file.is_file() {
                "healthy".to_string()
            } else {
                "warning".to_string()
            },
            detail: "OpenAPI is the source of truth and generated TS types back the manager-app contract baseline.".to_string(),
            action_hint: Some("Run pnpm lint:api and pnpm generate:shared-types after contract edits.".to_string()),
        },
        ServiceRecord {
            id: "backend".to_string(),
            label: "FastAPI stub backend".to_string(),
            category: "Backend".to_string(),
            status: if backend_main.is_file() {
                "attention".to_string()
            } else {
                "planned".to_string()
            },
            detail: "Stub routes exist, but the manager app does not poll the backend live yet.".to_string(),
            action_hint: Some("Next thin slice: manager app health polling and Today preview.".to_string()),
        },
    ];

    let diagnostics = vec![
        DiagnosticFact {
            label: "Snapshot source".to_string(),
            value: "tauri-live".to_string(),
            tone: "healthy".to_string(),
        },
        DiagnosticFact {
            label: "Host architecture".to_string(),
            value: env::consts::ARCH.to_string(),
            tone: "healthy".to_string(),
        },
        DiagnosticFact {
            label: "Runtime context".to_string(),
            value: docker_context.clone(),
            tone: if context_available {
                "healthy".to_string()
            } else {
                "warning".to_string()
            },
        },
        DiagnosticFact {
            label: "Compose services defined".to_string(),
            value: if compose_services_defined {
                "Yes".to_string()
            } else {
                "No".to_string()
            },
            tone: if compose_services_defined {
                "healthy".to_string()
            } else {
                "planned".to_string()
            },
        },
        DiagnosticFact {
            label: "Contract file present".to_string(),
            value: if contract_file.is_file() {
                "Yes".to_string()
            } else {
                "No".to_string()
            },
            tone: if contract_file.is_file() {
                "healthy".to_string()
            } else {
                "blocked".to_string()
            },
        },
    ];

    let settings = vec![
        SettingFact {
            label: "Runtime substrate".to_string(),
            value: "Docker Desktop".to_string(),
            detail: "Accepted in ADR 0001 for the v1 local runtime path.".to_string(),
        },
        SettingFact {
            label: "Docker context".to_string(),
            value: docker_context.clone(),
            detail: "Runtime scripts validate this local context by default.".to_string(),
        },
        SettingFact {
            label: "Contract source of truth".to_string(),
            value: "OpenAPI 3.1".to_string(),
            detail: "docs/contracts/ekamcore-api.yaml drives shared TypeScript generation.".to_string(),
        },
        SettingFact {
            label: "Workspace scoping".to_string(),
            value: "Explicit at API boundary".to_string(),
            detail: "Today, Recap, and job polling are scoped with workspace identifiers.".to_string(),
        },
    ];

    let mut logs = Vec::new();
    logs.push(LogEntry {
        id: "runtime-snapshot".to_string(),
        level: if engine_reachable {
            "info".to_string()
        } else if docker_app_installed {
            "warning".to_string()
        } else {
            "error".to_string()
        },
        source: "runtime".to_string(),
        message: runtime.detail.clone(),
    });
    logs.push(LogEntry {
        id: "contract-snapshot".to_string(),
        level: if contract_file.is_file() && shared_types_file.is_file() {
            "info".to_string()
        } else {
            "warning".to_string()
        },
        source: "contract".to_string(),
        message: if shared_types_file.is_file() {
            "OpenAPI contract and generated shared types are present.".to_string()
        } else {
            "OpenAPI contract exists, but generated shared types are missing.".to_string()
        },
    });

    SupervisionSnapshot {
        source: "tauri-live".to_string(),
        collected_at_ms: current_time_ms(),
        summary: if engine_reachable {
            "Local runtime checks are live and the manager app is supervising the first Sprint 0 stack facts.".to_string()
        } else {
            "Manager app is live, but the local runtime still needs attention before service startup.".to_string()
        },
        next_integration: "Connect the manager app to the FastAPI health and summary stubs.".to_string(),
        runtime,
        setup_checks,
        services,
        diagnostics,
        settings,
        logs,
        activity: vec![
            "The service supervision adapter now produces structured runtime, contract, and backend status.".to_string(),
            "Generated shared types are present for manager-app consumption.".to_string(),
            "FastAPI stubs are ready for the next thin end-to-end integration path.".to_string(),
        ],
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_supervision_snapshot])
        .run(tauri::generate_context!())
        .expect("error while running EkamCore manager app");
}
