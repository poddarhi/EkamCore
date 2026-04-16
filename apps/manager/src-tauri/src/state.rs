//! AppState — shared state managed by Tauri (S15-001).

use std::path::PathBuf;
use std::sync::Arc;

use crate::container_runtime::ContainerRuntime;
use crate::keychain::KeychainManager;

pub struct AppState {
    pub runtime: Arc<dyn ContainerRuntime>,
    pub keychain: KeychainManager,
    pub app_data_dir: PathBuf,
}
