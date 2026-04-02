//! Wizard state persistence: ~/Library/Application Support/EkamCore/setup-state.json

use std::collections::HashMap;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum StepStatus {
    Pending,
    InProgress,
    Passed,
    Failed,
    Skipped,
}

impl Default for StepStatus {
    fn default() -> Self {
        Self::Pending
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WizardState {
    pub current_step: u8,
    pub steps: HashMap<String, StepStatus>,
    pub completed: bool,
}

impl Default for WizardState {
    fn default() -> Self {
        let mut steps = HashMap::new();
        for i in 1..=8u8 {
            steps.insert(i.to_string(), StepStatus::Pending);
        }
        Self {
            current_step: 1,
            steps,
            completed: false,
        }
    }
}

fn state_path(app: &AppHandle) -> anyhow::Result<PathBuf> {
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| anyhow::anyhow!("cannot resolve app_data_dir: {e}"))?;
    std::fs::create_dir_all(&data_dir)?;
    Ok(data_dir.join("setup-state.json"))
}

/// Return true if the wizard was previously completed.
#[tauri::command]
pub fn is_setup_complete(app: AppHandle) -> bool {
    load_wizard_state(app)
        .map(|s| s.completed)
        .unwrap_or(false)
}

/// Persist the completed flag.
#[tauri::command]
pub fn mark_setup_complete(app: AppHandle) -> Result<(), String> {
    let mut state = load_wizard_state(app.clone()).unwrap_or_default();
    state.completed = true;
    save_wizard_state(app, state)
}

/// Load the persisted wizard state (returns default if the file does not exist).
#[tauri::command]
pub fn load_wizard_state(app: AppHandle) -> Result<WizardState, String> {
    let path = state_path(&app).map_err(|e| e.to_string())?;
    if !path.exists() {
        return Ok(WizardState::default());
    }
    let raw = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&raw).map_err(|e| e.to_string())
}

/// Save the wizard state to disk.
#[tauri::command]
pub fn save_wizard_state(app: AppHandle, state: WizardState) -> Result<(), String> {
    let path = state_path(&app).map_err(|e| e.to_string())?;
    let json = serde_json::to_string_pretty(&state).map_err(|e| e.to_string())?;
    std::fs::write(&path, json).map_err(|e| e.to_string())
}
