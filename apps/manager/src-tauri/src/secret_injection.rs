//! S15-005 — Keychain secret injection into Docker containers.
//!
//! Per ART-14 §13.1: reads all 8 secrets from macOS Keychain,
//! writes a temporary .env file (mode 0600), runs docker compose up,
//! waits for containers to read env, then securely deletes the temp file.
//!
//! Handles Keychain lock state gracefully — if the Keychain is locked
//! (screen locked), returns a specific error prompting the user to unlock.

use serde::Serialize;
use std::io::Write;
use std::path::PathBuf;
use std::process::Command;

use tauri::State;

use crate::keychain::{services, KeychainManager};
use crate::state::AppState;

// ── Types ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct SecretStatus {
    pub all_present: bool,
    pub missing: Vec<String>,
    pub keychain_accessible: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct InjectionResult {
    pub success: bool,
    pub message: String,
    pub containers_healthy: bool,
}

// ── All service secrets ─────────────────────────────────────────────────────

const ALL_SECRETS: &[(&str, &str)] = &[
    (services::POSTGRESQL, "POSTGRES_PASSWORD"),
    (services::REDIS, "REDIS_PASSWORD"),
    (services::QDRANT, "QDRANT_API_KEY"),
    (services::JWT_PRIVATE, "JWT_PRIVATE_KEY"),
    (services::JWT_PUBLIC, "JWT_PUBLIC_KEY"),
    (services::DATA_ENCRYPTION, "DATA_ENCRYPTION_KEY"),
    (services::FACE_EMBED_KEY, "FACE_EMBED_KEY"),
    (services::PAPERLESS_SECRET, "PAPERLESS_SECRET_KEY"),
];

// ── Commands ────────────────────────────────────────────────────────────────

/// Check if all secrets are present in the Keychain and accessible.
#[tauri::command]
pub fn check_secret_status() -> SecretStatus {
    let mut missing = Vec::new();
    let mut keychain_accessible = true;

    for (service, _env_var) in ALL_SECRETS {
        match KeychainManager::get_secret(service) {
            Ok(_) => {}
            Err(e) => {
                let msg = e.to_string();
                if msg.contains("denied") || msg.contains("-25293") || msg.contains("locked") {
                    keychain_accessible = false;
                    break;
                }
                missing.push(service.to_string());
            }
        }
    }

    SecretStatus {
        all_present: missing.is_empty() && keychain_accessible,
        missing,
        keychain_accessible,
    }
}

/// Inject secrets from Keychain into Docker containers and start the stack.
///
/// Flow (per ART-14 §13.1):
/// 1. Read all 8 secrets from Keychain
/// 2. Write temporary .env file (mode 0600)
/// 3. Run docker compose up -d with --env-file
/// 4. Wait for containers to read env
/// 5. Securely delete temp .env (overwrite + unlink)
/// 6. Verify containers healthy
#[tauri::command]
pub async fn inject_secrets_and_start(
    state: State<'_, AppState>,
) -> Result<InjectionResult, String> {
    // Step 1: Read all secrets
    let mut env_lines = Vec::new();
    for (service, env_var) in ALL_SECRETS {
        match KeychainManager::get_secret(service) {
            Ok(value) => {
                env_lines.push(format!("{env_var}={value}"));
            }
            Err(e) => {
                let msg = e.to_string();
                if msg.contains("denied") || msg.contains("locked") || msg.contains("-25293") {
                    return Err(
                        "Keychain is locked. Unlock your Mac to start EkamCore services."
                            .to_string(),
                    );
                }
                return Err(format!(
                    "Secret missing: {service}. Run the setup wizard first."
                ));
            }
        }
    }

    // Step 2: Write temp .env file (mode 0600)
    let env_path = state.app_data_dir.join("temp-secrets.env");
    write_secure_env_file(&env_path, &env_lines)?;

    // Step 3: docker compose up with env file
    let compose_dir = find_compose_dir()?;
    let up_result = Command::new("docker")
        .args([
            "compose",
            "--env-file",
            &env_path.to_string_lossy(),
            "up",
            "-d",
        ])
        .current_dir(&compose_dir)
        .output()
        .map_err(|e| format!("docker compose failed: {e}"))?;

    // Step 4: Brief wait for containers to read env
    std::thread::sleep(std::time::Duration::from_secs(5));

    // Step 5: Securely delete temp file
    secure_delete(&env_path);

    if !up_result.status.success() {
        let stderr = String::from_utf8_lossy(&up_result.stderr);
        return Ok(InjectionResult {
            success: false,
            message: format!("docker compose up failed: {stderr}"),
            containers_healthy: false,
        });
    }

    // Step 6: Quick health check
    let healthy = check_api_health().await;

    Ok(InjectionResult {
        success: true,
        message: "Secrets injected and services started.".to_string(),
        containers_healthy: healthy,
    })
}

