//! Shared labels, tones and dated attention rules. No observation is refreshed here.
use crate::model::{Job, Transfer};

const STALE_AFTER: f64 = 300.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tone {
    Active,
    Success,
    Warning,
    Error,
    Muted,
}

pub fn tone(state: &str) -> Tone {
    match state.to_ascii_uppercase().as_str() {
        "RUNNING" | "PREPARING" | "CONFIGURING" | "COMPLETING" | "RESIZING" => Tone::Active,
        "COMPLETED" | "READY" | "PUBLISHED" | "DUPLICATE" => Tone::Success,
        "FAILED"
        | "TIMEOUT"
        | "CANCELLED"
        | "NODE_FAIL"
        | "OUT_OF_MEMORY"
        | "BOOT_FAIL"
        | "DEADLINE"
        | "PREEMPTED"
        | "LAUNCHFAILED"
        | "PUBLICATION_UNKNOWN" => Tone::Error,
        "PENDING"
        | "SUBMITTED"
        | "SUSPENDED"
        | "REQUEUED"
        | "REQUEUE_FED"
        | "REQUEUE_HOLD"
        | "COMPLETED_UNVERIFIED"
        | "RATE_LIMITED"
        | "PUBLISHING" => Tone::Warning,
        _ => Tone::Muted,
    }
}

pub fn job_state(state: &str) -> &'static str {
    match state {
        "RUNNING" => "En cours",
        "PENDING" => "En attente",
        "SUBMITTED" => "Soumis",
        "CONFIGURING" => "Préparation",
        "COMPLETING" => "Finalisation",
        "RESIZING" => "Redimensionnement",
        "SUSPENDED" => "Suspendu",
        "REQUEUED" | "REQUEUE_FED" | "REQUEUE_HOLD" => "Remis en file",
        "COMPLETED" => "Terminé",
        "FAILED" => "Échec",
        "TIMEOUT" => "Délai dépassé",
        "CANCELLED" => "Annulé",
        "NODE_FAIL" => "Nœud perdu",
        "OUT_OF_MEMORY" => "Mémoire dépassée",
        "BOOT_FAIL" => "Démarrage échoué",
        "DEADLINE" => "Date limite",
        "PREEMPTED" => "Préempté",
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

pub fn job_active(state: &str) -> bool {
    matches!(
        state,
        "RUNNING"
            | "PENDING"
            | "SUBMITTED"
            | "CONFIGURING"
            | "COMPLETING"
            | "SUSPENDED"
            | "RESIZING"
            | "REQUEUED"
            | "REQUEUE_FED"
            | "REQUEUE_HOLD"
    )
}

pub fn observation_old(timestamp: Option<f64>, at: f64) -> bool {
    timestamp.is_none_or(|time| {
        !time.is_finite() || time <= 0.0 || time > at + 5.0 || at - time > STALE_AFTER
    })
}

pub fn job_attention(job: &Job, at: f64) -> Option<&'static str> {
    if tone(&job.state) == Tone::Error {
        Some(job_state(&job.state))
    } else if job.state == "COMPLETED" && !job.result_validated {
        Some("Résultat à vérifier")
    } else if job_active(&job.state) && observation_old(job.observed_at, at) {
        Some("Observation ancienne ou absente")
    } else {
        None
    }
}

pub fn transfer_attention(transfer: &Transfer, at: f64) -> Option<&'static str> {
    if tone(&transfer.state) == Tone::Error {
        Some(transfer_state(&transfer.state))
    } else if matches!(
        transfer.state.as_str(),
        "completed" | "completed_unverified"
    ) && !transfer.result_validated
    {
        Some("Copie à vérifier")
    } else if matches!(transfer.state.as_str(), "running" | "preparing")
        && observation_old(transfer.observed_at, at)
    {
        Some("Observation ancienne ou absente")
    } else {
        None
    }
}

pub fn priority(state: &str, needs_attention: bool) -> u8 {
    if tone(state) == Tone::Error {
        0
    } else if needs_attention {
        1
    } else if matches!(tone(state), Tone::Active | Tone::Warning) {
        2
    } else {
        3
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Validation {
    Verified,
    Check,
    Pending,
    Absent,
}

impl Validation {
    pub fn label(self) -> &'static str {
        match self {
            Self::Verified => "Vérifié",
            Self::Check => "À vérifier",
            Self::Pending => "À venir",
            Self::Absent => "Non validé",
        }
    }

    pub fn tone(self) -> Tone {
        match self {
            Self::Verified => Tone::Success,
            Self::Check => Tone::Warning,
            _ => Tone::Muted,
        }
    }
}

pub fn job_validation(job: &Job) -> Validation {
    if job.result_validated {
        Validation::Verified
    } else if job.state == "COMPLETED" {
        Validation::Check
    } else if job_active(&job.state) {
        Validation::Pending
    } else {
        Validation::Absent
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn failures_share_the_same_tone_and_attention() {
        for state in [
            "NODE_FAIL",
            "OUT_OF_MEMORY",
            "FAILED",
            "TIMEOUT",
            "BOOT_FAIL",
            "PREEMPTED",
        ] {
            let job = Job {
                state: state.into(),
                ..Job::default()
            };
            assert_eq!(tone(state), Tone::Error);
            assert!(job_attention(&job, 1000.0).is_some());
            assert_ne!(job_state(state), "Inconnu");
        }
    }

    #[test]
    fn completed_is_independent_of_validation_and_stale_active_records_need_attention() {
        let mut job = Job {
            state: "COMPLETED".into(),
            ..Job::default()
        };
        assert_eq!(job_validation(&job), Validation::Check);
        job.result_validated = true;
        assert_eq!(job_validation(&job), Validation::Verified);
        assert!(job_attention(&job, 1000.0).is_none());
        let mut transfer = Transfer {
            state: "completed".into(),
            ..Transfer::default()
        };
        assert_eq!(
            transfer_attention(&transfer, 1000.0),
            Some("Copie à vérifier")
        );
        transfer.result_validated = true;
        assert!(transfer_attention(&transfer, 1000.0).is_none());
        transfer.state = "running".into();
        transfer.observed_at = Some(600.0);
        assert!(transfer_attention(&transfer, 1000.0).is_some());
        transfer.observed_at = Some(900.0);
        assert!(transfer_attention(&transfer, 1000.0).is_none());
        transfer.state = "prepared".into();
        transfer.observed_at = None;
        assert!(transfer_attention(&transfer, 1000.0).is_none());
    }
}
