//! Dossiers, recovery proofs, resource measurements and recorded services.
use super::{line, state_style, tone_style, ACCENT, MUTED};
use crate::{
    app::{App, View},
    model::{present, timestamp_exact},
    status::Tone,
};
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::Line,
    widgets::{Cell, Row, Table},
    Frame,
};

fn section(title: &str) -> Line<'static> {
    Line::styled(
        title.to_owned(),
        Style::default().fg(ACCENT).add_modifier(Modifier::BOLD),
    )
}
fn measured(value: Option<f64>, unit: &str) -> String {
    value
        .filter(|value| value.is_finite() && *value >= 0.0)
        .map(|value| format!("{value:.1} {unit}"))
        .unwrap_or("inconnu".into())
}
fn proof(label: &str, value: Option<bool>) -> Line<'static> {
    let (text, tone) = match value {
        Some(true) => ("Vérifié", Tone::Success),
        Some(false) => ("Non établi", Tone::Warning),
        None => ("Inconnu", Tone::Muted),
    };
    Line::from(vec![
        ratatui::text::Span::raw(format!("{label} : ")),
        ratatui::text::Span::styled(text, tone_style(tone)),
    ])
}

pub fn lines(app: &App) -> Vec<Line<'static>> {
    let Some(job) = app.selected_job() else {
        return vec![Line::from("Sélectionner un job du registre local.")];
    };
    let workspace = &app.data.workspace;
    let mut lines = vec![section(&format!(
        "Calcul {} · {}{}",
        job.id,
        job.name,
        if app.favorites.contains(&job.id) {
            " · favori"
        } else {
            ""
        }
    ))];
    if let Some(note) = app.notes.get(&job.id) {
        lines.push(line(
            "Note locale",
            if app.anonymized { "[masquée]" } else { note },
        ));
    }
    if workspace.job_id != job.id {
        lines.push(Line::from("Chargement du dossier sélectionné…"));
        return lines;
    }
    if app.view == View::Recovery || app.view == View::Dossier {
        lines.push(section("Reprise · preuves enregistrées"));
        let recovery = &workspace.recovery;
        lines.extend([
            proof("Checkpoint complet", recovery.complete),
            proof("Intégrité", recovery.integrity),
            proof("Programme et données compatibles", recovery.compatible),
            proof("Copie indépendante", recovery.independent_backup),
            proof("Reprise effectivement observée", recovery.resume_observed),
            line(
                "Génération / étape / rangs",
                format!(
                    "{} / {} / {}",
                    recovery
                        .generation
                        .map(|v| v.to_string())
                        .unwrap_or("—".into()),
                    recovery.step.map(|v| v.to_string()).unwrap_or("—".into()),
                    recovery
                        .world_size
                        .map(|v| v.to_string())
                        .unwrap_or("—".into())
                ),
            ),
            line("Preuve datée", timestamp_exact(recovery.observed_at)),
            line("Source", present(&recovery.source)),
            Line::from(""),
        ]);
    }
    if app.view == View::Dossier {
        let efficiency = &workspace.efficiency;
        lines.push(section("Efficacité · allocations et mesures séparées"));
        super::details::allocation(
            &mut lines,
            "Demandées · script enregistré",
            &job.resources.requested,
        );
        lines.push(line(
            "Durée demandée",
            measured(
                job.resources.requested.time_limit_seconds.map(|v| v as f64),
                "s",
            ),
        ));
        lines.extend([
            line("CPU alloués", measured(efficiency.alloc_cpus, "CPU")),
            line("GPU alloués", measured(efficiency.alloc_gpus, "GPU")),
            line("Durée mesurée", measured(efficiency.elapsed_seconds, "s")),
            line(
                "CPU utilisé / réservé",
                format!(
                    "{} / {}",
                    measured(efficiency.cpu_seconds_used, "s CPU"),
                    measured(efficiency.cpu_seconds_reserved, "s CPU")
                ),
            ),
            line(
                "Efficacité CPU",
                measured(efficiency.cpu_efficiency_pct, "%"),
            ),
            line(
                "Pic mémoire / demande",
                format!(
                    "{} / {}",
                    measured(efficiency.max_rss_mb, "Mio"),
                    measured(efficiency.req_mem_mb, "Mio")
                ),
            ),
            line(
                "Efficacité mémoire",
                measured(efficiency.mem_efficiency_pct, "%"),
            ),
            line(
                "Utilisation GPU mesurée",
                measured(efficiency.gpu_utilization_pct, "%"),
            ),
            line("Mesure datée", timestamp_exact(efficiency.observed_at)),
            line("Source", present(&efficiency.source)),
            Line::from(""),
        ]);
        lines.push(section("Artefacts associés"));
        if workspace.links_total > workspace.links.len() {
            lines.push(line(
                "Associations affichées",
                format!(
                    "{} / {} au moins · liste bornée",
                    workspace.links.len(),
                    workspace.links_total
                ),
            ));
        }
        if workspace.links.is_empty() {
            lines.push(Line::from("Aucune association enregistrée."));
        }
        for artifact in &workspace.links {
            lines.push(line(
                &format!("{} {}", artifact.kind, artifact.id),
                format!(
                    "{} · {} · {}",
                    artifact.name, artifact.state, artifact.basis
                ),
            ));
        }
        lines.push(Line::from(""));
        lines.push(section("Chronologie · nouveaux événements en premier"));
        if workspace.events.is_empty() {
            lines.push(Line::from("Aucun événement historique enregistré."));
        }
        for event in &workspace.events {
            lines.push(Line::from(format!(
                "{} · {} · {} · {}",
                timestamp_exact(event.observed_at),
                event.kind,
                event.state,
                event.source
            )));
            if let Some(generation) = event.generation {
                lines.push(line(
                    "  Checkpoint",
                    format!(
                        "génération {generation} · reprise {}",
                        if event.resume_observed {
                            "observée"
                        } else {
                            "non établie"
                        }
                    ),
                ));
            }
        }
        lines.push(Line::from(""));
        lines.extend(log_lines(app));
    }
    if matches!(app.view, View::Dossier | View::Groups) {
        lines.push(section("Groupes et dépendances enregistrés"));
        lines.extend([
            line(
                "Tableau parent",
                workspace.group.array_parent.as_deref().unwrap_or("—"),
            ),
            line(
                "Plan de chaîne",
                workspace.group.parent_plan.as_deref().unwrap_or("—"),
            ),
            line("Indices demandés", present(&workspace.group.array_spec)),
            line("Dépendances", present(&workspace.group.dependencies)),
            line(
                "Restantes au relevé",
                match workspace.group.remaining_dependencies.as_deref() {
                    Some("") => "Aucune".into(),
                    Some(value) => crate::model::clean(value),
                    None => "Inconnues".into(),
                },
            ),
            line(
                "Relevé des dépendances",
                timestamp_exact(workspace.group.dependencies_observed_at),
            ),
            line("Source", present(&workspace.group.dependencies_source)),
        ]);
        let failed = workspace
            .members
            .iter()
            .filter(|member| crate::status::tone(&member.state) == Tone::Error)
            .count();
        let active = workspace
            .members
            .iter()
            .filter(|member| crate::status::job_active(&member.state))
            .count();
        lines.push(line(
            "Membres enregistrés",
            format!(
                "{} · actifs {active} · échecs {failed} · inventaire partiel possible",
                workspace.members.len()
            ),
        ));
        lines.push(Line::from(
            "Les dépendances déclarées et les dépendances restantes observées sont distinctes.",
        ));
        for member in &workspace.members {
            lines.push(Line::styled(
                format!(
                    "{} · {} · {}",
                    member.id,
                    member.name,
                    crate::status::job_state(&member.state)
                ),
                state_style(&member.state),
            ));
        }
        if workspace.members.is_empty() {
            lines.push(Line::from("Aucun sous-job observé dans le registre."));
        }
    }
    lines
}

