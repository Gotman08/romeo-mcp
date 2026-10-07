//! Restrained layout with explicit evidence ages; drawing never performs IO.
use crate::{
    app::{App, View},
    model::{age, clean},
};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, BorderType, Cell, Clear, Paragraph, Row, Table, Tabs, Wrap},
    Frame,
};

const ACCENT: Color = Color::Cyan;

fn block(title: impl Into<String>) -> Block<'static> {
    Block::bordered()
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::DarkGray))
        .title(Line::from(title.into()).style(Style::default().fg(Color::Gray)))
}

fn line(label: &str, value: impl AsRef<str>) -> Line<'static> {
    Line::from(vec![
        Span::styled(format!("{label}  "), Style::default().fg(Color::DarkGray)),
        Span::raw(clean(value.as_ref())),
    ])
}

fn state_style(state: &str) -> Style {
    let color = match state.to_ascii_uppercase().as_str() {
        "RUNNING" | "PREPARING" => ACCENT,
        "COMPLETED" | "READY" => Color::Green,
        "FAILED" | "TIMEOUT" | "CANCELLED" | "LAUNCHFAILED" | "LAUNCH_FAILED" => Color::Red,
        "PENDING" | "COMPLETED_UNVERIFIED" => Color::Yellow,
        _ => Color::Gray,
    };
    Style::default().fg(color)
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
    if area.width < 48 || area.height < 16 {
        frame.render_widget(
            Paragraph::new("ROMEO · agrandir le terminal (48 × 16 minimum)\nq : quitter")
                .wrap(Wrap { trim: true })
                .block(block(" ROMEO ")),
            area,
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
    let mode = if app.data.demo {
        "DÉMONSTRATION · données fictives"
    } else {
        "HISTORIQUE LOCAL · lecture seule"
    };
    let refresh = if app.paused {
        "pause"
    } else if app.loading {
        "lecture…"
    } else {
        "auto"
    };
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(vec![
                Span::styled(
                    " ROMEO ",
                    Style::default().fg(ACCENT).add_modifier(Modifier::BOLD),
                ),
                Span::raw("Tableau de bord"),
                Span::styled("   v0.1 interne", Style::default().fg(Color::DarkGray)),
            ]),
            Line::from(format!(
                " {mode}  ·  {refresh}  ·  relevé : {}",
                age(Some(app.data.generated_at))
            )),
        ]),
        parts[0],
    );
    let titles = if area.width < 65 {
        ["1 Aperçu", "2 Jobs", "3 Copies", "4 MAJ"]
    } else {
        ["1 Aperçu", "2 Jobs", "3 Transferts", "4 Mises à jour"]
    };
    frame.render_widget(
        Tabs::new(titles)
            .select(app.view.index())
            .highlight_style(Style::default().fg(ACCENT).add_modifier(Modifier::BOLD))
            .divider("  ")
            .block(block("")),
        parts[1],
    );
    match app.view {
        View::Overview => overview(frame, parts[2], app),
        View::Jobs => jobs(frame, parts[2], app),
        View::Transfers => transfers(frame, parts[2], app),
        View::Updates => updates(frame, parts[2], app),
    }
    let status = if app.editing {
        format!(
            " Filtre : {}_   Entrée : valider · Échap : fermer",
            clean(&app.query)
        )
    } else if let Some(error) = &app.error {
        format!(
            " {}  Dernier relevé conservé ; quitter puis rouvrir pour réessayer.",
            clean(error)
        )
    } else if let Some(warning) = app.data.warnings.first() {
        format!(
            " {} (+{} autre(s))",
            clean(warning),
            app.data.warnings.len().saturating_sub(1)
        )
    } else {
        " Les âges concernent les observations enregistrées. Aucun appel SSH ou GitHub.".to_owned()
    };
    let shortcuts = if area.width < 75 {
        " 1–4 vues  ↑↓  / filtre  ? aide  q quitter"
    } else {
        " Tab/←→ vues  ↑↓ sélection  / filtre  r relire  p pause  ? aide  q quitter"
    };
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(shortcuts).style(Style::default().fg(Color::DarkGray)),
            Line::from(status).style(Style::default().fg(if app.error.is_some() {
                Color::Red
            } else {
                Color::Gray
            })),
        ]),
        parts[3],
    );
    if app.help {
        help(frame, area);
    }
}

