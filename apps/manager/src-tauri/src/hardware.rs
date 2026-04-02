//! Step 1 — Hardware Check
//!
//! Verifies: Apple Silicon, ≥16 GB RAM, macOS ≥ 13.0.

use serde::Serialize;

const MIN_RAM_GB: f64 = 16.0;
const MIN_MACOS_MAJOR: u32 = 13;

#[derive(Debug, Serialize)]
pub struct HardwareCheckResult {
    pub is_apple_silicon: bool,
    pub ram_gb: f64,
    pub ram_ok: bool,
    pub macos_version: String,
    pub macos_ok: bool,
    pub all_passed: bool,
}

/// Run all hardware checks and return combined result.
#[tauri::command]
pub fn check_hardware() -> HardwareCheckResult {
    let is_apple_silicon = check_apple_silicon();
    let ram_bytes = read_ram_bytes();
    let ram_gb = ram_bytes as f64 / (1024.0 * 1024.0 * 1024.0);
    let ram_ok = ram_gb >= MIN_RAM_GB;
    let macos_version = read_macos_version();
    let macos_ok = parse_major_version(&macos_version) >= MIN_MACOS_MAJOR;
    let all_passed = is_apple_silicon && ram_ok && macos_ok;

    HardwareCheckResult {
        is_apple_silicon,
        ram_gb,
        ram_ok,
        macos_version,
        macos_ok,
        all_passed,
    }
}

fn check_apple_silicon() -> bool {
    std::process::Command::new("sysctl")
        .args(["-n", "hw.optional.arm64"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim() == "1")
        .unwrap_or(false)
}

fn read_ram_bytes() -> u64 {
    std::process::Command::new("sysctl")
        .args(["-n", "hw.memsize"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .and_then(|s| s.trim().parse::<u64>().ok())
        .unwrap_or(0)
}

fn read_macos_version() -> String {
    std::process::Command::new("sw_vers")
        .args(["-productVersion"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|| "0.0.0".to_string())
}

fn parse_major_version(version: &str) -> u32 {
    version
        .split('.')
        .next()
        .and_then(|s| s.parse().ok())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_major_version_standard() {
        assert_eq!(parse_major_version("13.5.1"), 13);
        assert_eq!(parse_major_version("14.0"), 14);
        assert_eq!(parse_major_version("15"), 15);
        assert_eq!(parse_major_version("0.0.0"), 0);
    }

    #[test]
    fn check_hardware_returns_result() {
        // Smoke test: just verify it runs without panic.
        let r = check_hardware();
        assert!(r.ram_gb >= 0.0);
    }
}
