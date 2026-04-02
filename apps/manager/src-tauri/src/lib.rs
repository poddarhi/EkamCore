use tauri::Manager;

mod disk;
mod docker;
mod hardware;
mod startup;
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
            // Log app data directory on startup
            if let Some(data_dir) = app.path().app_data_dir().ok() {
                tracing::info!("app_data_dir={}", data_dir.display());
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            hardware::check_hardware,
            disk::check_disk,
            docker::check_docker,
            tailscale::check_tailscale,
            startup::run_startup,
            wizard_state::is_setup_complete,
            wizard_state::mark_setup_complete,
            wizard_state::load_wizard_state,
            wizard_state::save_wizard_state,
        ])
        .run(tauri::generate_context!())
        .expect("error while running EkamCore Manager");
}