fn overview(frame: &mut Frame, area: Rect, app: &App) {
    let parts = Layout::vertical([Constraint::Length(4), Constraint::Min(1)]).split(area);
    let cards = Layout::horizontal([Constraint::Percentage(25); 4]).split(parts[0]);
    let active = app
        .data
        .jobs
        .iter()
        .filter(|job| job.state == "RUNNING" || job.state == "PENDING")
        .count();
    let metrics = [
        ("Jobs enregistrés", app.data.jobs.len().to_string()),
        ("RUNNING / PENDING", active.to_string()),
        ("Transferts", app.data.transfers.len().to_string()),
        ("Version MCP", clean(&app.data.runtime.version)),
    ];
    for (index, (title, value)) in metrics.into_iter().enumerate() {
        frame.render_widget(
            Paragraph::new(value)
                .style(Style::default().fg(ACCENT))
                .block(block(title)),
            cards[index],
        );
    }
    let panels = Layout::default()
        .direction(if area.width >= 78 {
            Direction::Horizontal
        } else {
            Direction::Vertical
        })
        .constraints([Constraint::Percentage(55), Constraint::Percentage(45)])
        .split(parts[1]);
    let mut rows = vec![
        line("Profil d'outils", &app.data.runtime.profile),
        line(
            "Configuration",
            if app.data.runtime.configured {
                "projet renseigné"
            } else {
                "projet absent"
            },
        ),
        line(
            "Registre",
            if app.data.runtime.registry_present {
                "présent"
            } else {
                "aucun registre créé"
            },
        ),
        Line::from(""),
    ];
    for job in app.data.jobs.iter().take(4) {
        rows.push(Line::from(vec![
            Span::raw(format!("{}  {}  ", clean(&job.id), clean(&job.name))),
            Span::styled(clean(&job.state), state_style(&job.state)),
        ]));
    }
    if app.data.jobs.is_empty() {
        rows.push(Line::from("Aucun job enregistré dans cette installation."));
    }
    paragraph(frame, panels[0], " Repères ", rows);
    paragraph(
        frame,
        panels[1],
        " Lire les états ",
        vec![
            Line::from(
                "Les états sont des observations datées. Le cluster n'est pas interrogé ici.",
            ),
            Line::from(""),
            Line::from("COMPLETED signifie fin Slurm. La validation du résultat reste distincte."),
            Line::from(""),
            Line::from("2 : jobs   3 : transferts   4 : mises à jour"),
        ],
    );
}

fn list_layout(area: Rect) -> (Rect, Rect) {
    let parts = if area.width >= 115 {
        Layout::horizontal([Constraint::Percentage(62), Constraint::Percentage(38)]).split(area)
    } else {
        Layout::vertical([Constraint::Min(3), Constraint::Length(7)]).split(area)
    };
    (parts[0], parts[1])
}

