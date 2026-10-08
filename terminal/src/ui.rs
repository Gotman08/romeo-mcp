//! Compact views prioritize records; rendering performs no IO.
mod details;
mod lists;
mod overlays;
mod overview;
mod progress;
mod updates;

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
            "{} · {} · local {} s · {reading}",
            if app.data.demo { "DÉMO" } else { "LOCAL" },
            if area.width < 80 {
                match app.palette {
                    Palette::NoColorEnvironment => "mono/NO_COLOR",
                    _ => "mono/--color never",
                }
            } else {
                app.palette.description()
            },
            app.refresh_seconds
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
                Span::styled("   v0.3 interne", Style::default().fg(MUTED)),
            ]),
            Line::from(format!(
                " {}",
                fit(&status, area.width.saturating_sub(2) as usize)
            )),
        ]),
        parts[0],
    );
    let titles = if area.width < 80 {
        ["1 Vue", "2 Jobs", "3 Cop.", "4 MAJ", "5 Bugs"]
    } else {
        [
            "1 Aperçu",
            "2 Jobs",
            "3 Transferts",
            "4 Mises à jour",
            "5 Rapports",
        ]
    };
    frame.render_widget(
        Tabs::new(titles)
            .select(app.view.index())
            .padding(" ", " ")
            .highlight_style(Style::default().fg(ACCENT).add_modifier(Modifier::BOLD))
            .divider(" ")
            .block(block("")),
        parts[1],
    );
    match app.view {
        View::Overview => overview::draw(frame, parts[2], app),
        View::Jobs | View::Transfers | View::Reports => lists::draw(frame, parts[2], app),
        View::Updates => updates::draw(frame, parts[2], app),
    }
    footer(frame, parts[3], app);
    if app.overlay != Overlay::None {
        overlays::draw(frame, area, app);
    }
}

fn footer(frame: &mut Frame, area: Rect, app: &App) {
    let is_list = matches!(app.view, View::Jobs | View::Transfers | View::Reports);
    let shortcuts = if area.width < 80 {
        if is_list {
            " ↑↓ / filtre s tri Entrée détail ? aide q quit"
        } else {
            " 1–5 vues ↑↓ défiler ? aide q quitter"
        }
    } else if is_list {
        " Tab vues ↑↓/Pg sélection / filtre s tri Entrée détail ? aide q quitter"
    } else {
        " 1–5/Tab vues ↑↓ défiler r relire p pause ? aide ! alertes q quitter"
    };
    let status = if app.editing {
        " Recherche : Entrée valider · Échap effacer".to_owned()
    } else if app.error.is_some() {
        " Lecture interrompue · r reconnecter · ! détail".to_owned()
    } else if !app.data.warnings.is_empty() {
        format!(
            " {} alerte(s) de lecture · ! détail",
            app.data.warnings.len()
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
}
