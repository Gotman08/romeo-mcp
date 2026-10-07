//! Versioned snapshot contract. No SSH, filesystem or MCP calls belong here.
use serde::Deserialize;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Snapshot {
    pub schema: u8,
    pub generated_at: f64,
    pub demo: bool,
    pub runtime: Runtime,
    pub jobs: Vec<Job>,
    pub transfers: Vec<Transfer>,
    pub updates: Updates,
    pub warnings: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Runtime {
    pub version: String,
    pub profile: String,
    pub configured: bool,
    pub registry_present: bool,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Job {
    pub id: String,
    pub name: String,
    pub partition: String,
    pub state: String,
    pub submitted_at: Option<f64>,
    pub observed_at: Option<f64>,
    pub elapsed: String,
    pub remaining: String,
    pub exit_code: String,
    pub result_validated: bool,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Transfer {
    pub id: String,
    pub name: String,
    pub direction: String,
    pub state: String,
    pub phase: String,
    pub observed_at: Option<f64>,
    pub local_path: String,
    pub remote_path: String,
    pub result_validated: bool,
    pub cancel_requested: bool,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Updates {
    pub version: String,
    pub next_version: String,
    pub latest_version: String,
    pub checked_at: Option<f64>,
    pub automatic_enabled: bool,
    pub restart_required: bool,
    pub state: String,
    pub phase: String,
    pub observed_at: Option<f64>,
    pub update_available: Option<bool>,
}

impl Snapshot {
    pub fn parse(line: &str) -> Result<Self, String> {
        let value: Self = serde_json::from_str(line).map_err(|_| {
            "Relevé local illisible ; les dernières données restent affichées.".to_owned()
        })?;
        if value.schema != 1 || value.jobs.len() > 100 || value.transfers.len() > 100 {
            return Err("Format du relevé incompatible avec cette interface.".to_owned());
        }
        Ok(value)
    }
}

pub fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

pub fn age(timestamp: Option<f64>) -> String {
    let Some(time) = timestamp.filter(|time| time.is_finite() && *time > 0.0) else {
        return "non observé".to_owned();
    };
    let seconds = now() - time;
    if seconds < -5.0 {
        return "date future".to_owned();
    }
    let seconds = seconds.max(0.0) as u64;
    if seconds < 60 {
        format!("{seconds} s")
    } else if seconds < 3600 {
        format!("{} min", seconds / 60)
    } else if seconds < 86400 {
        format!("{} h", seconds / 3600)
    } else {
        format!("{} j", seconds / 86400)
    }
}

pub fn clean(value: &str) -> String {
    // Defense in depth for strings arriving through the private JSON bridge.
    value
        .chars()
        .take(240)
        .map(|c| {
            if c.is_control() || matches!(c, '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}') {
                ' '
            } else {
                c
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reject_incompatible_schema_and_non_json() {
        assert!(Snapshot::parse("not-json").is_err());
        let mut value = serde_json::json!({"schema":2, "generated_at":1.0, "demo":false,
            "runtime":{"version":"1", "profile":"full", "configured":false,"registry_present":false},
            "jobs":[], "transfers":[], "updates":{"version":"1", "next_version":"1",
            "latest_version":"", "checked_at":null, "automatic_enabled":false,
            "restart_required":false, "state":"idle", "phase":"", "observed_at":null,
            "update_available":null}, "warnings":[]});
        assert!(Snapshot::parse(&value.to_string()).is_err());
        value["schema"] = 1.into();
        assert!(Snapshot::parse(&value.to_string()).is_ok());
    }

    #[test]
    fn timestamps_and_terminal_controls_are_not_misleading() {
        assert_eq!(age(None), "non observé");
        assert_eq!(age(Some(now() + 3600.0)), "date future");
        assert_eq!(age(Some(now() - 125.0)), "2 min");
        let safe = clean("nom\u{1b}[31m\n\u{202e}");
        assert!(!safe.contains('\u{1b}'));
        assert!(!safe.contains('\u{202e}'));
    }
}