fn jobs(frame: &mut Frame, area: Rect, app: &mut App) {
    let (table_area, detail_area) = list_layout(area);
    let filtered = app.jobs();
    let selected = filtered
        .get(app.jobs_table.selected().unwrap_or(0))
        .cloned()
        .cloned();
    let count = filtered.len();
    let rows: Vec<Row<'static>> = filtered
        .into_iter()
        .map(|job| {
            Row::new([
                Cell::from(clean(&job.id)),
                Cell::from(clean(&job.name)),
                Cell::from(clean(&job.state)).style(state_style(&job.state)),
                Cell::from(age(job.observed_at)),
            ])
        })
        .collect();
    let title = format!(
        " Jobs · {count}/{}{} ",
        app.data.jobs.len(),
        if app.query.is_empty() {
            String::new()
        } else {
            format!(" · filtre : {}", clean(&app.query))
        }
    );
    let table = Table::new(
        rows,
        [
            Constraint::Length(10),
            Constraint::Min(12),
            Constraint::Length(18),
            Constraint::Length(12),
        ],
    )
    .header(
        Row::new(["Job", "Nom", "État enregistré", "Âge trace"])
            .style(Style::default().fg(Color::DarkGray)),
    )
    .block(block(title))
    .row_highlight_style(Style::default().bg(Color::DarkGray))
    .highlight_symbol("› ");
    frame.render_stateful_widget(table, table_area, &mut app.jobs_table);
    let detail = if let Some(job) = selected {
        vec![
            line("Job", format!("{} · {}", job.id, job.name)),
            line(
                "Partition / soumission",
                format!("{} · il y a {}", job.partition, age(job.submitted_at)),
            ),
            line(
                "Observation",
                format!("{} · historique, cible non contrôlée", age(job.observed_at)),
            ),
            line(
                "Durée / restant / sortie",
                format!("{} / {} / {}", job.elapsed, job.remaining, job.exit_code),
            ),
            line(
                "Résultat",
                if job.result_validated {
                    "validation enregistrée"
                } else {
                    "non validé — vérifier les résultats du calcul"
                },
            ),
        ]
    } else {
        vec![Line::from(if app.data.jobs.is_empty() {
            "Aucun job local. Les soumissions du MCP alimentent ce registre."
        } else {
            "Aucun job ne correspond au filtre. Échap : effacer le filtre."
        })]
    };
    paragraph(frame, detail_area, " Détail du job ", detail);
}

fn transfers(frame: &mut Frame, area: Rect, app: &mut App) {
    let (table_area, detail_area) = list_layout(area);
    let filtered = app.transfers();
    let selected = filtered
        .get(app.transfers_table.selected().unwrap_or(0))
        .cloned()
        .cloned();
    let count = filtered.len();
    let rows: Vec<Row<'static>> = filtered
        .into_iter()
        .map(|transfer| {
            Row::new([
                Cell::from(if transfer.direction == "upload" {
                    "→ ROMEO"
                } else {
                    "← ROMEO"
                }),
                Cell::from(clean(
                    transfer
                        .name
                        .rsplit(['/', '\\'])
                        .next()
                        .unwrap_or(&transfer.name),
                )),
                Cell::from(clean(&transfer.state)).style(state_style(&transfer.state)),
                Cell::from(age(transfer.observed_at)),
            ])
        })
        .collect();
    let table = Table::new(
        rows,
        [
            Constraint::Length(9),
            Constraint::Min(12),
            Constraint::Length(22),
            Constraint::Length(12),
        ],
    )
    .header(
        Row::new(["Sens", "Fichier", "État enregistré", "Âge trace"])
            .style(Style::default().fg(Color::DarkGray)),
    )
    .block(block(format!(
        " Transferts · {count}/{} ",
        app.data.transfers.len()
    )))
    .row_highlight_style(Style::default().bg(Color::DarkGray))
    .highlight_symbol("› ");
    frame.render_stateful_widget(table, table_area, &mut app.transfers_table);
    let detail = if let Some(transfer) = selected {
        vec![
            line("Local", transfer.local_path),
            line("Distant", transfer.remote_path),
            line(
                "Phase / trace",
                format!(
                    "{} · {} · processus non contrôlé",
                    transfer.phase,
                    age(transfer.observed_at)
                ),
            ),
            line(
                "Intégrité",
                if transfer.result_validated {
                    "copie vérifiée dans le résultat enregistré"
                } else {
                    "validation de la copie absente"
                },
            ),
            line(
                "Annulation",
                if transfer.cancel_requested {
                    "demandée ; arrêt à vérifier"
                } else {
                    "aucune demande enregistrée"
                },
            ),
        ]
    } else {
        vec![Line::from(if app.data.transfers.is_empty() {
            "Aucun transfert local. Les plans MCP apparaîtront ici."
        } else {
            "Aucun transfert ne correspond au filtre. Échap : effacer le filtre."
        })]
    };
    paragraph(frame, detail_area, " Détail du transfert ", detail);
}

