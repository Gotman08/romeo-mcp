//! Compact views prioritize records; rendering performs no IO.
mod details;
mod lists;
mod overlays;
mod overview;
mod progress;
mod updates;
mod workspace;

use crate::{
    app::{App, Overlay, View},
    color::Palette,
    model::{age, clean, present},
    status::{self, Tone},
};
use ratatui::{
    layout::{Constraint, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{
        Block, BorderType, Paragraph, Scrollbar, ScrollbarOrientation, ScrollbarState, Tabs, Wrap,
    },
    Frame,
};

const BACKGROUND: Color = Color::Rgb(17, 21, 27);
const TEXT: Color = Color::Rgb(216, 222, 233);
const MUTED: Color = Color::Rgb(155, 165, 180);
const ACCENT: Color = Color::Rgb(86, 182, 194);
const ERROR: Color = Color::Rgb(239, 135, 146);
const SELECTED: Color = Color::Rgb(28, 40, 52);

pub fn summary(app: &mut App) -> String {
    let original = if app.anonymized {
        let projected = crate::presentation::project(&app.data);
        Some(std::mem::replace(&mut app.data, projected))
    } else {
        None
    };
    let mut output = format!(
        "ROMEO MCP — résumé d'observations enregistrées\nRelevé local : {}\n\n",
        crate::model::timestamp_exact(Some(app.data.generated_at))
    );
    for line in details::lines(app) {
        for span in line.spans {
            output.push_str(&crate::model::clean(&span.content));
        }
        output.push('\n');
    }
    output.push_str("\nCes preuves datées ne constituent pas une interrogation du cluster.\n");
    if let Some(data) = original {
        app.data = data;
    }
    output
}

fn block(title: impl Into<String>) -> Block<'static> {
    Block::bordered()
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Rgb(70, 81, 96)))
        .title(Line::from(title.into()).style(Style::default().fg(MUTED)))
}

fn line(label: &str, value: impl AsRef<str>) -> Line<'static> {
    Line::from(vec![
        Span::styled(format!("{label} : "), Style::default().fg(MUTED)),
        Span::raw(present(value.as_ref())),
    ])
}

fn state_style(state: &str) -> Style {
    tone_style(status::tone(state))
}

fn tone_style(tone: Tone) -> Style {
    let color = match tone {
        Tone::Active => ACCENT,
        Tone::Success => Color::Rgb(152, 195, 121),
        Tone::Warning => Color::Rgb(229, 192, 123),
        Tone::Error => ERROR,
        Tone::Muted => MUTED,
    };
    Style::default().fg(color)
}

fn fit(value: &str, width: usize) -> String {
    let value = clean(value);
    if Line::from(value.as_str()).width() <= width {
        return value;
    }
    let mut result = String::new();
    let mut used = 0;
    for character in value.chars() {
        let size = Span::raw(character.to_string()).width();
        if used + size + 1 > width {
            break;
        }
        result.push(character);
        used += size;
    }
    result.push('…');
    result
}

fn paragraph(frame: &mut Frame, area: Rect, title: &str, lines: Vec<Line<'static>>) {
    frame.render_widget(
        Paragraph::new(lines)
            .block(block(title))
            .wrap(Wrap { trim: false }),
        area,
    );
}