/// Reset all secrets — regenerate and store new ones in Keychain.
/// WARNING: This requires re-initializing all containers.
#[tauri::command]
pub fn regenerate_all_secrets() -> Result<String, String> {
    let mut regenerated = Vec::new();

    // Simple hex secrets (6 of 8)
    let simple = &[
        services::POSTGRESQL,
        services::REDIS,
        services::QDRANT,
        services::DATA_ENCRYPTION,
        services::FACE_EMBED_KEY,
        services::PAPERLESS_SECRET,
    ];

    for service in simple {
        let secret = KeychainManager::generate_random_secret(32);
        KeychainManager::set_secret(service, &secret)
            .map_err(|e| format!("Failed to store {service}: {e}"))?;
        regenerated.push(service.to_string());
    }

    // JWT keypair via openssl
    let (priv_pem, pub_pem) = generate_rsa_keypair()?;
    KeychainManager::set_secret(services::JWT_PRIVATE, &priv_pem)
        .map_err(|e| format!("Failed to store JWT private key: {e}"))?;
    KeychainManager::set_secret(services::JWT_PUBLIC, &pub_pem)
        .map_err(|e| format!("Failed to store JWT public key: {e}"))?;
    regenerated.push(services::JWT_PRIVATE.to_string());
    regenerated.push(services::JWT_PUBLIC.to_string());

    tracing::info!("secrets_regenerated: count={}", regenerated.len());
    Ok(format!(
        "Regenerated {} secrets. Restart all services to apply.",
        regenerated.len()
    ))
}

