//! Readable fields and compact historical evidence for the selected record.
use super::line;
use crate::{
    app::{App, View},
    model::{age, bytes, present, report_state, transfer_state},
};
use ratatui::text::Line;

pub fn lines(app: &App) -> Vec<Line<'static>> {
    match app.view {
        View::Overview => super::overview::lines(app),
        View::Jobs => job(app),
        View::Transfers => transfer(app),
        View::Reports => report(app),
        _ => vec![],
    }
}

fn job(app: &App) -> Vec<Line<'static>> {
    let jobs = app.jobs();
    let Some(job) = jobs.get(app.jobs_table.selected().unwrap_or(0)) else {
        return vec![Line::from(if app.data.jobs.is_empty() {
            "Aucun job local. Les soumissions du MCP alimentent ce registre."
        } else {
            "Aucun job ne correspond au filtre. Échap : effacer."
        })];
    };
    let validation = if job.result_validated {
        "Validation enregistrée"
    } else if matches!(
        job.state.as_str(),
        "RUNNING"
            | "PENDING"
            | "SUBMITTED"
            | "CONFIGURING"
            | "COMPLETING"
            | "SUSPENDED"
            | "RESIZING"
    ) {
        "À vérifier après la fin du calcul"
    } else {
        "Aucune validation de résultat enregistrée"
    };
    let mut lines = vec![
        line("Job", &job.id),
        line("Nom", &job.name),
        line("État Slurm", &job.state),
        line("Partition", &job.partition),
        line("Soumis il y a", age(job.submitted_at)),
        line("Observé il y a", age(job.observed_at)),
        line("Durée écoulée", present(&job.elapsed)),
        line("Temps restant", present(&job.remaining)),
        line("Code de sortie", present(&job.exit_code)),
        line("Résultat", validation),
    ];
    if let Some(checkpoint) = &job.checkpoint {
        lines.extend([
            Line::from(""),
            line(
                "Checkpoint",
                format!(
                    "Génération {} · étape {}",
                    checkpoint.generation, checkpoint.step
                ),
            ),
            line("Rangs associés", checkpoint.world_size.to_string()),
            line(
                "Intégrité",
                if checkpoint.integrity_verified {
                    "Vérifiée dans l'observation"
                } else {
                    "Non vérifiée"
                },
            ),
            line(
                "Reprise de l'exécution",
                if checkpoint.resume_validated {
                    "Chargement et progression observés"
                } else {
                    "À vérifier"
                },
            ),
            line(
                "Signal de sauvegarde",
                if checkpoint.signal_verified {
                    "Réception et sauvegarde observées"
                } else {
                    "Non vérifiées"
                },
            ),
            line("Preuve datant de", age(checkpoint.observed_at)),
        ]);
    } else {
        lines.push(line("Checkpoint", "Aucune observation enregistrée"));
    }
    lines
}

fn transfer(app: &App) -> Vec<Line<'static>> {
    let transfers = app.transfers();
    let Some(transfer) = transfers.get(app.transfers_table.selected().unwrap_or(0)) else {
        return vec![Line::from(if app.data.transfers.is_empty() {
            "Aucun transfert local. Les plans du MCP apparaîtront ici."
        } else {
            "Aucun transfert ne correspond au filtre. Échap : effacer."
        })];
    };
    let mut lines = vec![
        line("Transfert", &transfer.id),
        line("Local", &transfer.local_path),
        line("Distant", &transfer.remote_path),
        line(
            "État",
            format!(
                "{} ({})",
                transfer_state(&transfer.state),
                present(&transfer.state)
            ),
        ),
        line("Phase", present(&transfer.phase)),
        line("Observé il y a", age(transfer.observed_at)),
    ];
    if let Some(progress) = &transfer.progress {
        if let Some(percent) = progress.percent() {
            lines.push(line(
                "Progression",
                if let Some(total) = progress.bytes_total {
                    format!(
                        "{percent} % · {} / {}",
                        bytes(progress.bytes_transferred as f64),
                        bytes(total as f64)
                    )
                } else {
                    format!(
                        "{percent} % · {} traités (rsync)",
                        bytes(progress.bytes_transferred as f64)
                    )
                },
            ));
            lines.push(line(
                "Débit utile",
                progress
                    .bytes_per_second
                    .map(|speed| format!("{}/s", bytes(speed)))
                    .unwrap_or_else(|| "—".into()),
            ));
            lines.push(line(
                "Temps estimé",
                progress
                    .eta_seconds
                    .map(|seconds| format!("{seconds:.0} s"))
                    .unwrap_or_else(|| "—".into()),
            ));
            lines.push(line("Mesure datant de", age(progress.observed_at)));
        } else {
            lines.push(line("Progression", "Non mesurée"));
        }
    } else {
        lines.push(line("Progression", "Non mesurée par ce transport"));
    }
    lines.extend([
        line(
            "Intégrité",
            if transfer.result_validated {
                "Copie vérifiée dans le résultat enregistré"
            } else {
                "Validation de copie absente"
            },
        ),
        line(
            "Annulation",
            if transfer.cancel_requested {
                "Demandée ; arrêt à observer"
            } else {
                "—"
            },
        ),
    ]);
    lines
}

fn report(app: &App) -> Vec<Line<'static>> {
    let reports = app.reports();
    let Some(report) = reports.get(app.reports_table.selected().unwrap_or(0)) else {
        return vec![Line::from(if app.data.reports.items.is_empty() {
            "Aucun rapport local. L'assistant utilise mcp_issue_report."
        } else {
            "Aucun rapport ne correspond au filtre. Échap : effacer."
        })];
    };
    let mut lines = vec![
        line("Rapport", &report.id),
        line("Résumé", &report.summary),
        line("Catégorie", &report.category),
        line("Publication", report_state(&report.state)),
        line("Occurrences", report.occurrences.to_string()),
        line("Dernière preuve", age(report.observed_at)),
        line(
            "Issue GitHub",
            report
                .issue_number
                .map(|number| format!("#{number}"))
                .unwrap_or_else(|| "—".into()),
        ),
        line("Lien", present(&report.issue_url)),
        line(
            "Vérification",
            if report.result_validated {
                "Publication relue et vérifiée à cette date"
            } else {
                "Aucune publication vérifiée"
            },
        ),
    ];
    if report.retry_after > crate::model::now() {
        lines.push(line(
            "Nouvel envoi après",
            format!("{:.0} s", report.retry_after - crate::model::now()),
        ));
    }
    lines
}
