//! Selected records grouped by state, time, recovery and validation evidence.
use super::{line, progress, state_style, tone_style, ACCENT};
use crate::{
    app::{App, View},
    model::{age, bytes, present, report_state, transfer_state},
    status::{job_state, job_validation, Tone},
};
use ratatui::{
    style::{Modifier, Style},
    text::{Line, Span},
};

fn section(title: &'static str) -> Line<'static> {
    Line::styled(
        title,
        Style::default().fg(ACCENT).add_modifier(Modifier::BOLD),
    )
}

fn marked(label: &str, value: impl AsRef<str>, style: Style) -> Line<'static> {
    let mut output = line(label, value);
    if let Some(span) = output.spans.last_mut() {
        span.style = style;
    }
    output
}

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
    let mut lines = vec![
        section("État"),
        line("Job", &job.id),
        line("Nom", &job.name),
        marked(
            "Calcul",
            format!("{} ({})", job_state(&job.state), present(&job.state)),
            state_style(&job.state),
        ),
        line("Partition", &job.partition),
        Line::from(""),
        section("Temps"),
        line("Durée écoulée", present(&job.elapsed)),
        line("Temps restant", present(&job.remaining)),
        line("Observé il y a", age(job.observed_at)),
        line("Soumis il y a", age(job.submitted_at)),
        Line::from(""),
        section("Checkpoint"),
    ];
    if let Some(checkpoint) = &job.checkpoint {
        lines.extend([
            line(
                "Sauvegarde",
                format!(
                    "Génération {} · étape {}",
                    checkpoint.generation, checkpoint.step
                ),
            ),
            line("Rangs associés", checkpoint.world_size.to_string()),
            marked(
                "Intégrité",
                if checkpoint.integrity_verified {
                    "Vérifiée dans l'observation"
                } else {
                    "Non vérifiée"
                },
                tone_style(if checkpoint.integrity_verified {
                    Tone::Success
                } else {
                    Tone::Warning
                }),
            ),
            line(
                "Reprise",
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
        lines.push(Line::from("Aucune observation enregistrée"));
    }
    lines.extend([
        Line::from(""),
        section("Validation"),
        marked(
            "Résultat",
            job_validation(job).label(),
            tone_style(job_validation(job).tone()),
        ),
        line("Code de sortie", present(&job.exit_code)),
    ]);
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
        section("État"),
        line("Transfert", &transfer.id),
        marked(
            "Copie",
            format!(
                "{} ({})",
                transfer_state(&transfer.state),
                present(&transfer.state)
            ),
            state_style(&transfer.state),
        ),
        line("Phase", present(&transfer.phase)),
        Line::from(""),
        section("Progression"),
    ];
    if let Some(progress) = transfer
        .progress
        .as_ref()
        .filter(|progress| progress.percent().is_some())
    {
        lines.push(progress::bar(Some(progress), 32));
        lines.push(line(
            "Octets traités",
            if let Some(total) = progress.bytes_total {
                format!(
                    "{} / {}",
                    bytes(progress.bytes_transferred as f64),
                    bytes(total as f64)
                )
            } else {
                format!("{} (rsync)", bytes(progress.bytes_transferred as f64))
            },
        ));
        lines.extend([
            Line::from(""),
            section("Temps"),
            line(
                "Débit utile",
                progress
                    .bytes_per_second
                    .map(|speed| format!("{}/s", bytes(speed)))
                    .unwrap_or_else(|| "—".into()),
            ),
            line(
                "Temps estimé",
                progress
                    .eta_seconds
                    .map(|seconds| format!("{seconds:.0} s"))
                    .unwrap_or_else(|| "—".into()),
            ),
            line("Mesure datant de", age(progress.observed_at)),
        ]);
    } else {
        lines.extend([
            Line::from("Non mesurée par ce transport"),
            Line::from(""),
            section("Temps"),
        ]);
    }
    lines.extend([
        line("Observé il y a", age(transfer.observed_at)),
        Line::from(""),
        section("Validation"),
        marked(
            "Intégrité",
            if transfer.result_validated {
                "Copie vérifiée dans le résultat enregistré"
            } else {
                "Validation de copie absente"
            },
            tone_style(if transfer.result_validated {
                Tone::Success
            } else {
                Tone::Warning
            }),
        ),
        line(
            "Annulation",
            if transfer.cancel_requested {
                "Demandée ; arrêt à observer"
            } else {
                "—"
            },
        ),
        Line::from(""),
        section("Chemins"),
        line("Local", &transfer.local_path),
        line("Distant", &transfer.remote_path),
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
        section("État"),
        line("Rapport", &report.id),
        line("Résumé", &report.summary),
        line("Catégorie", &report.category),
        marked(
            "Publication",
            report_state(&report.state),
            state_style(&report.state),
        ),
        line("Occurrences", report.occurrences.to_string()),
        Line::from(""),
        section("Temps"),
        line("Dernière preuve", age(report.observed_at)),
        Line::from(""),
        section("Validation"),
        marked(
            "Publication relue",
            if report.result_validated {
                "Vérifiée à cette date"
            } else {
                "Aucune publication vérifiée"
            },
            tone_style(if report.result_validated {
                Tone::Success
            } else {
                Tone::Muted
            }),
        ),
        Line::from(""),
        section("Issue GitHub"),
        line(
            "Issue",
            report
                .issue_number
                .map(|number| format!("#{number}"))
                .unwrap_or_else(|| "—".into()),
        ),
        line("Lien", present(&report.issue_url)),
    ];
    if report.retry_after > crate::model::now() {
        lines.push(Line::from(vec![Span::raw(format!(
            "Nouvel envoi après : {:.0} s",
            report.retry_after - crate::model::now()
        ))]));
    }
    lines
}
