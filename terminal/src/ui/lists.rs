//! Adaptive record tables, independent filters and optional inline details.
use super::{block, details, fit, paragraph, state_style, ACCENT, MUTED, SELECTED};
use crate::{
    app::{App, View},
    model::{age, clean, report_state, transfer_state},
};
use ratatui::{
    layout::{Constraint, Layout, Rect},
    style::{Modifier, Style},
    text::Line,
    widgets::{Cell, Paragraph, Row, Table, Wrap},
    Frame,
};

pub(super) fn draw(frame: &mut Frame, area: Rect, app: &mut App) {
    let filtered: String = if app.query().is_empty() {
        "Filtre : tous · / rechercher".into()
    } else {
        format!(
            "Filtre : {}{} · Échap effacer",
            clean(app.query()),
            if app.editing { "_" } else { "" }
        )
    };
    let top = Layout::vertical([
        Constraint::Length(if app.view == View::Reports { 2 } else { 1 }),
        Constraint::Min(1),
    ])
    .split(area);
    let mut filters = vec![Line::from(fit(&filtered, area.width as usize))];
    if app.view == View::Reports {
        filters.push(Line::from(format!(
            "Envoi automatique : {}",
            match app.data.reports.automatic_enabled {
                Some(true) => "activé",
                Some(false) => "désactivé",
                None => "inconnu",
            }
        )));
    }
    frame.render_widget(
        Paragraph::new(filters).style(Style::default().fg(ACCENT)),
        top[0],
    );
    let compact = area.width < 85 || area.height < 20;
    let (table_area, detail_area) = if compact {
        (top[1], None)
    } else if area.width >= 128 {
        let panels = Layout::horizontal([Constraint::Percentage(60), Constraint::Percentage(40)])
            .split(top[1]);
        (panels[0], Some(panels[1]))
    } else {
        let length = match app.view {
            View::Jobs => app.jobs().len(),
            View::Transfers => app.transfers().len(),
            _ => app.reports().len(),
        };
        let height = (length as u16 + 3)
            .min(top[1].height.saturating_sub(10))
            .max(5);
        let panels =
            Layout::vertical([Constraint::Length(height), Constraint::Min(1)]).split(top[1]);
        (panels[0], Some(panels[1]))
    };
    let narrow = table_area.width < 70;
    let (rows, header, widths, title, count, total) = match app.view {
        View::Jobs => {
            let jobs = app.jobs();
            let count = jobs.len();
            let rows = jobs
                .into_iter()
                .map(|job| {
                    if narrow {
                        Row::new(vec![
                            Cell::from(clean(&job.id)),
                            Cell::from(fit(
                                &job.name,
                                table_area.width.saturating_sub(25) as usize,
                            )),
                            Cell::from(clean(&job.state)).style(state_style(&job.state)),
                        ])
                    } else {
                        Row::new(vec![
                            Cell::from(clean(&job.id)),
                            Cell::from(clean(&job.name)),
                            Cell::from(clean(&job.state)).style(state_style(&job.state)),
                            Cell::from(age(job.observed_at)),
                        ])
                    }
                })
                .collect::<Vec<_>>();
            let header = if narrow {
                vec!["Job", "Nom", "État"]
            } else {
                vec!["Job", "Nom", "État Slurm", "Trace"]
            };
            let widths = if narrow {
                vec![
                    Constraint::Length(8),
                    Constraint::Min(8),
                    Constraint::Length(12),
                ]
            } else {
                vec![
                    Constraint::Length(9),
                    Constraint::Min(12),
                    Constraint::Length(18),
                    Constraint::Length(10),
                ]
            };
            (rows, header, widths, "Jobs", count, app.data.jobs.len())
        }
        View::Transfers => {
            let transfers = app.transfers();
            let count = transfers.len();
            let rows = transfers
                .into_iter()
                .map(|transfer| {
                    let name = transfer
                        .name
                        .rsplit(['/', '\\'])
                        .next()
                        .unwrap_or(&transfer.name);
                    let percent = transfer
                        .progress
                        .as_ref()
                        .and_then(|progress| progress.percent())
                        .map(|percent| format!("{percent} %"))
                        .unwrap_or_else(|| "—".into());
                    if narrow {
                        Row::new(vec![
                            Cell::from(fit(name, table_area.width.saturating_sub(22) as usize)),
                            Cell::from(transfer_state(&transfer.state))
                                .style(state_style(&transfer.state)),
                            Cell::from(percent),
                        ])
                    } else {
                        Row::new(vec![
                            Cell::from(if transfer.direction == "upload" {
                                "→ ROMEO"
                            } else {
                                "← ROMEO"
                            }),
                            Cell::from(clean(name)),
                            Cell::from(transfer_state(&transfer.state))
                                .style(state_style(&transfer.state)),
                            Cell::from(percent),
                            Cell::from(age(transfer.observed_at)),
                        ])
                    }
                })
                .collect::<Vec<_>>();
            let header = if narrow {
                vec!["Fichier", "État", "Copie"]
            } else {
                vec!["Sens", "Fichier", "État", "Copie", "Trace"]
            };
            let widths = if narrow {
                vec![
                    Constraint::Min(12),
                    Constraint::Length(12),
                    Constraint::Length(6),
                ]
            } else {
                vec![
                    Constraint::Length(8),
                    Constraint::Min(12),
                    Constraint::Length(20),
                    Constraint::Length(6),
                    Constraint::Length(8),
                ]
            };
            (
                rows,
                header,
                widths,
                "Transferts",
                count,
                app.data.transfers.len(),
            )
        }
        _ => {
            let reports = app.reports();
            let count = reports.len();
            let rows = reports
                .into_iter()
                .map(|report| {
                    Row::new(vec![
                        Cell::from(clean(&report.summary)),
                        Cell::from(report_state(&report.state)).style(state_style(&report.state)),
                        Cell::from(
                            report
                                .issue_number
                                .map(|number| format!("#{number}"))
                                .unwrap_or_else(|| "—".into()),
                        ),
                    ])
                })
                .collect::<Vec<_>>();
            (
                rows,
                vec!["Résumé", "Publication", "Issue"],
                vec![
                    Constraint::Min(14),
                    Constraint::Length(if narrow { 12 } else { 18 }),
                    Constraint::Length(7),
                ],
                "Rapports",
                count,
                app.data.reports.items.len(),
            )
        }
    };
    app.page_rows = table_area.height.saturating_sub(3).max(1) as usize;
    let selected = match app.view {
        View::Jobs => app.jobs_table.selected(),
        View::Transfers => app.transfers_table.selected(),
        _ => app.reports_table.selected(),
    };
    let position = if count == 0 {
        0
    } else {
        selected.unwrap_or(0).min(count - 1) + 1
    };
    let title = format!(" {title} {count}/{total} · ligne {position}/{count} ");
    let table = Table::new(rows, widths)
        .header(Row::new(header).style(Style::default().fg(MUTED)))
        .block(block(title))
        .row_highlight_style(Style::default().bg(SELECTED).add_modifier(Modifier::BOLD))
        .highlight_symbol("› ");
    match app.view {
        View::Jobs => frame.render_stateful_widget(table, table_area, &mut app.jobs_table),
        View::Transfers => {
            frame.render_stateful_widget(table, table_area, &mut app.transfers_table)
        }
        _ => frame.render_stateful_widget(table, table_area, &mut app.reports_table),
    };
    if let Some(area) = detail_area {
        paragraph(
            frame,
            area,
            " Détail · Entrée pour tout lire ",
            details::lines(app),
        );
    } else if count == 0 {
        let inner = Rect::new(
            table_area.x + 1,
            table_area.y + 2,
            table_area.width.saturating_sub(2),
            table_area.height.saturating_sub(3),
        );
        frame.render_widget(
            Paragraph::new(details::lines(app)).wrap(Wrap { trim: false }),
            inner,
        );
    }
}
