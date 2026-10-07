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
    pub reports: Reports,
    pub warnings: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Runtime {
    pub version: String,
    pub profile: String,
    pub configured: bool,
    pub registry_present: bool,
}

#[derive(Clone, Debug, Deserialize, Default)]
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
    pub checkpoint: Option<Checkpoint>,
}

#[derive(Clone, Debug, Deserialize, Default)]
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
    pub progress: Option<Progress>,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Checkpoint {
    pub generation: u64,
    pub step: u64,
    pub world_size: u64,
    pub integrity_verified: bool,
    pub resume_validated: bool,
    pub signal_verified: bool,
    pub observed_at: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Progress {
    pub bytes_transferred: u64,
    pub bytes_total: Option<u64>,
    pub percent_reported: Option<u64>,
    pub bytes_per_second: Option<f64>,
    pub eta_seconds: Option<f64>,
    pub observed_at: Option<f64>,
}

impl Progress {
    pub fn percent(&self) -> Option<u64> {
        if let Some(total) = self.bytes_total {
            if total == 0 || self.bytes_transferred > total {
                return None;
            }
            return Some(((self.bytes_transferred as u128 * 100) / total as u128) as u64);
        }
        self.percent_reported.filter(|percent| *percent <= 100)
    }
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Reports {
    pub automatic_enabled: Option<bool>,
    pub items: Vec<Report>,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Report {
    pub id: String,
    pub summary: String,
    pub state: String,
    pub category: String,
    pub issue_url: String,
    pub issue_number: Option<u64>,
    pub observed_at: Option<f64>,
    pub occurrences: u64,
    pub result_validated: bool,
    pub retry_after: f64,
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
        if value.schema != 2
            || value.jobs.len() > 100
            || value.transfers.len() > 100
            || value.reports.items.len() > 100
            || value.warnings.len() > 100
            || !value.generated_at.is_finite()
            || value.generated_at <= 0.0
        {
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

pub fn present(value: &str) -> String {
    if value.trim().is_empty() {
        "—".to_owned()
    } else {
        clean(value)
    }
}

pub fn bytes(value: f64) -> String {
    if !value.is_finite() || value < 0.0 {
        return "—".to_owned();
    }
    let mut amount = value;
    let units = ["o", "Kio", "Mio", "Gio", "Tio"];
    let mut index = 0;
    while amount >= 1024.0 && index < units.len() - 1 {
        amount /= 1024.0;
        index += 1;
    }
    if index == 0 {
        format!("{amount:.0} {}", units[index])
    } else {
        format!("{amount:.1} {}", units[index])
    }
}

pub fn report_state(state: &str) -> &'static str {
    match state {
        "local_only" => "Local",
        "publishing" => "Envoi à vérifier",
        "published" => "Publié",
        "duplicate" => "Déjà publié",
        "failed" => "Échec",
        "publication_unknown" => "Envoi incertain",
        "rate_limited" => "En attente",
        _ => "Inconnu",
    }
}

pub fn transfer_state(state: &str) -> &'static str {
    match state {
        "prepared" => "Préparé",
        "preparing" => "Préparation",
        "running" => "En cours",
        "completed" => "Terminé",
        "completed_unverified" => "À vérifier",
        "cancelled" => "Annulé",
        "failed" | "launchFailed" => "Échec",
        _ => "Inconnu",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reject_incompatible_schema_and_non_json() {
        assert!(Snapshot::parse("not-json").is_err());
        let mut value = serde_json::json!({"schema":3, "generated_at":1.0, "demo":false,
            "runtime":{"version":"1", "profile":"full", "configured":false,"registry_present":false},
            "jobs":[], "transfers":[], "updates":{"version":"1", "next_version":"1",
            "latest_version":"", "checked_at":null, "automatic_enabled":false,
            "restart_required":false, "state":"idle", "phase":"", "observed_at":null,
            "update_available":null}, "reports":{"automatic_enabled":false,"items":[]}, "warnings":[]});
        assert!(Snapshot::parse(&value.to_string()).is_err());
        value["schema"] = 2.into();
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

    #[test]
    fn progress_needs_a_measured_valid_total() {
        let mut progress = Progress {
            bytes_total: Some(120),
            bytes_transferred: 48,
            ..Progress::default()
        };
        assert_eq!(progress.percent(), Some(40));
        progress.bytes_total = Some(0);
        assert_eq!(progress.percent(), None);
        progress.bytes_total = Some(12);
        assert_eq!(progress.percent(), None);
        progress.bytes_total = None;
        progress.percent_reported = Some(40);
        assert_eq!(progress.percent(), Some(40));
        progress.percent_reported = Some(101);
        assert_eq!(progress.percent(), None);
        assert_eq!(present(""), "—");
        assert_eq!(bytes(f64::NAN), "—");
    }
}
