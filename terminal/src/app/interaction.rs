//! Keyboard, mouse and contextual actions; no execution or network IO.
use super::{Action, App, KeyCode, KeyEvent, KeyModifiers, LayoutMode, Overlay, Panel, View};

impl App {
    pub fn menu_items(&self) -> Vec<(&'static str, &'static str)> {
        let mut items = vec![
            ("Dossier du calcul", "dossier"),
            ("Reprise vérifiée", "recovery"),
            ("Groupes et dépendances", "groups"),
            ("Services et sessions", "sessions"),
            ("Copier l'identifiant", "copy"),
            ("Exporter le résumé", "export"),
            ("Épingler / retirer des favoris", "favorite"),
            ("Modifier la note locale", "note"),
            ("Ouvrir les favoris", "favorites"),
            ("Mode présentation : activer / désactiver", "anonymize"),
            ("Notifications : activer / désactiver", "notifications"),
            ("Souris : activer / désactiver", "mouse"),
        ];
        if self.selected_job().is_some()
            && matches!(
                self.view,
                View::Jobs | View::Dossier | View::Recovery | View::Groups
            )
        {
            items.extend([
                ("Lire les journaux enregistrés", "logs"),
                ("Interroger ROMEO : état du job", "status"),
                ("Interroger ROMEO : efficacité", "efficiency"),
                ("Interroger ROMEO : journaux", "remote_logs"),
                ("Interroger ROMEO : reprise", "resume"),
            ]);
        } else if self.view == View::Sessions {
            if let Some(session) = self
                .data
                .sessions
                .get(self.sessions_table.selected().unwrap_or(0))
            {
                items.push(if session.name == "allocation" {
                    ("Interroger ROMEO : état de l'allocation", "allocation")
                } else {
                    ("Interroger ROMEO : état du service", "service")
                });
            }
        }
        if self.action_busy {
            items.push(("Arrêter l'action en cours (aucun job annulé)", "cancel"));
        }
        items
    }

    fn menu_action(&mut self) -> Action {
        let key = self
            .menu_items()
            .get(self.menu_selected)
            .map(|item| item.1)
            .unwrap_or("");
        self.close_overlay();
        match key {
            "dossier" => self.switch_view(View::Dossier),
            "recovery" => self.switch_view(View::Recovery),
            "groups" => self.switch_view(View::Groups),
            "sessions" => self.switch_view(View::Sessions),
            "copy" => return Action::Copy(false),
            "export" => return Action::Export,
            "favorite" => self.toggle_favorite(),
            "note" => self.edit_note(),
            "favorites" => {
                self.menu_selected = 0;
                self.open(Overlay::Favorites);
            }
            "cancel" => return Action::Cancel,
            "anonymize" => self.anonymized = !self.anonymized,
            "notifications" => self.notifications = !self.notifications,
            "mouse" => self.mouse_enabled = !self.mouse_enabled,
            "logs" => self.open(Overlay::Logs),
            "status" => return Action::Remote("status"),
            "efficiency" => return Action::Remote("efficiency"),
            "remote_logs" => return Action::Remote("logs"),
            "resume" => return Action::Remote("resume"),
            "service" => return Action::Remote("service"),
            "allocation" => return Action::Remote("allocation"),
            _ => {}
        }
        Action::None
    }
    pub fn toggle_favorite(&mut self) {
        if !matches!(
            self.view,
            View::Jobs | View::Dossier | View::Recovery | View::Groups
        ) {
            return;
        }
        if let Some(id) = self.selected_job().map(|row| row.id.clone()) {
            if !self.favorites.remove(&id) && self.favorites.len() < 1000 {
                self.favorites.insert(id);
            }
        }
    }
    fn edit_note(&mut self) {
        if !matches!(
            self.view,
            View::Jobs | View::Dossier | View::Recovery | View::Groups
        ) {
            return;
        }
        if self.anonymized {
            self.confirm("Désactiver le mode présentation pour modifier une note.");
            return;
        }
        if let Some(id) = self.selected_job().map(|row| row.id.clone()) {
            self.note_edit = self.notes.get(&id).cloned().unwrap_or_default();
            self.note_target = Some(id);
            self.open(Overlay::Note);
        }
    }

