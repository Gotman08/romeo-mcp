//! Bounded text editing. A pasted block never becomes navigation or execution keys.
use super::{App, KeyCode, KeyEvent, KeyModifiers, Overlay};

fn normalized(value: &str) -> impl Iterator<Item = char> + '_ {
    value.chars().map(|c| {
        if c.is_control() || matches!(c, '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}') {
            ' '
        } else {
            c
        }
    })
}

impl App {
    fn note_byte(&self, position: usize) -> usize {
        self.note_edit
            .char_indices()
            .nth(position)
            .map_or(self.note_edit.len(), |(index, _)| index)
    }

    fn insert_note(&mut self, value: &str) {
        let count = self.note_edit.chars().count();
        self.note_cursor = self.note_cursor.min(count);
        let inserted: String = normalized(value)
            .take(500usize.saturating_sub(count))
            .collect();
        let at = self.note_byte(self.note_cursor);
        self.note_cursor += inserted.chars().count();
        self.note_edit.insert_str(at, &inserted);
    }

    pub fn paste(&mut self, value: &str) {
        if self.overlay == Overlay::Note {
            self.insert_note(value);
        } else if self.editing && self.overlay == Overlay::None {
            let mut query = if self.replace_filter {
                String::new()
            } else {
                self.query().to_owned()
            };
            query.extend(normalized(value).take(80usize.saturating_sub(query.chars().count())));
            self.replace_filter = false;
            self.set_query(query);
            if let Some(table) = self.table() {
                table.select(Some(0));
            }
            self.debounce_until =
                Some(std::time::Instant::now() + std::time::Duration::from_millis(180));
        }
    }

    pub(super) fn note_key(&mut self, key: KeyEvent) {
        self.note_cursor = self.note_cursor.min(self.note_edit.chars().count());
        match key.code {
            KeyCode::Esc => self.close_overlay(),
            KeyCode::Enter => self.insert_note(" "),
            KeyCode::Char('s') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.note_key(KeyEvent::new(KeyCode::F(2), KeyModifiers::NONE));
            }
            KeyCode::F(2) => {
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
                        self.confirm(
                            "Limite des notes locales atteinte ; note conservée sans modification.",
                        );
                        return;
                    }
                }
                self.close_overlay();
                self.confirm("Note locale enregistrée.");
            }
            KeyCode::Left => self.note_cursor = self.note_cursor.saturating_sub(1),
            KeyCode::Right => {
                self.note_cursor = (self.note_cursor + 1).min(self.note_edit.chars().count())
            }
            KeyCode::Home => self.note_cursor = 0,
            KeyCode::End => self.note_cursor = self.note_edit.chars().count(),
            KeyCode::Backspace if self.note_cursor > 0 => {
                let end = self.note_byte(self.note_cursor);
                self.note_cursor -= 1;
                let start = self.note_byte(self.note_cursor);
                self.note_edit.replace_range(start..end, "");
            }
            KeyCode::Delete => {
                let start = self.note_byte(self.note_cursor);
                let end = self.note_byte(self.note_cursor + 1);
                self.note_edit.replace_range(start..end, "");
            }
            KeyCode::Char(c)
                if !c.is_control()
                    && !key
                        .modifiers
                        .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT) =>
            {
                self.insert_note(&c.to_string());
            }
            _ => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        app::View,
        model::{Job, Snapshot},
    };

    fn editor() -> App {
        let mut app = App::new(View::Jobs);
        app.apply(Snapshot {
            jobs: vec![Job {
                id: "42".into(),
                ..Default::default()
            }],
            ..Default::default()
        });
        app.key(KeyEvent::new(KeyCode::Char('N'), KeyModifiers::NONE));
        app
    }

    #[test]
    fn multiline_paste_stays_in_the_editor_and_is_saved_only_explicitly() {
        let mut app = editor();
        app.paste("first\rq\n*e");
        assert_eq!(app.overlay, Overlay::Note);
        assert!(app.notes.is_empty());
        assert!(app.favorites.is_empty());
        assert_eq!(app.note_edit, "first q *e");
        app.key(KeyEvent::new(KeyCode::F(2), KeyModifiers::NONE));
        assert_eq!(app.notes["42"], "first q *e");
    }

    #[test]
    fn plain_windows_multiline_input_cannot_save_or_quit_the_note() {
        let mut app = editor();
        for code in [KeyCode::Char('a'), KeyCode::Enter, KeyCode::Char('q')] {
            assert_eq!(
                app.key(KeyEvent::new(code, KeyModifiers::NONE)),
                super::super::Action::None
            );
        }
        assert_eq!(app.overlay, Overlay::Note);
        assert!(app.notes.is_empty());
        assert_eq!(app.note_edit, "a q");
        app.key(KeyEvent::new(KeyCode::Char('s'), KeyModifiers::CONTROL));
        assert_eq!(app.notes["42"], "a q");
    }

    #[test]
    fn cursor_edits_unicode_without_splitting_utf8_and_limits_paste() {
        let mut app = editor();
        app.paste("é🙂Z");
        app.note_key(KeyEvent::new(KeyCode::Left, KeyModifiers::NONE));
        app.note_key(KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE));
        assert_eq!(app.note_edit, "éZ");
        app.paste("界");
        assert_eq!(app.note_edit, "é界Z");
        app.note_key(KeyEvent::new(KeyCode::Home, KeyModifiers::NONE));
        app.note_key(KeyEvent::new(KeyCode::Delete, KeyModifiers::NONE));
        assert_eq!(app.note_edit, "界Z");
        app.paste(&"a".repeat(1000));
        assert_eq!(app.note_edit.chars().count(), 500);
        assert!(app.note_edit.ends_with("界Z"));
    }

    #[test]
    fn search_paste_is_bounded_and_does_not_trigger_view_keys() {
        let mut app = editor();
        app.close_overlay();
        app.key(KeyEvent::new(KeyCode::Char('/'), KeyModifiers::NONE));
        app.paste(&format!("COMPLETED\rq9{}", "x".repeat(100)));
        assert_eq!(app.view, View::Jobs);
        assert!(app.editing);
        assert_eq!(app.query().chars().count(), 80);
        assert!(app.query().starts_with("COMPLETED q9"));
        assert!(app.debounce_until.is_some());
    }
}
