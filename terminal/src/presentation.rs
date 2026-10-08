//! Projection for sharing; raw observations remain available to selection and IO.
use crate::model::Snapshot;

pub fn project(data: &Snapshot) -> Snapshot {
    let mut masked = data.clone();
    for job in masked.jobs.iter_mut().chain(masked.recent_jobs.iter_mut()) {
        job.name = "[nom masqué]".into();
        job.partition = "[masquée]".into();
    }
    for transfer in &mut masked.transfers {
        transfer.name = "[fichier masqué]".into();
        transfer.local_path = "[chemin masqué]".into();
        transfer.remote_path = "[chemin masqué]".into();
    }
    for report in &mut masked.reports.items {
        report.summary = "[résumé masqué]".into();
        report.issue_url.clear();
    }
    for alert in &mut masked.attention {
        alert.name = "[nom masqué]".into();
    }
    for artifact in &mut masked.workspace.links {
        artifact.name = "[nom masqué]".into();
    }
    for member in &mut masked.workspace.members {
        member.name = "[nom masqué]".into();
    }
    if let Some(logs) = &mut masked.workspace.logs {
        logs.content = "[journal masqué]".into();
    }
    masked.warnings = masked
        .warnings
        .iter()
        .map(|_| "Avertissement de lecture · contenu masqué".into())
        .collect();
    masked
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn projection_masks_paths_names_logs_and_preserves_proofs() {
        let mut data = Snapshot::default();
        data.jobs.push(crate::model::Job {
            id: "42".into(),
            name: "confidential calculation".into(),
            ..Default::default()
        });
        data.transfers.push(crate::model::Transfer {
            local_path: "C:/private/project".into(),
            result_validated: true,
            ..Default::default()
        });
        let masked = project(&data);
        assert_eq!(masked.jobs[0].id, "42");
        assert!(!masked.jobs[0].name.contains("confidential"));
        assert!(!masked.transfers[0].local_path.contains("private"));
        assert!(masked.transfers[0].result_validated);
        assert_eq!(data.jobs[0].name, "confidential calculation");
    }
}
