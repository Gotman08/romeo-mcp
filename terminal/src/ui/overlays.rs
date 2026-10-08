//! Scrollable help, complete record details and local reader alerts.
use super::{details, scrollable, BACKGROUND, TEXT};
use crate::{
    app::{App, Overlay},
    model::clean,
};
use ratatui::{
    layout::Rect,
    style::Style,
    text::{Line, Span},
    widgets::{Block, Clear, Paragraph, Wrap},
    Frame,
};

pub(super) fn draw(frame: &mut Frame, area: Rect, app: &mut App) {
    let width = area.width.saturating_sub(2).min(94);
    let height = area.height.saturating_sub(2).min(28);
    let popup = Rect::new(
        area.x + (area.width - width) / 2,
        area.y + (area.height - height) / 2,
        width,
        height,
    );
    frame.render_widget(Clear, popup);
    frame.render_widget(
        Block::default().style(Style::default().fg(TEXT).bg(BACKGROUND)),
        popup,
    );
    let mut cursor_line = None;
    let (title, lines) = match app.overlay {
        Overlay::Help => (
            " Aide · ↑↓ défiler · Échap fermer ",
            vec![
                Line::from("1–9 / Tab / ←→ : changer de vue"),
                Line::from("↑↓ / j k : sélectionner ; Pg↑ Pg↓ : une page"),
                Line::from("Début / Fin : première / dernière ligne"),
                Line::from("Entrée : ouvrir le détail complet, même en mode compact"),
                Line::from("/ : rechercher ; la saisie remplace le filtre précédent"),
                Line::from("Entrée : conserver ; Échap : effacer en une fois"),
                Line::from("Les filtres Jobs, Transferts et Rapports sont indépendants."),
                Line::from("Recherche globale dans le registre local, pages bornées."),
                Line::from("n / b : page de données suivante / précédente"),
                Line::from("Aperçu : ↑↓ sélectionner une alerte ; Entrée ouvre sa trace"),
                Line::from("F6 : liste / détail actif (résumé dans l'Aperçu)"),
                Line::from("v : liste seule / liste et détail ; [ ] : largeur du détail"),
                Line::from("c : copier l'identifiant ; C : copier le chemin d'un transfert"),
                Line::from("e : exporter un résumé local ; ! montre le chemin complet"),
                Line::from("Préférences : dernière vue, tri et disposition mémorisés."),
                Line::from("Recherche : libellés français et techniques, accents ignorés."),
                Line::from("s : tri actifs, date, état ou priorité ; sélection conservée"),
                Line::from("r : relire les fichiers ; reconnecter le lecteur en erreur"),
                Line::from("p : pause / reprise de la relecture locale"),
                Line::from("! : consulter toutes les alertes de lecture"),
                Line::from("q / Ctrl-C : quitter et restaurer le terminal"),
                Line::from(""),
                Line::from("Les états sont des observations datées, pas des sondes du cluster."),
                Line::from("Le tableau ne lance pas de job, de transfert ou de publication."),
                Line::from("Compteurs : toutes les traces lisibles connues, même hors page."),
                Line::from(app.palette.description()),
                Line::from("6 Dossier / 7 Reprise / 8 Groupes / 9 Sessions"),
                Line::from("a : menu contextuel ; * : favori ; N : note locale"),
                Line::from("Note : F2/Ctrl-S enregistrer ; ←→ Début/Fin déplacer"),
                Line::from("Le collage reste du texte ; les retours deviennent des espaces."),
                Line::from("P : présentation anonymisée ; w/W : largeur identifiant"),
                Line::from("Filtres combinés : etat:COMPLETED validation:check gpu:oui"),
                Line::from("partition:gpu depuis:2026-10-01 avant:2026-10-09 cpu:>=8"),
                Line::from("Aperçu : F6 active le résumé ; Mises à jour : ↑↓/Fin défilent."),
                Line::from("f : ouvrir les favoris ; X : arrêter l'action d'observation"),
                Line::from("tui --color auto/always/never : choisir le mode couleur"),
                Line::from("Une copie à 100 % ne garantit pas son intégrité."),
            ],
        ),
        Overlay::Details => (
            " Détail · ↑↓/Pg défiler · Échap fermer ",
            details::lines(app),
        ),
        Overlay::Logs => (
            " Journaux enregistrés · Échap fermer ",
            super::workspace::log_lines(app),
        ),
        Overlay::Note => {
            let (lines, cursor) = note_lines(app, popup.width.saturating_sub(2));
            cursor_line = Some(cursor);
            (" Note locale · F2 enregistrer · Échap annuler ", lines)
        }
        Overlay::Actions => (
            " Actions · ↑↓ choisir · Entrée · Échap ",
            app.menu_items()
                .iter()
                .enumerate()
                .map(|(index, item)| {
                    Line::styled(
                        format!(
                            "{} {}",
                            if index == app.menu_selected {
                                "›"
                            } else {
                                " "
                            },
                            item.0
                        ),
                        if index == app.menu_selected {
                            Style::default().fg(super::ACCENT)
                        } else {
                            Style::default().fg(TEXT)
                        },
                    )
                })
                .collect(),
        ),
        Overlay::Favorites => (
            " Favoris · ↑↓ choisir · Entrée dossier · Échap ",
            if app.favorites.is_empty() {
                vec![Line::from("Aucun favori. * épingle le calcul sélectionné.")]
            } else {
                app.favorites
                    .iter()
                    .enumerate()
                    .map(|(index, id)| {
                        Line::styled(
                            format!(
                                "{} Calcul {}",
                                if index == app.menu_selected {
                                    "›"
                                } else {
                                    " "
                                },
                                id
                            ),
                            if index == app.menu_selected {
                                Style::default().fg(super::ACCENT)
                            } else {
                                Style::default().fg(TEXT)
                            },
                        )
                    })
                    .collect()
            },
        ),
        _ => {
            let mut lines = Vec::new();
            if let Some(notice) = app.notice.as_ref().or(app.last_confirmation.as_ref()) {
                lines.push(Line::from(if app.anonymized {
                    "Confirmation locale · contenu masqué".into()
                } else {
                    clean(notice)
                }));
            }
            if let Some(error) = &app.error {
                lines.push(Line::from(if app.anonymized {
                    "Erreur de lecture · contenu masqué".into()
                } else {
                    clean(error)
                }));
                lines.push(Line::from("r : retenter la lecture locale"));
            }
            lines.extend(
                app.data
                    .warnings
                    .iter()
                    .map(|warning| Line::from(clean(warning))),
            );
            lines.extend(
                app.notification_log
                    .iter()
                    .rev()
                    .map(|item| Line::from(clean(item))),
            );
            if lines.is_empty() {
                lines.push(Line::from("Aucune alerte de lecture enregistrée."));
            }
            (" Alertes · ↑↓ défiler · Échap fermer ", lines)
        }
    };
    let visible = popup.height.saturating_sub(2).max(1) as usize;
    if let Some(cursor) = cursor_line {
        keep_visible(app, cursor, cursor + 1, visible);
    } else if matches!(app.overlay, Overlay::Actions | Overlay::Favorites) {
        // Menu entries can occupy several rendered lines on narrow terminals.
        let heights: Vec<_> = lines
            .iter()
            .map(|line| {
                Paragraph::new(line.clone())
                    .wrap(Wrap { trim: false })
                    .line_count(popup.width.saturating_sub(2))
            })
            .collect();
        let selected = app.menu_selected.min(heights.len().saturating_sub(1));
        let start = heights.iter().take(selected).sum();
        let end = start + heights.get(selected).copied().unwrap_or(1);
        keep_visible(app, start, end, visible);
    }
    scrollable(frame, popup, title, lines, app);
}

