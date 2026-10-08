//! Versioned snapshot contract. No SSH, filesystem or MCP calls belong here.
pub use crate::status::{report_state, transfer_state};
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
    #[serde(default)]
    pub request_id: u64,
    #[serde(default)]
    pub coverage: Coverage,
    #[serde(default)]
    pub attention: Vec<Alert>,
    #[serde(default)]
    pub recent_jobs: Vec<Job>,
    #[serde(default)]
    pub active_jobs: usize,
    #[serde(default)]
    pub partial: bool,
    #[serde(default)]
    pub workspace: Workspace,
    #[serde(default)]
    pub sessions: Vec<Session>,
    #[serde(default)]
    pub notifications: Vec<Notification>,
}
#[derive(Clone, Debug, Deserialize, Default)]
pub struct Notification {
    pub key: String,
    pub job_id: String,
    pub message: String,
    pub observed_at: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Coverage {
    pub jobs: Page,
    pub transfers: Page,
    pub reports: Page,
    pub alerts: Page,
    #[serde(default)]
    pub sessions: Page,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Workspace {
    #[serde(default)]
    pub job_id: String,
    #[serde(default)]
    pub links: Vec<Artifact>,
    #[serde(default)]
    pub links_total: usize,
    #[serde(default)]
    pub events: Vec<HistoryEvent>,
    #[serde(default)]
    pub members: Vec<Member>,
    #[serde(default)]
    pub efficiency: Efficiency,
    #[serde(default)]
    pub recovery: Recovery,
    pub logs: Option<Logs>,
    #[serde(default)]
    pub group: Group,
}
#[derive(Clone, Debug, Deserialize, Default)]
pub struct Artifact {
    pub kind: String,
    pub id: String,
    pub name: String,
    pub state: String,
    pub basis: String,
}
#[derive(Clone, Debug, Deserialize, Default)]
pub struct HistoryEvent {
    pub kind: String,
    pub state: String,
    pub observed_at: Option<f64>,
    pub source: String,
    pub generation: Option<u64>,
    pub resume_observed: bool,
}
#[derive(Clone, Debug, Deserialize, Default)]
pub struct Member {
    pub id: String,
    pub name: String,
    pub state: String,
}
#[derive(Clone, Debug, Deserialize, Default)]
pub struct Group {
    pub array_parent: Option<String>,
    pub parent_plan: Option<String>,
    #[serde(default)]
    pub array_spec: String,
    #[serde(default)]
    pub dependencies: String,
    pub remaining_dependencies: Option<String>,
    pub dependencies_observed_at: Option<f64>,
    #[serde(default)]
    pub dependencies_source: String,
}
#[derive(Clone, Debug, Deserialize, Default)]
pub struct Efficiency {
    pub alloc_cpus: Option<f64>,
    pub alloc_gpus: Option<f64>,
    pub elapsed_seconds: Option<f64>,
    pub cpu_seconds_used: Option<f64>,
    pub cpu_seconds_reserved: Option<f64>,
    pub cpu_efficiency_pct: Option<f64>,
    pub max_rss_mb: Option<f64>,
    pub req_mem_mb: Option<f64>,
    pub mem_efficiency_pct: Option<f64>,
    pub gpu_utilization_pct: Option<f64>,
    pub observed_at: Option<f64>,
    #[serde(default)]
    pub source: String,
}
#[derive(Clone, Debug, Deserialize, Default)]
pub struct Recovery {
    pub complete: Option<bool>,
    pub integrity: Option<bool>,
    pub compatible: Option<bool>,
    pub independent_backup: Option<bool>,
    pub resume_observed: Option<bool>,
    pub step: Option<u64>,
    pub generation: Option<u64>,
    pub world_size: Option<u64>,
    pub observed_at: Option<f64>,
    #[serde(default)]
    pub source: String,
}
#[derive(Clone, Debug, Deserialize, Default)]
pub struct Logs {
    pub content: String,
    pub observed_at: Option<f64>,
    pub stream: String,
    pub truncated: bool,
    pub source: String,
}
#[derive(Clone, Debug, Deserialize, Default)]
pub struct Session {
    pub id: String,
    pub name: String,
    pub job_id: String,
    pub state: String,
    pub slurm_state: String,
    pub ready: Option<bool>,
    pub created_at: Option<f64>,
    pub observed_at: Option<f64>,
    pub expires_at: Option<f64>,
    pub source: String,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Page {
    pub page: usize,
    pub pages: usize,
    pub loaded: usize,
    pub matched: usize,
    pub total: usize,
    pub page_size: usize,
}

impl Page {
    fn valid(&self, loaded: usize) -> bool {
        (1..=100).contains(&self.page_size)
            && self.loaded == loaded
            && self.loaded <= self.page_size
            && self.total >= self.matched
            && self.matched >= self.loaded
            && self.pages == self.matched.div_ceil(self.page_size).max(1)
            && self.page < self.pages
    }
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Alert {
    pub kind: String,
    pub id: String,
    pub name: String,
    pub state: String,
    pub reason: String,
    pub observed_at: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Resources {
    #[serde(default)]
    pub requested: Allocation,
    #[serde(default)]
    pub observed: Allocation,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Allocation {
    pub nodes: Option<u64>,
    pub tasks: Option<u64>,
    pub tasks_per_node: Option<u64>,
    pub cpus_per_task: Option<u64>,
    pub omp_threads: Option<u64>,
    pub gpus: Option<u64>,
    pub gpus_per_node: Option<u64>,
    pub gpus_per_task: Option<u64>,
    pub time_limit_seconds: Option<u64>,
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
    #[serde(default)]
    pub resources: Resources,
}

#[derive(Clone, Debug, Deserialize, Default)]
pub struct Transfer {
    pub id: String,
    pub name: String,
    pub direction: String,
    pub state: String,
    pub phase: String,
    pub observed_at: Option<f64>,
    #[serde(default)]
    pub created_at: Option<f64>,
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
        if !matches!(value.schema, 2 | 3)
            || value.jobs.len() > 100
            || value.transfers.len() > 100
            || value.reports.items.len() > 100
            || value.warnings.len() > 100
            || value.attention.len() > 100
            || value.recent_jobs.len() > 4
            || value.sessions.len() > 100
            || value.notifications.len() > 50
            || value.workspace.links.len() > 100
            || value.workspace.events.len() > 48
            || value.workspace.members.len() > 100
            || value
                .workspace
                .logs
                .as_ref()
                .is_some_and(|logs| logs.content.len() > 32000)
            || (value.schema == 3
                && (!value.coverage.jobs.valid(value.jobs.len())
                    || !value.coverage.transfers.valid(value.transfers.len())
                    || !value.coverage.reports.valid(value.reports.items.len())
                    || !value.coverage.alerts.valid(value.attention.len())
                    || ((value.coverage.sessions.page_size != 0 || !value.sessions.is_empty())
                        && !value.coverage.sessions.valid(value.sessions.len()))
                    || value.active_jobs > value.coverage.jobs.total))
            || !value.generated_at.is_finite()
            || value.generated_at <= 0.0
        {
            return Err("Format du relevé incompatible avec cette interface.".to_owned());
        }
        Ok(value)
    }
}

pub fn timestamp_exact(timestamp: Option<f64>) -> String {
    timestamp
        .filter(|time| time.is_finite() && *time > 0.0 && *time < i64::MAX as f64)
        .and_then(|time| chrono::DateTime::from_timestamp(time as i64, 0))
        .map(|time| time.format("%Y-%m-%d %H:%M:%S UTC").to_string())
        .unwrap_or_else(|| "non observé ou date invalide".into())
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reject_incompatible_schema_and_non_json() {
        assert!(Snapshot::parse("not-json").is_err());
        let mut value = serde_json::json!({"schema":4, "generated_at":1.0, "demo":false,
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
