//! Scrollable help, complete record details and local reader alerts.
use super::{details, scrollable, BACKGROUND, TEXT};
use crate::{
    app::{App, Overlay},
    model::clean,
};
use ratatui::{
    layout::Rect,
    style::Style,
    text::Line,
    widgets::{Block, Clear},
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
    let (title, lines) = match app.overlay {
        Overlay::Help => (
            " Aide · ↑↓ défiler · Échap fermer ",
            vec![
                Line::from("1–5 / Tab / ←→ : changer de vue"),
                Line::from("↑↓ / j k : sélectionner ; Pg↑ Pg↓ : une page"),
                Line::from("Début / Fin : première / dernière ligne"),
                Line::from("Entrée : ouvrir le détail complet, même en mode compact"),
                Line::from("/ : rechercher ; la saisie remplace le filtre précédent"),
                Line::from("Entrée : conserver ; Échap : effacer en une fois"),
                Line::from("Les filtres Jobs, Transferts et Rapports sont indépendants."),
                Line::from("Recherche : libellés français et techniques, accents ignorés."),
                Line::from("s : tri par date, état ou priorité ; sélection conservée"),
                Line::from("r : relire les fichiers ; reconnecter le lecteur en erreur"),
                Line::from("p : pause / reprise de la relecture locale"),
                Line::from("! : consulter toutes les alertes de lecture"),
                Line::from("q / Ctrl-C : quitter et restaurer le terminal"),
                Line::from(""),
                Line::from("Les états sont des observations datées, pas des sondes du cluster."),
                Line::from("Le tableau ne lance pas de job, de transfert ou de publication."),
                Line::from("Les nombres concernent les traces récentes chargées."),
                Line::from("Une copie à 100 % ne garantit pas son intégrité."),
                Line::from(app.palette.description()),
                Line::from("tui --color auto/always/never : choisir le mode couleur"),
                Line::from("Aperçu et Mises à jour : ↑↓ ou Fin pour lire toute la vue."),
            ],
        ),
        Overlay::Details => (
            " Détail · ↑↓/Pg défiler · Échap fermer ",
            details::lines(app),
        ),
        _ => {
            let mut lines = Vec::new();
            if let Some(error) = &app.error {
                lines.push(Line::from(clean(error)));
                lines.push(Line::from("r : retenter la lecture locale"));
            }
            lines.extend(
                app.data
                    .warnings
                    .iter()
                    .map(|warning| Line::from(clean(warning))),
            );
            if lines.is_empty() {
                lines.push(Line::from("Aucune alerte de lecture enregistrée."));
            }
            (" Alertes · ↑↓ défiler · Échap fermer ", lines)
        }
    };
    scrollable(frame, popup, title, lines, app);
}
