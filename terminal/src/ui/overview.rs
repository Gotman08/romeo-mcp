//! Prioritize interrupted calculations and evidence requiring inspection.
use super::{block, line, paragraph, scrollable, state_style, tone_style, ACCENT, MUTED};
use crate::{
    app::{App, Overlay},
    model::{age, clean, now, report_state},
    preferences::Panel,
    status::{job_active, job_attention, job_state, tone, transfer_attention, Tone},
};
use ratatui::{
    layout::{Constraint, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Cell, Paragraph, Row, Table},
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
    if app.data.schema == 3 {
        draw_global(frame, area, app);
        return;
    }
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
    if app.data.schema == 3 {
        let mut lines = vec![Line::from(format!(
            "Alertes : {}/{} · page {}/{}",
            app.data.attention.len(),
            app.data.coverage.alerts.total,
            app.data.coverage.alerts.page + 1,
            app.data.coverage.alerts.pages
        ))];
        for alert in &app.data.attention {
            lines.push(Line::from(format!(
                "{} {} · {} · {} · observé {}",
                clean(&alert.kind),
                clean(&alert.id),
                clean(&alert.name),
                clean(&alert.reason),
                age(alert.observed_at)
            )));
        }
        return content(app, lines);
    }
    content(app, attention(app).0)
}

fn draw_global(frame: &mut Frame, area: Rect, app: &mut App) {
    let header_height = if area.width >= 80 { 3 } else { 1 };
    let parts =
        Layout::vertical([Constraint::Length(header_height), Constraint::Min(1)]).split(area);
    let page = &app.data.coverage.alerts;
    if area.width >= 80 {
        let cards = Layout::horizontal([Constraint::Percentage(25); 4]).split(parts[0]);
        for (index, (label, value)) in [
            ("Jobs du registre", app.data.coverage.jobs.total),
            ("En cours / attente", app.data.active_jobs),
            ("Transferts connus", app.data.coverage.transfers.total),
            ("À vérifier", page.total),
        ]
        .into_iter()
        .enumerate()
        {
            frame.render_widget(
                Paragraph::new(value.to_string())
                    .style(Style::default().fg(ACCENT))
                    .block(block(label)),
                cards[index],
            );
        }
    } else {
        frame.render_widget(
            Paragraph::new(format!(
                " {} jobs · {} actifs · {} copies · {} alertes",
                app.data.coverage.jobs.total,
                app.data.active_jobs,
                app.data.coverage.transfers.total,
                page.total
            )),
            parts[0],
        );
    }
    let height = (app.data.attention.len() as u16 + 3)
        .min(parts[1].height.saturating_sub(4))
        .max(3);
    let panels = Layout::vertical([Constraint::Length(height), Constraint::Min(1)]).split(parts[1]);
    app.split_visible = panels[1].height >= 3;
    app.page_rows = panels[0].height.saturating_sub(3).max(1) as usize;
    let title = format!(
        " À vérifier {}/{} · p.{}/{}{} · Entrée ouvrir ",
        page.loaded,
        page.total,
        page.page + 1,
        page.pages,
        if app.focus == Panel::List {
            " · actif"
        } else {
            ""
        }
    );
    let object_width = if area.width < 70 { 11 } else { 14 };
    let reason_width = if area.width < 70 { 17 } else { 28 };
    let rows = app.data.attention.iter().map(|alert| {
        Row::new(vec![
            Cell::from(fit_alert(
                &format!(
                    "{} {}",
                    if alert.kind == "jobs" {
                        "Job"
                    } else if alert.kind == "transfers" {
                        "Copie"
                    } else {
                        "Rapport"
                    },
                    alert.id
                ),
                object_width,
            )),
            Cell::from(fit_alert(
                &alert.name,
                panels[0]
                    .width
                    .saturating_sub((object_width + reason_width + 6) as u16)
                    as usize,
            )),
            Cell::from(fit_alert(&alert.reason, reason_width)).style(tone_style(
                if tone(&alert.state) == Tone::Error {
                    Tone::Error
                } else {
                    Tone::Warning
                },
            )),
        ])
    });
    frame.render_stateful_widget(
        Table::new(
            rows,
            [
                Constraint::Length(object_width as u16),
                Constraint::Min(8),
                Constraint::Length(reason_width as u16),
            ],
        )
        .header(Row::new(["Objet", "Nom", "À examiner"]).style(Style::default().fg(MUTED)))
        .block(block(title))
        .row_highlight_style(Style::default().bg(super::SELECTED))
        .highlight_symbol("› "),
        panels[0],
        &mut app.alerts_table,
    );
    super::scrollbar(
        frame,
        panels[0],
        app.data.attention.len(),
        app.alerts_table.offset(),
        app.page_rows,
    );
    if app.data.attention.is_empty() {
        let inner = Rect::new(
            panels[0].x + 1,
            panels[0].y + 2,
            panels[0].width.saturating_sub(2),
            panels[0].height.saturating_sub(3),
        );
        frame.render_widget(
            Paragraph::new("Aucune alerte dans les traces connues."),
            inner,
        );
    }
    let mut context = content(app, vec![]);
    // The attention table already conveys alerts; keep the second panel for context.
    if context.len() >= 2 {
        context.drain(..2);
    }
    if app.focus == Panel::Detail && app.overlay == Overlay::None {
        scrollable(
            frame,
            panels[1],
            " Résumé · actif · F6 alertes ",
            context,
            app,
        );
    } else {
        paragraph(frame, panels[1], " Résumé · F6 activer ", context);
    }
}

fn fit_alert(value: &str, width: usize) -> String {
    super::fit(value, width)
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