fn keep_visible(app: &mut App, start: usize, end: usize, visible: usize) {
    let offset = app.scroll as usize;
    let scroll = if start < offset {
        start
    } else if end > offset + visible {
        end.min(start + visible).saturating_sub(visible)
    } else {
        offset
    };
    app.scroll = scroll.min(u16::MAX as usize) as u16;
}

/// Hard-wrap note text so the cursor's rendered line remains unambiguous.
fn note_lines(app: &App, width: u16) -> (Vec<Line<'static>>, usize) {
    let mut lines = vec![
        Line::from(format!(
            "Calcul : {}",
            app.note_target.as_deref().unwrap_or("—")
        )),
        Line::from(format!(
            "{} / 500 caractères · ←→ Début/Fin",
            app.note_edit.chars().count()
        )),
    ];
    let prefix = Paragraph::new(lines.clone())
        .wrap(Wrap { trim: false })
        .line_count(width);
    let mut body = Vec::new();
    let mut row = Vec::new();
    let mut used = 0;
    let mut cursor = prefix;
    let note: Vec<_> = app.note_edit.chars().collect();
    for index in 0..=note.len() {
        let symbols = (index == app.note_cursor.min(note.len()))
            .then_some(Span::styled("▏", Style::default().fg(super::ACCENT)))
            .into_iter()
            .chain(note.get(index).map(|c| Span::raw(c.to_string())));
        for span in symbols {
            if used + span.width() > width.max(1) as usize && !row.is_empty() {
                body.push(Line::from(std::mem::take(&mut row)));
                used = 0;
            }
            if span.content == "▏" && span.style.fg.is_some() {
                cursor = prefix + body.len();
            }
            used += span.width();
            row.push(span);
        }
    }
    body.push(Line::from(row));
    lines.extend(body);
    (lines, cursor)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        app::View,
        model::{Job, Snapshot},
    };
    use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
    use ratatui::{backend::TestBackend, Terminal};

    fn render(app: &mut App, width: u16, height: u16) -> String {
        let mut terminal = Terminal::new(TestBackend::new(width, height)).unwrap();
        terminal.draw(|frame| crate::ui::draw(frame, app)).unwrap();
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

    fn press(app: &mut App, code: KeyCode) {
        app.key(KeyEvent::new(code, KeyModifiers::NONE));
    }
    fn sample() -> App {
        let mut app = App::new(View::Jobs);
        app.apply(Snapshot {
            jobs: vec![Job {
                id: "42".into(),
                ..Default::default()
            }],
            ..Default::default()
        });
        app
    }

    #[test]
    fn menus_keep_selection_visible_when_moving_up_or_resizing() {
        for (width, height) in [(100, 18), (48, 16)] {
            let mut app = sample();
            press(&mut app, KeyCode::Char('a'));
            press(&mut app, KeyCode::End);
            assert!(render(&mut app, width, height).contains("› Interroger ROMEO : reprise"));
            press(&mut app, KeyCode::Home);
            assert!(render(&mut app, width, height).contains("› Dossier du calcul"));
            assert_eq!(app.scroll, 0);
            press(&mut app, KeyCode::Esc);
            app.favorites.extend((0..30).map(|i| format!("{i:03}")));
            press(&mut app, KeyCode::Char('f'));
            press(&mut app, KeyCode::End);
            assert!(render(&mut app, width, height).contains("› Calcul 029"));
            press(&mut app, KeyCode::Home);
            assert!(render(&mut app, width, height).contains("› Calcul 000"));
        }
    }

    #[test]
    fn long_notes_follow_the_cursor_in_both_directions() {
        let mut app = sample();
        press(&mut app, KeyCode::Char('N'));
        app.paste(&format!("{}FIN-DE-NOTE", "x".repeat(480)));
        let tail = render(&mut app, 48, 16);
        assert!(tail.contains("NOTE▏"));
        assert!(app.scroll > 0);
        press(&mut app, KeyCode::Home);
        assert!(render(&mut app, 48, 16).contains("▏xxxx"));
        press(&mut app, KeyCode::End);
        assert!(render(&mut app, 48, 16).contains("NOTE▏"));
        assert!(render(&mut app, 160, 40).contains("FIN-DE-NOTE▏"));
    }
}
