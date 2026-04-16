//! macOS Keychain access for EkamCore secrets (S15-001 / ART-14 §13).
//!
//! Wraps `security-framework` to provide typed get/set/delete for each
//! EkamCore service secret. Generates crypto-grade random strings and
//! RSA keypairs for first-run provisioning.

use rand::Rng;
use security_framework::passwords::{
    delete_generic_password, get_generic_password, set_generic_password,
};

const ACCOUNT: &str = "EkamCore";

/// Known service names per ART-14 §13.
pub mod services {
    pub const POSTGRESQL: &str = "EkamCore-PostgreSQL";
    pub const REDIS: &str = "EkamCore-Redis";
    pub const QDRANT: &str = "EkamCore-Qdrant";
    pub const JWT_PRIVATE: &str = "EkamCore-JWT-Private";
    pub const JWT_PUBLIC: &str = "EkamCore-JWT-Public";
    pub const DATA_ENCRYPTION: &str = "EkamCore-DataEncryption";
    pub const FACE_EMBED_KEY: &str = "EkamCore-FaceEmbedKey";
    pub const PAPERLESS_SECRET: &str = "EkamCore-PaperlessSecret";
}

#[derive(Debug, thiserror::Error)]
pub enum KeychainError {
    #[error("Keychain item not found: {0}")]
    NotFound(String),
    #[error("Keychain access denied: {0}")]
    AccessDenied(String),
    #[error("Keychain error: {0}")]
    Other(String),
}

impl serde::Serialize for KeychainError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

pub struct KeychainManager;

impl KeychainManager {
    /// Retrieve a secret from the macOS Keychain.
    pub fn get_secret(service: &str) -> Result<String, KeychainError> {
        let bytes = get_generic_password(service, ACCOUNT)
            .map_err(|e| {
                let msg = e.to_string();
                if msg.contains("not found") || msg.contains("-25300") {
                    KeychainError::NotFound(service.to_string())
                } else {
                    KeychainError::Other(msg)
                }
            })?;
        String::from_utf8(bytes.to_vec())
            .map_err(|e| KeychainError::Other(e.to_string()))
    }

    /// Store a secret in the macOS Keychain. Overwrites if exists.
    pub fn set_secret(service: &str, value: &str) -> Result<(), KeychainError> {
        // Delete first to handle "already exists" (overwrite).
        let _ = delete_generic_password(service, ACCOUNT);
        set_generic_password(service, ACCOUNT, value.as_bytes())
            .map_err(|e| KeychainError::Other(e.to_string()))
    }

    /// Delete a secret from the macOS Keychain.
    pub fn delete_secret(service: &str) -> Result<(), KeychainError> {
        delete_generic_password(service, ACCOUNT)
            .map_err(|e| KeychainError::Other(e.to_string()))
    }

    /// Check if a secret exists without retrieving it.
    pub fn has_secret(service: &str) -> bool {
        get_generic_password(service, ACCOUNT).is_ok()
    }

    /// Generate a crypto-grade random secret string of ``length`` bytes,
    /// hex-encoded (so the output is 2 * length characters).
    pub fn generate_random_secret(length: usize) -> String {
        let mut rng = rand::thread_rng();
        let bytes: Vec<u8> = (0..length).map(|_| rng.gen()).collect();
        hex::encode(bytes)
    }
}

// hex encoding without an extra crate — inline implementation.
mod hex {
    const HEX_CHARS: &[u8; 16] = b"0123456789abcdef";

    pub fn encode(bytes: Vec<u8>) -> String {
        let mut s = String::with_capacity(bytes.len() * 2);
        for b in bytes {
            s.push(HEX_CHARS[(b >> 4) as usize] as char);
            s.push(HEX_CHARS[(b & 0x0f) as usize] as char);
        }
        s
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generate_random_secret_correct_length() {
        let secret = KeychainManager::generate_random_secret(32);
        assert_eq!(secret.len(), 64); // 32 bytes * 2 hex chars
        assert!(secret.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn hex_encode_roundtrip() {
        let bytes = vec![0xDE, 0xAD, 0xBE, 0xEF];
        assert_eq!(hex::encode(bytes), "deadbeef");
    }
}