pub fn draw(frame: &mut Frame, app: &mut App) {
    if app.anonymized {
        let projected = crate::presentation::project(&app.data);
        let original = std::mem::replace(&mut app.data, projected);
        draw_inner(frame, app);
        app.data = original;
    } else {
        draw_inner(frame, app);
    }
}
fn draw_inner(frame: &mut Frame, app: &mut App) {
    app.split_visible = false;
    app.table_area = None;
    app.detail_area = None;
    app.tab_hits.clear();
    let area = frame.area();
    frame.render_widget(
        Block::default().style(Style::default().fg(TEXT).bg(BACKGROUND)),
        area,
    );
    if area.width < 48 || area.height < 16 {
        paragraph(
            frame,
            area,
            " ROMEO ",
            vec![
                Line::from("Agrandir le terminal : 48 × 16 minimum."),
                Line::from("q : quitter"),
            ],
        );
        return;
    }
    let parts = Layout::vertical([
        Constraint::Length(2),
        Constraint::Length(3),
        Constraint::Min(1),
        Constraint::Length(2),
    ])
    .split(area);
    let reading = if app.loading {
        "lecture…"
    } else if app.error.is_some() {
        "interrompue"
    } else if app.paused {
        "pause"
    } else {
        "active"
    };
    let mode = if app.data.demo {
        "DÉMONSTRATION"
    } else {
        "HISTORIQUE LOCAL"
    };
    let status = if app.palette != Palette::Color {
        format!(
            "{} · {} · relu {} · {reading}",
            if app.data.demo { "DÉMO" } else { "LOCAL" },
            if area.width < 80 {
                match app.palette {
                    Palette::NoColorEnvironment => "mono/NO_COLOR",
                    _ => "mono/--color never",
                }
            } else {
                app.palette.description()
            },
            age(Some(app.data.generated_at))
        )
    } else if area.width < 80 {
        format!(
            "{} · local {} s · relu {} · {reading}",
            if app.data.demo { "DÉMO" } else { "LOCAL" },
            app.refresh_seconds,
            age(Some(app.data.generated_at))
        )
    } else {
        format!(
            "{mode} · relecture locale {} s · {reading} · lus il y a {}",
            app.refresh_seconds,
            age(Some(app.data.generated_at))
        )
    };
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(vec![
                Span::styled(
                    " ROMEO ",
                    Style::default().fg(ACCENT).add_modifier(Modifier::BOLD),
                ),
                Span::raw("Tableau de bord"),
                Span::styled(
                    if app.anonymized {
                        "   v0.5 · PRÉSENTATION"
                    } else {
                        "   v0.5 interne"
                    },
                    Style::default().fg(MUTED),
                ),
            ]),
            Line::from(format!(
                " {}",
                fit(&status, area.width.saturating_sub(2) as usize)
            )),
        ]),
        parts[0],
    );
    let all = [
        "1 Aperçu",
        "2 Jobs",
        "3 Copies",
        "4 MAJ",
        "5 Rapports",
        "6 Dossier",
        "7 Reprise",
        "8 Groupes",
        "9 Sessions",
    ];
    let count = if area.width < 65 {
        3
    } else if area.width < 140 {
        5
    } else {
        9
    };
    let start = app.view.index().saturating_sub(count / 2).min(9 - count);
    let titles = &all[start..start + count];
    let mut x = parts[1].x + 2;
    for (index, title) in titles.iter().enumerate() {
        let width = Line::from(*title).width() as u16 + 2;
        app.tab_hits.push((
            Rect::new(x, parts[1].y + 1, width, 1),
            View::from_index(start + index),
        ));
        x += width + 1;
    }
    frame.render_widget(
        Tabs::new(titles.iter().copied())
            .select(app.view.index() - start)
            .padding(" ", " ")
            .highlight_style(Style::default().fg(ACCENT).add_modifier(Modifier::BOLD))
            .divider(" ")
            .block(block("")),
        parts[1],
    );
    match app.view {
        View::Overview => overview::draw(frame, parts[2], app),
        View::Jobs
        | View::Transfers
        | View::Reports
        | View::Dossier
        | View::Recovery
        | View::Groups => lists::draw(frame, parts[2], app),
        View::Updates => updates::draw(frame, parts[2], app),
        View::Sessions => workspace::sessions(frame, parts[2], app),
    }
    footer(frame, parts[3], app);
    if app.overlay != Overlay::None {
        overlays::draw(frame, area, app);
    }
}

