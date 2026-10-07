//! Locally cached update state; rendering performs no release checks.
use super::{line, paragraph, scrollable};
use crate::{
    app::{App, Overlay},
    model::{age, present},
};
use ratatui::{layout::Rect, text::Line, Frame};

pub(super) fn draw(frame: &mut Frame, area: Rect, app: &mut App) {
    let update = &app.data.updates;
    let availability = match update.update_available {
        Some(true) => "Version plus récente dans le contrôle enregistré",
        Some(false) => "Pas de version plus récente dans ce contrôle",
        None => "Disponibilité inconnue ; aucun contrôle concluant",
    };
    let lines = vec![
        line("Version actuelle", &update.version),
        line("Prochain démarrage", &update.next_version),
        line("Dernière version connue", present(&update.latest_version)),
        line("Contrôle datant de", age(update.checked_at)),
        Line::from(availability),
        Line::from(""),
        line(
            "Mises à jour automatiques",
            if update.state == "unknown" {
                "inconnues"
            } else if update.automatic_enabled {
                "activées"
            } else {
                "désactivées"
            },
        ),
        line("Préparation", present(&update.state)),
        line("Phase", present(&update.phase)),
        line("Trace opération", age(update.observed_at)),
        line(
            "Reconnexion",
            if update.restart_required {
                "Reconnecter le MCP ou redémarrer l'application"
            } else {
                "Aucune demande enregistrée"
            },
        ),
        Line::from(""),
        Line::from("Cache local. Les outils MCP effectuent les contrôles GitHub."),
    ];
    if app.overlay == Overlay::None {
        scrollable(frame, area, " Mises à jour · ↑↓ défiler ", lines, app);
    } else {
        paragraph(frame, area, " Mises à jour ", lines);
    }
}
