use std::path::PathBuf;
use std::sync::Arc;
use tauri::Manager;

mod commands;
mod container_runtime;
mod disk;
mod docker;
mod hardware;
mod keychain;
mod startup;
mod state;
mod tailscale;
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
                        // The app will still launch — commands that need
                        // the runtime will return errors at call time.
                        // For now, create a fallback that always errors.
                        Arc::new(NoopRuntime)
                    }
                };

            let app_state = state::AppState {
                runtime,
                keychain: keychain::KeychainManager,
                app_data_dir: data_dir,
            };
            app.manage(app_state);
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
