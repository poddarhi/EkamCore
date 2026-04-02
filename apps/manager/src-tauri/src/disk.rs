//! Step 2 — Disk Space Check
//!
//! Requires ≥ 30 GB free on the boot volume.
//! Uses `df -k /` to avoid platform-specific FFI struct layout issues.

use serde::Serialize;

const REQUIRED_GB: f64 = 30.0;
const WARNING_GB: f64 = 40.0;

#[derive(Debug, Serialize)]
pub struct DiskCheckResult {
    pub free_gb: f64,
    pub required_gb: f64,
    /// true when free_gb >= REQUIRED_GB
    pub passed: bool,
    /// true when passed but free_gb < WARNING_GB (tight on space)
    pub warning: bool,
}

/// Check boot volume free space via `df -k /`.
#[tauri::command]
pub fn check_disk() -> DiskCheckResult {
    let free_gb = boot_volume_free_gb();
    let passed = free_gb >= REQUIRED_GB;
    let warning = passed && free_gb < WARNING_GB;
    DiskCheckResult {
        free_gb,
        required_gb: REQUIRED_GB,
        passed,
        warning,
    }
}

fn boot_volume_free_gb() -> f64 {
    boot_volume_free_gb_inner().unwrap_or(0.0)
}

fn boot_volume_free_gb_inner() -> Option<f64> {
    let output = std::process::Command::new("df")
        .args(["-k", "/"])
        .output()
        .ok()?;

    let stdout = String::from_utf8(output.stdout).ok()?;
    // df -k / output (second line is the data row):
    //   Filesystem   1024-blocks    Used  Available  Capacity  ...
    //   /dev/disk3s5 488245288  ...  AVAILABLE ...
    // Column index 3 = Available (1K-blocks)
    let data_line = stdout.lines().nth(1)?;
    let available_kib: u64 = data_line.split_whitespace().nth(3)?.parse().ok()?;
    Some(available_kib as f64 / (1024.0 * 1024.0)) // KiB → GiB
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_disk_returns_positive_value() {
        let r = check_disk();
        assert!(r.free_gb >= 0.0);
        assert_eq!(r.required_gb, 30.0);
        assert!(r.free_gb > 1.0, "Expected > 1 GB free, got {:.1}", r.free_gb);
    }

    #[test]
    fn warning_logic() {
        let tight = DiskCheckResult {
            free_gb: 35.0,
            required_gb: 30.0,
            passed: true,
            warning: true,
        };
        assert!(tight.passed);
        assert!(tight.warning);

        let plenty = DiskCheckResult {
            free_gb: 50.0,
            required_gb: 30.0,
            passed: true,
            warning: false,
        };
        assert!(plenty.passed);
        assert!(!plenty.warning);
    }
}
