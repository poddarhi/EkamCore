use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;
use tauri::Manager;
use tokio::sync::Mutex;

mod commands;
mod container_runtime;
mod dashboard;
mod diagnostics;
mod disk;
mod docker;
mod hardware;
mod installer;
mod keychain;
mod launchd;
mod secret_injection;
mod setup;
mod startup;
mod state;
mod tailscale;
mod update;
mod watchdog;
mod wizard_state;

pub use wizard_state::WizardState;

/// Run the Tauri application.
pub fn run() {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let data_dir = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| PathBuf::from("."));
            tracing::info!("app_data_dir={}", data_dir.display());

            // Resolve the project root for docker-compose.yml.
            // In dev: ../../.. from src-tauri. In prod: bundled.
            let compose_dir = std::env::var("EKAMCORE_COMPOSE_DIR")
                .map(PathBuf::from)
                .unwrap_or_else(|_| {
                    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                        .join("../../..")
                });

            let runtime: Arc<dyn container_runtime::ContainerRuntime> =
                match container_runtime::DockerRuntime::new(compose_dir) {
                    Ok(r) => Arc::new(r),
                    Err(e) => {
                        tracing::warn!("docker_runtime_init_failed: {e}");
                        Arc::new(NoopRuntime)
                    }
                };

            // S15-003: Create watchdog
            let wd = Arc::new(Mutex::new(watchdog::Watchdog::new(runtime.clone())));

            let app_state = state::AppState {
                runtime,
                keychain: keychain::KeychainManager,
                app_data_dir: data_dir,
                watchdog: wd.clone(),
                started_at: Instant::now(),
            };
            app.manage(app_state);

            // S15-003: Watchdog is deferred — spawned from a Tauri command
            // when the frontend calls it, since setup() doesn't have a tokio runtime.
            tracing::info!("watchdog deferred to frontend init");

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // Existing wizard + startup commands
            hardware::check_hardware,
            disk::check_disk,
            docker::check_docker,
            tailscale::check_tailscale,
            startup::run_startup,
            wizard_state::is_setup_complete,
            wizard_state::mark_setup_complete,
            wizard_state::load_wizard_state,
            wizard_state::save_wizard_state,
            // S15-001: runtime management
            commands::get_service_health,
            commands::restart_service,
            commands::get_service_logs,
            commands::get_container_stats,
            commands::start_stack,
            commands::stop_stack,
            // S15-001: keychain
            commands::keychain_has_secret,
            commands::keychain_get_secret,
            commands::keychain_set_secret,
            commands::keychain_generate_secret,
            // S15-002: setup wizard steps 4-7
            setup::pull_images,
            setup::initialize_database,
            setup::create_admin,
            setup::request_permissions,
            setup::select_source_folders,
            setup::configure_paperless,
            // S15-003: dashboard + service controls
            dashboard::get_dashboard_data,
            dashboard::force_restart_service,
            dashboard::stop_all_services,
            dashboard::start_all_services,
            // S15-004: diagnostics + storage
            diagnostics::generate_diagnostics,
            diagnostics::get_system_info_text,
            diagnostics::clean_docker_cache,
            diagnostics::get_storage_breakdown,
            // S15-005: launchd + secret injection + settings
            launchd::register_login_item,
            launchd::unregister_login_item,
            launchd::is_login_item_registered,
            launchd::install_backup_schedule,
            launchd::uninstall_backup_schedule,
            launchd::get_launchd_status,
            launchd::run_backup_now,
            secret_injection::check_secret_status,
            secret_injection::inject_secrets_and_start,
            secret_injection::regenerate_all_secrets,
            secret_injection::reset_setup,
            // Self-contained installer
            installer::run_installer,
            installer::check_system_deps,
            // S15-006: update + rollback
            update::check_for_updates,
            update::apply_update,
            update::rollback_to_backup,
            update::list_backups,
        ])
        .run(tauri::generate_context!())
        .expect("error while running EkamCore Manager");
}

/// Fallback runtime when Docker is not available at startup.
struct NoopRuntime;

#[async_trait::async_trait]
impl container_runtime::ContainerRuntime for NoopRuntime {
    async fn start_stack(&self) -> Result<(), container_runtime::RuntimeError> {
        Err(container_runtime::RuntimeError::DockerUnavailable(
            "Docker was not available when the app started.".into(),
        ))
    }
    async fn stop_stack(&self) -> Result<(), container_runtime::RuntimeError> {
        Err(container_runtime::RuntimeError::DockerUnavailable(
            "Docker was not available when the app started.".into(),
        ))
    }
    async fn restart_service(
        &self,
        _service: &str,
    ) -> Result<(), container_runtime::RuntimeError> {
        Err(container_runtime::RuntimeError::DockerUnavailable(
            "Docker was not available when the app started.".into(),
        ))
    }
    async fn get_service_health(
        &self,
    ) -> Result<Vec<container_runtime::ServiceHealth>, container_runtime::RuntimeError> {
        Err(container_runtime::RuntimeError::DockerUnavailable(
            "Docker was not available when the app started.".into(),
        ))
    }
    async fn get_service_logs(
        &self,
        _service: &str,
        _lines: usize,
    ) -> Result<String, container_runtime::RuntimeError> {
        Err(container_runtime::RuntimeError::DockerUnavailable(
            "Docker was not available when the app started.".into(),
        ))
    }
    async fn get_container_stats(
        &self,
    ) -> Result<Vec<container_runtime::ContainerStats>, container_runtime::RuntimeError> {
        Err(container_runtime::RuntimeError::DockerUnavailable(
            "Docker was not available when the app started.".into(),
        ))
    }
}
