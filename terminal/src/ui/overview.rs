//! Prioritize interrupted calculations and evidence requiring inspection.
use super::{block, line, paragraph, scrollable, state_style, tone_style, ACCENT, MUTED};
use crate::{
    app::{App, Overlay},
    model::{age, clean, now, report_state},
    status::{job_active, job_attention, job_state, tone, transfer_attention, Tone},
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
    let at = now();
    for job in &app.data.jobs {
        if let Some(reason) = job_attention(job, at) {
            count += 1;
            lines.push(Line::from(vec![
                Span::raw(format!("{}  {}  ", clean(&job.id), clean(&job.name))),
                Span::styled(
                    reason,
                    tone_style(if tone(&job.state) == Tone::Error {
                        Tone::Error
                    } else {
                        Tone::Warning
                    }),
                ),
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
        }
    }
    for transfer in &app.data.transfers {
        if let Some(reason) = transfer_attention(transfer, at) {
            count += 1;
            lines.push(Line::from(vec![
                Span::raw(format!("Copie {} · ", clean(&transfer.name))),
                Span::styled(
                    reason,
                    tone_style(if tone(&transfer.state) == Tone::Error {
                        Tone::Error
                    } else {
                        Tone::Warning
                    }),
                ),
            ]));
        }
    }
    for report in &app.data.reports.items {
        if matches!(report.state.as_str(), "failed" | "publication_unknown") {
            count += 1;
            lines.push(Line::from(vec![
                Span::raw(format!("Rapport · {} · ", clean(&report.summary))),
                Span::styled(report_state(&report.state), state_style(&report.state)),
            ]));
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
        .filter(|job| job_active(&job.state))
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
    for job in app.recent_jobs().into_iter().take(4) {
        rows.push(Line::from(vec![
            Span::raw(format!("{}  {}  ", clean(&job.id), clean(&job.name))),
            Span::styled(job_state(&job.state), state_style(&job.state)),
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{app::View, model::Transfer};

    #[test]
    fn transfer_attention_counts_records_once_and_keeps_validated_history_quiet() {
        let mut app = App::new(View::Overview);
        app.data.transfers = vec![
            Transfer {
                state: "completed".into(),
                name: "unverified".into(),
                ..Transfer::default()
            },
            Transfer {
                state: "completed_unverified".into(),
                name: "unverified2".into(),
                ..Transfer::default()
            },
            Transfer {
                state: "running".into(),
                name: "old".into(),
                observed_at: Some(now() - 600.0),
                ..Transfer::default()
            },
            Transfer {
                state: "completed".into(),
                name: "verified".into(),
                result_validated: true,
                ..Transfer::default()
            },
        ];
        let (lines, count) = attention(&app);
        assert_eq!(count, 3);
        let text = lines
            .iter()
            .map(ToString::to_string)
            .collect::<Vec<_>>()
            .join("\n");
        assert!(text.contains("Copie à vérifier"));
        assert!(text.contains("Observation ancienne"));
    }
}