fn updates(frame: &mut Frame, area: Rect, app: &App) {
    let update = &app.data.updates;
    let availability = match update.update_available {
        Some(true) => "Nouvelle version dans le dernier contrôle enregistré",
        Some(false) => "Aucune version plus récente dans ce contrôle",
        None => "Disponibilité inconnue ; aucun contrôle concluant enregistré",
    };
    paragraph(
        frame,
        area,
        " Mises à jour · cache local uniquement ",
        vec![
            line("Version du lecteur", &update.version),
            line("Version sélectionnée", &update.next_version),
            line(
                "Dernière version connue",
                if update.latest_version.is_empty() {
                    "inconnue"
                } else {
                    &update.latest_version
                },
            ),
            line(
                "Contrôle GitHub",
                format!("il y a {}", age(update.checked_at)),
            ),
            Line::from(clean(availability)),
            Line::from(""),
            line(
                "Autorisation automatique",
                if update.state == "unknown" {
                    "inconnue"
                } else if update.automatic_enabled {
                    "activée"
                } else {
                    "désactivée"
                },
            ),
            line(
                "Préparation enregistrée",
                format!("{} · {}", update.state, update.phase),
            ),
            line("Dernière trace opération", age(update.observed_at)),
            line(
                "Reconnexion demandée",
                if update.restart_required {
                    "oui — reconnecter le MCP ou redémarrer l'application"
                } else {
                    "aucune selon l'état local"
                },
            ),
            Line::from(""),
            Line::from("La relecture du tableau ne vérifie pas GitHub et n'installe rien."),
            Line::from("L'assistant ou la commande update gère les contrôles et installations."),
            Line::from("Une phase enregistrée ne prouve pas que son worker est encore actif."),
        ],
    );
}

fn help(frame: &mut Frame, area: Rect) {
    let width = area.width.min(76);
    let height = area.height.min(20);
    let popup = Rect::new(
        area.x + (area.width - width) / 2,
        area.y + (area.height - height) / 2,
        width,
        height,
    );
    frame.render_widget(Clear, popup);
    paragraph(
        frame,
        popup,
        " Aide · ? / Échap pour fermer ",
        vec![
            Line::from("1–4 / Tab / ← →    Choisir une vue"),
            Line::from("↑ ↓ / j k          Sélectionner un job ou un transfert"),
            Line::from("Début / Fin        Première / dernière ligne"),
            Line::from("/                  Filtrer noms, identifiants et états"),
            Line::from("Entrée / Échap     Fermer la saisie ; Échap efface ensuite le filtre"),
            Line::from("r                  Relire les fichiers locaux, même en pause"),
            Line::from("p                  Suspendre / reprendre la relecture automatique"),
            Line::from("q / Ctrl-C         Quitter et restaurer le terminal"),
            Line::from(""),
            Line::from("Cette première version est une vue des traces de cette installation."),
            Line::from("Elle n'interroge pas le cluster, ne lance pas de job et n'annule rien."),
            Line::from("Pour observer le cluster, utiliser les outils MCP depuis l'assistant."),
            Line::from("Les nombres affichés concernent le sous-ensemble récent chargé."),
        ],
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::{backend::TestBackend, Terminal};

    fn render(width: u16, height: u16, view: View, help_visible: bool) -> String {
        let mut app = App::new(view);
        app.help = help_visible;
        let mut terminal = Terminal::new(TestBackend::new(width, height)).unwrap();
        terminal.draw(|frame| draw(frame, &mut app)).unwrap();
        terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect()
    }

    #[test]
    fn all_views_render_empty_and_small_terminals_without_panics() {
        for view in [View::Overview, View::Jobs, View::Transfers, View::Updates] {
            for (width, height) in [(100, 30), (60, 18), (48, 16), (40, 10), (1, 1)] {
                let output = render(width, height, view, false);
                if width >= 48 && height >= 16 {
                    assert!(output.contains("ROMEO"));
                }
            }
        }
        assert!(render(40, 10, View::Overview, false).contains("agrandir"));
    }

    #[test]
    fn help_and_states_preserve_evidence_semantics() {
        assert!(render(100, 30, View::Overview, true).contains("restaurer le terminal"));
        assert!(render(100, 30, View::Jobs, false).contains("Aucun job local"));
        assert!(render(100, 30, View::Updates, false).contains("Disponibilité inconnue"));
        assert!(render(100, 30, View::Overview, false).contains("HISTORIQUE LOCAL"));
    }
}
