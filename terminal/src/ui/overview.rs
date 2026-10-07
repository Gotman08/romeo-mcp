//! Prioritize interrupted calculations and evidence requiring inspection.
use super::{block, line, paragraph, scrollable, state_style, ACCENT, MUTED};
use crate::{
    app::{App, Overlay},
    model::{age, clean, now, report_state},
};
use ratatui::{
    layout::{Constraint, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

fn attention(app: &App) -> (Vec<Line<'static>>, usize) {
    let mut lines = Vec::new();
    let mut count = 0;
    for job in &app.data.jobs {
        if matches!(
            job.state.as_str(),
            "FAILED" | "TIMEOUT" | "CANCELLED" | "NODE_FAIL" | "OUT_OF_MEMORY"
        ) {
            count += 1;
            lines.push(Line::from(vec![
                Span::raw(format!("{}  {}  ", clean(&job.id), clean(&job.name))),
                Span::styled(clean(&job.state), state_style(&job.state)),
            ]));
            if let Some(checkpoint) = &job.checkpoint {
                lines.push(Line::from(format!(
                    "  Checkpoint {} · étape {} · {}",
                    checkpoint.generation,
                    checkpoint.step,
                    if checkpoint.integrity_verified {
                        "intégrité observée"
                    } else {
                        "à vérifier"
                    }
                )));
            }
        } else if job.state == "COMPLETED" && !job.result_validated {
            count += 1;
            lines.push(Line::from(format!(
                "{}  {} · résultat à valider",
                clean(&job.id),
                clean(&job.name)
            )));
        } else if matches!(job.state.as_str(), "RUNNING" | "PENDING")
            && job.observed_at.is_none_or(|time| now() - time > 300.0)
        {
            count += 1;
            lines.push(Line::from(format!(
                "{} · observation ancienne ou absente",
                clean(&job.id)
            )));
        }
    }
    for transfer in &app.data.transfers {
        if matches!(
            transfer.state.as_str(),
            "failed" | "cancelled" | "launchFailed"
        ) {
            count += 1;
            lines.push(Line::from(format!(
                "Copie {} · {}",
                clean(&transfer.name),
                clean(&transfer.state)
            )));
        }
    }
    for report in &app.data.reports.items {
        if matches!(report.state.as_str(), "failed" | "publication_unknown") {
            count += 1;
            lines.push(Line::from(format!(
                "Rapport · {} · {}",
                clean(&report.summary),
                report_state(&report.state)
            )));
        }
    }
    if let Some(error) = &app.error {
        count += 1;
        lines.push(Line::from(clean(error)));
    }
    (lines, count)
}

pub(super) fn draw(frame: &mut Frame, area: Rect, app: &mut App) {
    let active = app
        .data
        .jobs
        .iter()
        .filter(|job| matches!(job.state.as_str(), "RUNNING" | "PENDING"))
        .count();
    let (alert, count) = attention(app);
    let header_height = if area.width >= 80 { 3 } else { 1 };
    let parts =
        Layout::vertical([Constraint::Length(header_height), Constraint::Min(1)]).split(area);
    if area.width >= 80 {
        let cards = Layout::horizontal([Constraint::Percentage(25); 4]).split(parts[0]);
        for (index, (name, value)) in [
            ("Jobs chargés", app.data.jobs.len()),
            ("En cours / attente", active),
            ("Transferts", app.data.transfers.len()),
            ("À vérifier", count),
        ]
        .into_iter()
        .enumerate()
        {
            frame.render_widget(
                Paragraph::new(value.to_string())
                    .style(Style::default().fg(ACCENT))
                    .block(block(name)),
                cards[index],
            );
        }
    } else {
        frame.render_widget(
            Paragraph::new(format!(
                " {} jobs · {active} actifs · {} copies · {} alertes",
                app.data.jobs.len(),
                app.data.transfers.len(),
                count
            ))
            .style(Style::default().fg(ACCENT)),
            parts[0],
        );
    }
    let rows = content(app, alert);
    if app.overlay == Overlay::None {
        scrollable(frame, parts[1], " À examiner · ↑↓ défiler ", rows, app);
    } else {
        paragraph(frame, parts[1], " À examiner ", rows);
    }
}

pub(super) fn lines(app: &App) -> Vec<Line<'static>> {
    content(app, attention(app).0)
}

fn content(app: &App, mut rows: Vec<Line<'static>>) -> Vec<Line<'static>> {
    if rows.is_empty() {
        rows.push(Line::from("Aucune alerte dans les observations chargées."));
    }
    rows.extend([
        Line::from(""),
        Line::from("Activité récente").style(Style::default().fg(MUTED)),
    ]);
    for job in app.data.jobs.iter().take(4) {
        rows.push(Line::from(vec![
            Span::raw(format!("{}  {}  ", clean(&job.id), clean(&job.name))),
            Span::styled(clean(&job.state), state_style(&job.state)),
            Span::styled(
                format!(" · trace {}", age(job.observed_at)),
                Style::default().fg(MUTED),
            ),
        ]));
    }
    rows.push(Line::from(""));
    rows.push(line(
        "Profil / MCP",
        format!(
            "{} / {}",
            clean(&app.data.runtime.profile),
            clean(&app.data.runtime.version)
        ),
    ));
    rows.push(line(
        "Configuration",
        if app.data.runtime.configured {
            "renseignée"
        } else {
            "absente"
        },
    ));
    rows.push(line(
        "Registre",
        if app.data.runtime.registry_present {
            "présent"
        } else {
            "aucun"
        },
    ));
    rows.push(
        Line::from("2 : Jobs · 3 : Transferts · 5 : Rapports").style(Style::default().fg(MUTED)),
    );
    rows
}