fn footer(frame: &mut Frame, area: Rect, app: &App) {
    let is_list = matches!(
        app.view,
        View::Jobs
            | View::Transfers
            | View::Reports
            | View::Dossier
            | View::Recovery
            | View::Groups
            | View::Sessions
    );
    let shortcuts = if area.width < 80 {
        if is_list {
            " ↑↓ n/b pages / filtre Entrée détail ? q"
        } else if app.view == View::Updates {
            " ↑↓ défiler p pause r relire ? q"
        } else {
            " ↑↓ alerte Entrée ouvrir F6 résumé ? q"
        }
    } else if is_list {
        " Tab vues ↑↓ n/b pages / filtre a actions F6 panneau * favori c copier e exporter ? q"
    } else if app.view == View::Updates {
        " Tab vues ↑↓/Pg défiler p pause r relire e exporter ? aide q quitter"
    } else {
        " ↑↓ alerte Entrée ouvrir n/b pages F6 résumé c copier e exporter ? q"
    };
    let status = if let Some(notice) = &app.notice {
        format!(
            " {}{}",
            if app.anonymized {
                "Action terminée · contenu masqué"
            } else {
                notice
            },
            if app.error.is_some() || !app.data.warnings.is_empty() {
                " · ! alertes"
            } else {
                " · ! détail"
            }
        )
    } else if app.action_busy {
        " Action en arrière-plan · navigation disponible".into()
    } else if app.data.partial {
        " Inventaire incomplet · compteurs partiels · jobs disponibles".into()
    } else if app.editing {
        " Recherche : Entrée valider · Échap effacer".to_owned()
    } else if app.error.is_some() {
        " Lecture interrompue · r reconnecter · ! détail".to_owned()
    } else if !app.data.warnings.is_empty() {
        format!(
            " {} alerte(s) de lecture · ! détail",
            app.data.warnings.len()
        )
    } else if app.loading {
        format!(
            " {} · dernier relevé conservé",
            app.read_phase
                .as_deref()
                .unwrap_or("Lecture locale en cours")
        )
    } else if app.data.demo {
        " Données fictives · aucune connexion au cluster".to_owned()
    } else {
        " Observations enregistrées · aucune actualisation distante".to_owned()
    };
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(fit(shortcuts, area.width as usize)).style(Style::default().fg(MUTED)),
            Line::from(fit(&status, area.width as usize))
                .style(Style::default().fg(if app.error.is_some() { ERROR } else { MUTED })),
        ]),
        area,
    );
}

fn scrollable(
    frame: &mut Frame,
    area: Rect,
    title: &str,
    lines: Vec<Line<'static>>,
    app: &mut App,
) {
    let paragraph = Paragraph::new(lines).wrap(Wrap { trim: false });
    let total = paragraph.line_count(area.width.saturating_sub(2));
    let visible = area.height.saturating_sub(2) as usize;
    app.scroll_page = visible.max(1) as u16;
    app.scroll_max = total.saturating_sub(visible).min(u16::MAX as usize) as u16;
    app.scroll = app.scroll.min(app.scroll_max);
    let mut border = block(title);
    if app.scroll_max > 0 {
        border = border.title_bottom(
            Line::from(format!(
                " Lignes {}–{} / {} ",
                app.scroll as usize + 1,
                (app.scroll as usize + visible).min(total),
                total
            ))
            .style(Style::default().fg(MUTED)),
        );
    }
    frame.render_widget(paragraph.block(border).scroll((app.scroll, 0)), area);
    scrollbar(frame, area, total, app.scroll as usize, visible);
}