/// Reset the setup state — removes setup-state.json (requires re-running wizard).
#[tauri::command]
pub fn reset_setup(state: State<'_, AppState>) -> Result<(), String> {
    let setup_path = state.app_data_dir.join("setup-state.json");
    if setup_path.exists() {
        std::fs::remove_file(&setup_path)
            .map_err(|e| format!("Failed to remove setup state: {e}"))?;
    }
    tracing::info!("setup_state_reset");
    Ok(())
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/// Write .env lines to a file with mode 0600 (owner read/write only).
fn write_secure_env_file(path: &PathBuf, lines: &[String]) -> Result<(), String> {
    use std::os::unix::fs::OpenOptionsExt;

    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .mode(0o600)
        .open(path)
        .map_err(|e| format!("Failed to create .env file: {e}"))?;

    for line in lines {
        writeln!(file, "{line}")
            .map_err(|e| format!("Failed to write .env: {e}"))?;
    }

    Ok(())
}

/// Securely delete a file: overwrite with zeros, then unlink.
fn secure_delete(path: &PathBuf) {
    if let Ok(metadata) = std::fs::metadata(path) {
        let size = metadata.len() as usize;
        if size > 0 {
            if let Ok(mut file) = std::fs::OpenOptions::new().write(true).open(path) {
                let zeros = vec![0u8; size];
                let _ = file.write_all(&zeros);
                let _ = file.sync_all();
            }
        }
    }
    let _ = std::fs::remove_file(path);
}

fn find_compose_dir() -> Result<String, String> {
    if let Ok(dir) = std::env::var("EKAMCORE_COMPOSE_DIR") {
        if std::path::Path::new(&dir)
            .join("docker-compose.yml")
            .exists()
        {
            return Ok(dir);
        }
    }

    let manifest = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
    if manifest.join("docker-compose.yml").exists() {
        return Ok(manifest.to_string_lossy().to_string());
    }

    Err("Cannot find docker-compose.yml".to_string())
}

async fn check_api_health() -> bool {
    Command::new("curl")
        .args([
            "-sf",
            "--max-time",
            "5",
            "http://localhost:8420/health",
        ])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn generate_rsa_keypair() -> Result<(String, String), String> {
    let priv_output = Command::new("openssl")
        .args([
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
        ])
        .output()
        .map_err(|e| format!("openssl genpkey failed: {e}"))?;

    if !priv_output.status.success() {
        return Err(format!(
            "openssl genpkey failed: {}",
            String::from_utf8_lossy(&priv_output.stderr)
        ));
    }

    let private_pem =
        String::from_utf8(priv_output.stdout).map_err(|e| format!("Invalid UTF-8: {e}"))?;

    let pub_output = Command::new("openssl")
        .args(["pkey", "-pubout"])
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .and_then(|mut child| {
            if let Some(ref mut stdin) = child.stdin {
                stdin.write_all(private_pem.as_bytes())?;
            }
            child.wait_with_output()
        })
        .map_err(|e| format!("openssl pkey failed: {e}"))?;

    if !pub_output.status.success() {
        return Err(format!(
            "openssl pkey -pubout failed: {}",
            String::from_utf8_lossy(&pub_output.stderr)
        ));
    }

    let public_pem =
        String::from_utf8(pub_output.stdout).map_err(|e| format!("Invalid UTF-8: {e}"))?;

    Ok((private_pem, public_pem))
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_secrets_defined() {
        assert_eq!(ALL_SECRETS.len(), 8);
        for (service, env_var) in ALL_SECRETS {
            assert!(!service.is_empty());
            assert!(!env_var.is_empty());
            assert!(service.starts_with("EkamCore-"));
        }
    }

    #[test]
    fn env_vars_uppercase() {
        for (_, env_var) in ALL_SECRETS {
            assert_eq!(*env_var, env_var.to_uppercase(), "Env var should be uppercase: {env_var}");
        }
    }

    #[test]
    fn secret_status_serializable() {
        let status = SecretStatus {
            all_present: false,
            missing: vec!["EkamCore-Redis".to_string()],
            keychain_accessible: true,
        };
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"all_present\":false"));
        assert!(json.contains("EkamCore-Redis"));
    }

    #[test]
    fn injection_result_serializable() {
        let result = InjectionResult {
            success: true,
            message: "OK".to_string(),
            containers_healthy: true,
        };
        let json = serde_json::to_string(&result).unwrap();
        assert!(json.contains("\"success\":true"));
        assert!(json.contains("\"containers_healthy\":true"));
    }

    #[test]
    fn secure_delete_handles_missing_file() {
        let path = PathBuf::from("/tmp/ekamcore-test-nonexistent-file-12345.env");
        // Should not panic
        secure_delete(&path);
    }

    #[test]
    fn secure_delete_overwrites_and_removes() {
        let path = PathBuf::from("/tmp/ekamcore-test-secret-delete.env");
        std::fs::write(&path, "SECRET=value123").unwrap();
        assert!(path.exists());

        secure_delete(&path);
        assert!(!path.exists());
    }

    #[test]
    fn write_secure_env_file_creates_with_correct_mode() {
        let path = PathBuf::from("/tmp/ekamcore-test-env-mode.env");
        let lines = vec!["KEY=value".to_string()];
        write_secure_env_file(&path, &lines).unwrap();

        // Verify file exists and has correct permissions
        use std::os::unix::fs::MetadataExt;
        let meta = std::fs::metadata(&path).unwrap();
        assert_eq!(meta.mode() & 0o777, 0o600);

        // Cleanup
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn find_compose_dir_from_manifest() {
        let manifest = env!("CARGO_MANIFEST_DIR");
        let candidate = std::path::Path::new(manifest).join("../../..");
        // Just verify the path resolution doesn't panic
        assert!(candidate.to_string_lossy().len() > 1);
    }
}
