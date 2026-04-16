//! AppState — shared state managed by Tauri (S15-001, S15-003).

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;

use tokio::sync::Mutex;

use crate::container_runtime::ContainerRuntime;
use crate::keychain::KeychainManager;
use crate::watchdog::Watchdog;

pub struct AppState {
    pub runtime: Arc<dyn ContainerRuntime>,
    pub keychain: KeychainManager,
    pub app_data_dir: PathBuf,
    pub watchdog: Arc<Mutex<Watchdog>>,
    pub started_at: Instant,
}