    pub fn mouse(&mut self, event: crossterm::event::MouseEvent) {
        use crossterm::event::MouseEventKind;
        if !self.mouse_enabled {
            return;
        }
        match event.kind {
            MouseEventKind::ScrollUp => {
                self.key(KeyEvent::new(KeyCode::Up, KeyModifiers::NONE));
            }
            MouseEventKind::ScrollDown => {
                self.key(KeyEvent::new(KeyCode::Down, KeyModifiers::NONE));
            }
            MouseEventKind::Down(crossterm::event::MouseButton::Left) => {
                if self.overlay != Overlay::None {
                    return;
                }
                if let Some((_, view)) = self
                    .tab_hits
                    .iter()
                    .find(|(rect, _)| rect.contains((event.column, event.row).into()))
                {
                    self.switch_view(*view);
                    return;
                }
                if self
                    .detail_area
                    .is_some_and(|rect| rect.contains((event.column, event.row).into()))
                {
                    self.focus = Panel::Detail;
                    return;
                }
                if let Some(rect) = self
                    .table_area
                    .filter(|rect| rect.contains((event.column, event.row).into()))
                {
                    let count = self.row_count();
                    if event.row >= rect.y + 2 {
                        if let Some(table) = self.table() {
                            let position = table.offset() + (event.row - rect.y - 2) as usize;
                            if position < count {
                                table.select(Some(position));
                                self.focus = Panel::List;
                                self.mark_read(false);
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }

    pub fn key(&mut self, key: KeyEvent) -> Action {
        if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
            return Action::Quit;
        }
        if self.overlay == Overlay::Note {
            match key.code {
                KeyCode::Esc => self.close_overlay(),
                KeyCode::Enter => {
                    if let Some(id) = self.note_target.take() {
                        if self.note_edit.is_empty() {
                            self.notes.remove(&id);
                        } else if (self.notes.len() < 1000 || self.notes.contains_key(&id))
                            && self.notes.values().map(String::len).sum::<usize>()
                                - self.notes.get(&id).map_or(0, String::len)
                                + self.note_edit.len()
                                <= 256000
                        {
                            self.notes.insert(id, self.note_edit.clone());
                        } else {
                            self.close_overlay();
                            self.confirm("Limite des notes locales atteinte ; note conservée sans modification.");
                            return Action::None;
                        }
                    }
                    self.close_overlay();
                    self.confirm("Note locale enregistrée.");
                }
                KeyCode::Backspace => {
                    self.note_edit.pop();
                }
                KeyCode::Char(c) if !c.is_control() && self.note_edit.chars().count() < 500 => {
                    self.note_edit.push(c)
                }
                _ => {}
            }
            return Action::None;
        }
        if self.overlay == Overlay::Actions {
            match key.code {
                KeyCode::Esc | KeyCode::Char('a') => self.close_overlay(),
                KeyCode::Up => self.menu_selected = self.menu_selected.saturating_sub(1),
                KeyCode::Down => {
                    self.menu_selected =
                        (self.menu_selected + 1).min(self.menu_items().len().saturating_sub(1));
                    self.scroll = self
                        .menu_selected
                        .saturating_sub(self.scroll_page as usize / 2)
                        as u16;
                }
                KeyCode::Enter => return self.menu_action(),
                _ => {}
            }
            return Action::None;
        }
        if self.overlay == Overlay::Favorites {
            match key.code {
                KeyCode::Esc => self.close_overlay(),
                KeyCode::Up => self.menu_selected = self.menu_selected.saturating_sub(1),
                KeyCode::Down => {
                    self.menu_selected =
                        (self.menu_selected + 1).min(self.favorites.len().saturating_sub(1));
                    self.scroll = self
                        .menu_selected
                        .saturating_sub(self.scroll_page as usize / 2)
                        as u16;
                }
                KeyCode::Enter => {
                    if let Some(id) = self.favorites.iter().nth(self.menu_selected).cloned() {
                        self.close_overlay();
                        self.switch_view(View::Dossier);
                        self.set_query(id.clone());
                        self.pending_detail = Some((View::Dossier, id));
                    }
                }
                _ => {}
            }
            return Action::None;
        }
        if self.editing {
            let before = self.query().to_owned();
            let index = self.view.filter_index().expect("Only lists have an editor");
            match key.code {
                KeyCode::Esc => {
                    self.filters[index].clear();
                    self.editing = false;
                }
                KeyCode::Enter => {
                    self.editing = false;
                    self.debounce_until = None;
                }
                KeyCode::Backspace => {
                    self.filters[index].pop();
                    self.replace_filter = false;
                }
                KeyCode::Char('u') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    self.filters[index].clear()
                }
                KeyCode::Char(c) if !c.is_control() => {
                    if self.replace_filter {
                        self.filters[index].clear();
                        self.replace_filter = false;
                    }
                    if self.filters[index].chars().count() < 80 {
                        self.filters[index].push(c);
                    }
                }
                _ => {}
            }
            if let Some(table) = self.table() {
                table.select(Some(0));
            }
            if self.query() != before {
                let page = self.collection_index().unwrap_or(index);
                self.pages[page] = 0;
                self.anchor_allowed[page] = false;
                self.mark_read(false);
                self.debounce_until =
                    Some(std::time::Instant::now() + std::time::Duration::from_millis(180));
                return Action::None;
            }
            return Action::None;
        }
        if key.code == KeyCode::Char('q') {
            return Action::Quit;
        }
        if key.code == KeyCode::Char('r') {
            self.error = None;
            self.debounce_until = None;
            self.mark_read(true);
            return Action::Refresh;
        }
        if self.overlay != Overlay::None {
            match key.code {
                KeyCode::Esc => self.close_overlay(),
                KeyCode::Char('?') if self.overlay == Overlay::Help => self.close_overlay(),
                KeyCode::Char('!') if self.overlay == Overlay::Alerts => self.close_overlay(),
                KeyCode::Enter if self.overlay == Overlay::Details => self.close_overlay(),
                _ => self.scroll_key(key.code),
            }
            return Action::None;
        }
        if (self.view == View::Updates
            || (self.view == View::Overview && self.data.schema != 3)
            || (self.focus == Panel::Detail && self.split_visible))
            && matches!(
                key.code,
                KeyCode::Up
                    | KeyCode::Down
                    | KeyCode::PageUp
                    | KeyCode::PageDown
                    | KeyCode::Home
                    | KeyCode::End
                    | KeyCode::Char('j')
                    | KeyCode::Char('k')
            )
        {
            self.scroll_key(key.code);
            return Action::None;
        }
        match key.code {
            KeyCode::Char('p') => self.paused = !self.paused,
            KeyCode::Char('a') => {
                self.menu_selected = 0;
                self.open(Overlay::Actions);
            }
            KeyCode::Char('*') => self.toggle_favorite(),
            KeyCode::Char('f') => {
                self.menu_selected = 0;
                self.open(Overlay::Favorites);
            }
            KeyCode::Char('X') if self.action_busy => return Action::Cancel,
            KeyCode::Char('N') => self.edit_note(),
            KeyCode::Char('P') => self.anonymized = !self.anonymized,
            KeyCode::Char('w') => self.id_width = self.id_width.saturating_sub(1).max(7),
            KeyCode::Char('W') => self.id_width = (self.id_width + 1).min(32),
            KeyCode::Char('s') => self.cycle_sort(),
            KeyCode::Char('n') => self.page(true),
            KeyCode::Char('b') => self.page(false),
            KeyCode::Char('v') => {
                self.layout = if self.layout == LayoutMode::Split {
                    LayoutMode::List
                } else {
                    LayoutMode::Split
                };
                self.focus = Panel::List;
                self.scroll = 0;
            }
            KeyCode::F(6) if self.split_visible => {
                self.focus = if self.focus == Panel::List {
                    Panel::Detail
                } else {
                    Panel::List
                };
                self.scroll = 0;
            }
            KeyCode::Char('[') => {
                self.detail_percent = self.detail_percent.saturating_sub(5).max(25)
            }
            KeyCode::Char(']') => self.detail_percent = (self.detail_percent + 5).min(65),
            KeyCode::Char('c') => return Action::Copy(false),
            KeyCode::Char('C') => return Action::Copy(true),
            KeyCode::Char('e') => return Action::Export,
            KeyCode::Char('?') => self.open(Overlay::Help),
            KeyCode::Char('!') => self.open(Overlay::Alerts),
            KeyCode::Enter if self.view == View::Overview && self.data.schema == 3 => {
                self.open_alert();
                return Action::Refresh;
            }
            KeyCode::Enter if self.view != View::Updates => self.open(Overlay::Details),
            KeyCode::Char('/') if self.view.filter_index().is_some() => {
                self.editing = true;
                self.replace_filter = true;
            }
            KeyCode::Esc => {
                if let Some(index) = self.view.filter_index() {
                    self.filters[index].clear();
                    let page = self.collection_index().unwrap_or(index);
                    self.pages[page] = 0;
                    self.anchor_allowed[page] = false;
                    self.mark_read(false);
                }
                if let Some(table) = self.table() {
                    table.select(Some(0));
                }
            }
            KeyCode::Tab | KeyCode::Right => {
                self.switch_view(View::from_index(self.view.index() + 1))
            }
            KeyCode::BackTab | KeyCode::Left => {
                self.switch_view(View::from_index(self.view.index() + 8))
            }
            KeyCode::Char(c @ '1'..='9') => {
                self.switch_view(View::from_index(c as usize - '1' as usize))
            }
            KeyCode::Down | KeyCode::Char('j') => self.move_row(1),
            KeyCode::Up | KeyCode::Char('k') => self.move_row(-1),
            KeyCode::PageDown => self.move_row(self.page_rows as isize),
            KeyCode::PageUp => self.move_row(-(self.page_rows as isize)),
            KeyCode::Home => {
                if let Some(table) = self.table() {
                    table.select(Some(0));
                }
                self.mark_read(false);
            }
            KeyCode::End => {
                let last = self.row_count().checked_sub(1);
                if let Some(table) = self.table() {
                    table.select(last);
                }
                self.mark_read(false);
            }
            _ => {}
        }
        Action::None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{Job, Notification, Session, Snapshot};

    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::NONE)
    }
    fn sample() -> App {
        let mut app = App::new(View::Dossier);
        app.apply(Snapshot {
            jobs: vec![
                Job {
                    id: "42".into(),
                    state: "RUNNING".into(),
                    ..Default::default()
                },
                Job {
                    id: "43".into(),
                    state: "RUNNING".into(),
                    ..Default::default()
                },
            ],
            ..Default::default()
        });
        app.collect_read = false;
        app
    }

    #[test]
    fn search_is_debounced_and_selection_changes_request_the_selected_dossier() {
        let mut app = sample();
        app.key(key(KeyCode::End));
        assert_eq!(app.read_request().detail_job, "43");
        assert!(!app.read_request().collect);
        app.key(key(KeyCode::Home));
        assert_eq!(app.read_request().detail_job, "42");
        app.key(key(KeyCode::Char('/')));
        app.key(key(KeyCode::Char('x')));
        assert!(app.debounce_until.is_some());
        assert!(!app.collect_read);
        app.key(key(KeyCode::Enter));
        assert!(app.debounce_until.is_none());
        app.key(key(KeyCode::Char('r')));
        assert!(app.read_request().collect && app.read_request().force);
    }

    #[test]
    fn notes_are_explicit_cancellable_and_hidden_in_presentation() {
        let mut app = sample();
        app.key(key(KeyCode::Char('*')));
        assert!(app.favorites.contains("42"));
        app.key(key(KeyCode::Char('N')));
        app.key(key(KeyCode::Char('é')));
        app.key(key(KeyCode::Esc));
        assert!(app.notes.is_empty());
        app.key(key(KeyCode::Char('N')));
        app.key(key(KeyCode::Char('é')));
        app.key(key(KeyCode::Enter));
        assert_eq!(app.notes["42"], "é");
        app.key(key(KeyCode::Char('P')));
        app.key(key(KeyCode::Char('N')));
        assert_eq!(app.overlay, Overlay::None);
        assert_eq!(app.notes["42"], "é");
    }

    #[test]
    fn annotation_keeps_its_original_job_when_refresh_changes_selection() {
        let mut app = sample();
        app.key(key(KeyCode::Char('N')));
        app.note_edit = "Original job annotation".into();
        assert_eq!(app.note_target.as_deref(), Some("42"));
        app.apply(Snapshot {
            jobs: vec![Job {
                id: "43".into(),
                state: "RUNNING".into(),
                ..Default::default()
            }],
            ..Default::default()
        });
        assert_eq!(app.selected_job().unwrap().id, "43");
        app.key(key(KeyCode::Enter));
        assert_eq!(app.notes["42"], "Original job annotation");
        assert!(!app.notes.contains_key("43"));
        assert!(app.note_target.is_none());
        assert!(app.note_edit.is_empty());
    }

    #[test]
    fn favorites_wait_for_a_complete_page_and_keep_the_exact_identity() {
        let mut app = sample();
        app.favorites.insert("1001".into());
        app.key(key(KeyCode::Char('f')));
        app.key(key(KeyCode::Enter));
        assert_eq!(app.read_request().detail_job, "1001");
        app.apply(Snapshot {
            schema: 3,
            request_id: app.revision,
            partial: true,
            ..Default::default()
        });
        assert!(app.pending_detail.is_some());
        app.apply(Snapshot {
            schema: 3,
            request_id: app.revision,
            jobs: vec![Job {
                id: "1001".into(),
                ..Default::default()
            }],
            ..Default::default()
        });
        assert_eq!(app.overlay, Overlay::Details);
        assert_eq!(app.copy_value(false), Some("1001".into()));
    }

    #[test]
    fn remote_menu_actions_use_only_the_visible_job_or_session() {
        let mut app = sample();
        assert!(app.menu_items().iter().any(|item| item.1 == "status"));
        app.key(key(KeyCode::Char('3')));
        assert!(!app
            .menu_items()
            .iter()
            .any(|item| matches!(item.1, "status" | "efficiency" | "remote_logs" | "resume")));
        app.key(key(KeyCode::Char('9')));
        app.data.sessions = vec![Session {
            name: "allocation".into(),
            job_id: "42".into(),
            ..Default::default()
        }];
        assert!(app.menu_items().iter().any(|item| item.1 == "allocation"));
        assert!(!app.menu_items().iter().any(|item| item.1 == "service"));
    }

    #[test]
    fn notifications_are_optional_deduplicated_and_confirmations_expire() {
        let mut app = sample();
        app.data.generated_at = 1.0;
        let snapshot = Snapshot {
            generated_at: 2.0,
            notifications: vec![Notification {
                key: "event".into(),
                job_id: "42".into(),
                message: "Terminé".into(),
                observed_at: Some(1.0),
            }],
            ..Default::default()
        };
        app.notify_changes(&snapshot);
        assert!(app.notification_log.is_empty());
        app.notifications = true;
        app.notify_changes(&snapshot);
        assert!(app.notification_log.is_empty());
        app.seen_notifications.clear();
        app.notify_changes(&snapshot);
        app.notify_changes(&snapshot);
        assert_eq!(app.notification_log.len(), 1);
        app.seen_notifications
            .extend((0..5001).map(|n| format!("old-{n}")));
        app.notify_changes(&snapshot);
        app.notify_changes(&snapshot);
        assert_eq!(app.notification_log.len(), 1);
        app.notice_until = Some(std::time::Instant::now());
        assert!(app.expire_confirmation());
        assert!(app.notice.is_none());
        assert!(app
            .last_confirmation
            .as_deref()
            .unwrap()
            .contains("Terminé"));
    }
}