fn scrollbar(frame: &mut Frame, area: Rect, total: usize, position: usize, visible: usize) {
    if total <= visible || area.width == 0 || area.height <= 2 {
        return;
    }
    let mut state = ScrollbarState::new(total)
        .position(position)
        .viewport_content_length(visible);
    frame.render_stateful_widget(
        Scrollbar::new(ScrollbarOrientation::VerticalRight)
            .begin_symbol(None)
            .end_symbol(None)
            .track_symbol(Some("│"))
            .thumb_symbol("┃")
            .track_style(Style::default().fg(Color::Rgb(70, 81, 96)))
            .thumb_style(Style::default().fg(MUTED)),
        Rect::new(area.x, area.y + 1, area.width, area.height - 2),
        &mut state,
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{Job, Snapshot, Transfer};
    use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
    use ratatui::{backend::TestBackend, Terminal};
    fn render(width: u16, height: u16, app: &mut App) -> String {
        let mut terminal = Terminal::new(TestBackend::new(width, height)).unwrap();
        terminal.draw(|frame| draw(frame, app)).unwrap();
        let buffer = terminal.backend().buffer();
        (0..height)
            .map(|y| {
                (0..width)
                    .map(|x| buffer[(x, y)].symbol())
                    .collect::<String>()
            })
            .collect::<Vec<_>>()
            .join("\n")
    }
    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::NONE)
    }

    #[test]
    fn minimum_size_keeps_job_rows_visible_and_details_accessible() {
        let mut app = App::new(View::Jobs);
        app.apply(Snapshot {
            jobs: vec![Job {
                id: "42001".into(),
                name: "Simulation MPI".into(),
                state: "RUNNING".into(),
                ..Job::default()
            }],
            ..Snapshot::default()
        });
        let text = render(48, 16, &mut app);
        assert!(text.contains("42001"));
        assert!(text.contains("En cours"));
        assert!(text.contains("Résultat"));
        assert!(text.contains("Entrée"));
        app.key(key(KeyCode::Enter));
        let text = render(48, 16, &mut app);
        assert!(text.contains("Durée écoulée"));
        app.key(key(KeyCode::End));
        assert!(render(48, 16, &mut app).contains("Validation"));
    }

    #[test]
    fn active_transfer_filter_stays_visible_after_enter() {
        let mut app = App::new(View::Transfers);
        app.apply(Snapshot {
            transfers: vec![Transfer {
                id: "a".into(),
                name: "checkpoint".into(),
                ..Transfer::default()
            }],
            ..Snapshot::default()
        });
        app.key(key(KeyCode::Char('/')));
        for c in "checkpoint".chars() {
            app.key(key(KeyCode::Char(c)));
        }
        app.key(key(KeyCode::Enter));
        assert!(render(100, 30, &mut app).contains("Filtre : checkpoint"));
    }

    #[test]
    fn updates_summary_includes_the_saved_proof_and_authorization() {
        let mut app = App::new(View::Updates);
        app.data.updates.version = "1.4.0".into();
        app.data.updates.next_version = "1.4.1".into();
        app.data.updates.latest_version = "1.4.2".into();
        app.data.updates.state = "idle".into();
        app.data.updates.automatic_enabled = true;
        app.data.updates.checked_at = Some(1000.0);
        let exported = summary(&mut app);
        assert!(exported.contains("Version actuelle : 1.4.0"));
        assert!(exported.contains("Prochain démarrage : 1.4.1"));
        assert!(exported.contains("Mises à jour automatiques : activées"));
        assert!(exported.contains("1970-01-01 00:16:40 UTC"));
    }

    #[test]
    fn compact_overview_can_scroll_to_configuration_and_restore_help() {
        let mut app = App::new(View::Overview);
        app.data.runtime.profile = "essential".into();
        let text = render(48, 16, &mut app);
        assert!(text.contains("local 5 s"));
        assert!(app.scroll_max > 0);
        app.key(key(KeyCode::End));
        assert!(render(48, 16, &mut app).contains("Configuration"));
        app.key(key(KeyCode::Enter));
        assert_eq!(app.scroll, 0);
        render(48, 16, &mut app);
        app.key(key(KeyCode::End));
        assert!(render(48, 16, &mut app).contains("essential"));
    }

    #[test]
    fn all_views_and_overlays_fit_without_panics() {
        for view in [
            View::Overview,
            View::Jobs,
            View::Transfers,
            View::Updates,
            View::Reports,
            View::Dossier,
            View::Recovery,
            View::Groups,
            View::Sessions,
        ] {
            for (width, height) in [(100, 30), (80, 24), (60, 18), (48, 16), (40, 10), (1, 1)] {
                let mut app = App::new(view);
                assert!(
                    render(width, height, &mut app).contains(if width >= 48 && height >= 16 {
                        "ROMEO"
                    } else if width >= 40 {
                        "Agrandir"
                    } else {
                        ""
                    })
                );
                if width >= 48 && height >= 16 {
                    app.overlay = Overlay::Help;
                    render(width, height, &mut app);
                    app.key(key(KeyCode::End));
                    assert!(
                        render(width, height, &mut app).contains("intégrité"),
                        "{width}x{height} {view:?}"
                    );
                }
            }
        }
    }

    #[test]
    fn error_footer_is_short_and_alert_detail_is_available() {
        let mut app = App::new(View::Overview);
        app.error = Some(
            "Lecteur arrêté. Une explication beaucoup plus longue qui doit rester consultable."
                .into(),
        );
        assert!(render(48, 16, &mut app).contains("r reconnecter"));
        app.key(key(KeyCode::Char('!')));
        assert!(render(100, 30, &mut app).contains("Une explication"));
    }

    #[test]
    fn confirmations_survive_warnings_and_sharing_masks_private_content() {
        let mut app = App::new(View::Dossier);
        app.data.jobs = vec![Job {
            id: "42".into(),
            name: "private-project".into(),
            ..Default::default()
        }];
        app.data.workspace.job_id = "42".into();
        app.data.workspace.logs = Some(crate::model::Logs {
            content: "/private/log-path".into(),
            ..Default::default()
        });
        app.notes.insert("42".into(), "private-note".into());
        app.data.warnings.push("/private/warning-path".into());
        app.confirm("Résumé exporté : /private/export-path");
        assert!(render(100, 30, &mut app).contains("Résumé exporté"));
        app.notice = None;
        app.key(key(KeyCode::Char('!')));
        assert!(render(100, 30, &mut app).contains("/private/export-path"));
        app.key(key(KeyCode::Esc));
        app.anonymized = true;
        let exported = summary(&mut app);
        for secret in ["private-project", "private/log-path", "private-note"] {
            assert!(!exported.contains(secret));
        }
        app.key(key(KeyCode::Char('!')));
        let text = render(100, 30, &mut app);
        assert!(!text.contains("private/"));
        assert_eq!(app.data.jobs[0].name, "private-project");
    }

    #[test]
    fn sessions_keep_availability_and_the_active_filter_visible_at_small_sizes() {
        let mut app = App::new(View::Sessions);
        app.data.sessions.push(crate::model::Session {
            name: "jupyter".into(),
            ready: Some(true),
            ..Default::default()
        });
        app.set_query("ready".into());
        for (width, height) in [(48, 16), (100, 30)] {
            let text = render(width, height, &mut app);
            assert!(text.contains("Filtre : ready"));
            assert!(text.contains("Observée"));
            assert!(text.contains("actions") || width < 80);
        }
    }

    #[test]
    fn failure_and_validation_styles_survive_selection() {
        let mut app = App::new(View::Jobs);
        app.data.jobs = vec![
            Job {
                id: "node".into(),
                state: "NODE_FAIL".into(),
                ..Job::default()
            },
            Job {
                id: "done".into(),
                state: "COMPLETED".into(),
                ..Job::default()
            },
        ];
        let mut terminal = Terminal::new(TestBackend::new(100, 30)).unwrap();
        terminal.draw(|frame| draw(frame, &mut app)).unwrap();
        let buffer = terminal.backend().buffer();
        let mut text = String::new();
        let mut errors = 0;
        let mut warnings = 0;
        for y in 0..30 {
            for x in 0..100 {
                let cell = &buffer[(x, y)];
                text.push_str(cell.symbol());
                errors += usize::from(cell.fg == ERROR);
                warnings += usize::from(cell.fg == Color::Rgb(229, 192, 123));
            }
        }
        assert!(text.contains("Nœud perdu"));
        assert!(text.contains("À vérifier"));
        assert!(errors >= "Nœud perdu".chars().count());
        assert!(warnings >= "À vérifier".chars().count());
    }

    #[test]
    fn monochrome_reason_and_scroll_position_are_visible_at_small_sizes() {
        let mut app = App::new(View::Overview);
        app.palette = Palette::NoColorEnvironment;
        assert!(render(48, 16, &mut app).contains("NO_COLOR"));
        app.key(key(KeyCode::Char('?')));
        let text = render(48, 16, &mut app);
        assert!(text.contains("Lignes"));
        assert!(text.contains('┃'));
        app.key(key(KeyCode::End));
        assert!(render(48, 16, &mut app).contains("--color"));
    }

    #[test]
    #[ignore = "explicit rendering measurement, not a timing assertion"]
    fn measure_render_cost() {
        let mut app = App::new(View::Jobs);
        app.data.jobs = (0..40)
            .map(|id| Job {
                id: id.to_string(),
                name: format!("Synthetic job {id}"),
                state: "RUNNING".into(),
                ..Default::default()
            })
            .collect();
        app.data.schema = 3;
        app.data.coverage.jobs = crate::model::Page {
            pages: 25,
            loaded: 40,
            matched: 1000,
            total: 1000,
            page_size: 40,
            ..Default::default()
        };
        for (width, height) in [(100, 30), (160, 40)] {
            let mut terminal = Terminal::new(TestBackend::new(width, height)).unwrap();
            terminal.draw(|frame| draw(frame, &mut app)).unwrap();
            let start = std::time::Instant::now();
            for _ in 0..200 {
                terminal.draw(|frame| draw(frame, &mut app)).unwrap();
            }
            println!(
                "Ratatui TestBackend {width}x{height}, 40 rows: {:.3} ms/draw (200 draws)",
                start.elapsed().as_secs_f64() * 5.0
            );
        }
    }
}