pub fn log_lines(app: &App) -> Vec<Line<'static>> {
    let mut lines = vec![section("Dernières lignes enregistrées")];
    match &app.data.workspace.logs {
        Some(logs) => {
            lines.push(line(
                "Relevé",
                format!(
                    "{} · {} · {}{}",
                    timestamp_exact(logs.observed_at),
                    logs.stream,
                    logs.source,
                    if logs.truncated {
                        " · extrait borné"
                    } else {
                        ""
                    }
                ),
            ));
            if app.anonymized {
                lines.push(Line::from("[contenu des journaux masqué en présentation]"));
            } else {
                lines.extend(
                    logs.content
                        .lines()
                        .map(|line| Line::from(crate::model::clean(line))),
                );
            }
        }
        None => lines.push(Line::from(
            "Aucun journal sauvegardé. a : lire les journaux sur ROMEO.",
        )),
    }
    lines
}

pub fn sessions(frame: &mut Frame, area: Rect, app: &mut App) {
    use ratatui::{
        layout::{Constraint, Layout},
        widgets::Paragraph,
    };
    let parts = Layout::vertical([Constraint::Length(1), Constraint::Min(1)]).split(area);
    let filter = if app.query().is_empty() {
        "Filtre : tous · / rechercher".into()
    } else {
        format!(
            "Filtre : {}{} · Échap effacer",
            if app.anonymized {
                "[masqué]".into()
            } else {
                crate::model::clean(app.query())
            },
            if app.editing { "_" } else { "" }
        )
    };
    frame.render_widget(
        Paragraph::new(filter).style(Style::default().fg(ACCENT)),
        parts[0],
    );
    let area = parts[1];
    let compact = area.width < 70;
    let rows: Vec<Row> = app
        .data
        .sessions
        .iter()
        .map(|item| {
            let readiness = Cell::from(match item.ready {
                Some(true) => "Observée",
                Some(false) => "Non établie",
                None => "Inconnue",
            });
            let mut cells = vec![Cell::from(crate::model::clean(&item.name))];
            if !compact {
                cells.push(Cell::from(super::fit(&item.job_id, app.id_width as usize)));
            }
            cells.extend([
                Cell::from(crate::model::clean(&item.state)).style(state_style(&item.state)),
                readiness,
            ]);
            if !compact {
                cells.push(Cell::from(
                    item.expires_at
                        .map(|value| timestamp_exact(Some(value)))
                        .unwrap_or_else(|| "Inconnue".into()),
                ));
            }
            Row::new(cells)
        })
        .collect();
    let page = &app.data.coverage.sessions;
    let title = format!(
        " Sessions {}/{} · p.{}/{} ",
        rows.len(),
        page.total,
        page.page + 1,
        page.pages
    );
    let (header, widths) = if compact {
        (
            vec!["Service", "État", "Disponibilité"],
            vec![
                Constraint::Min(10),
                Constraint::Length(12),
                Constraint::Length(13),
            ],
        )
    } else {
        (
            vec![
                "Service",
                "Job",
                "État",
                "Disponibilité",
                "Expiration au relevé",
            ],
            vec![
                Constraint::Min(10),
                Constraint::Length(app.id_width),
                Constraint::Length(12),
                Constraint::Length(13),
                Constraint::Min(10),
            ],
        )
    };
    app.table_area = Some(area);
    app.page_rows = area.height.saturating_sub(3).max(1) as usize;
    frame.render_stateful_widget(
        Table::new(rows, widths)
            .header(Row::new(header).style(Style::default().fg(MUTED)))
            .block(super::block(title))
            .highlight_symbol("› ")
            .row_highlight_style(Style::default().bg(super::SELECTED)),
        area,
        &mut app.sessions_table,
    );
}

pub fn session_lines(app: &App) -> Vec<Line<'static>> {
    let Some(item) = app
        .data
        .sessions
        .get(app.sessions_table.selected().unwrap_or(0))
    else {
        return vec![Line::from("Aucun service/session enregistré.")];
    };
    vec![
        line("Service", &item.name),
        line("Identifiant", &item.id),
        line("Allocation", &item.job_id),
        line("État enregistré", &item.state),
        line("Slurm enregistré", &item.slurm_state),
        proof("Disponibilité observée", item.ready),
        line("Création", timestamp_exact(item.created_at)),
        line("Observation", timestamp_exact(item.observed_at)),
        line("Expiration", timestamp_exact(item.expires_at)),
        line("Source", present(&item.source)),
    ]
}
