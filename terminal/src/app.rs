//! Keyboard navigation and selection, independent of terminal IO and rendering.
use crate::model::{Job, Snapshot, Transfer};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::widgets::TableState;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum View {
    Overview,
    Jobs,
    Transfers,
    Updates,
}

impl View {
    pub fn index(self) -> usize {
        match self {
            Self::Overview => 0,
            Self::Jobs => 1,
            Self::Transfers => 2,
            Self::Updates => 3,
        }
    }

    pub fn from_index(index: usize) -> Self {
        [Self::Overview, Self::Jobs, Self::Transfers, Self::Updates][index % 4]
    }
}

#[derive(Default, Debug, PartialEq, Eq)]
pub enum Action {
    #[default]
    None,
    Refresh,
    Quit,
}

pub struct App {
    pub data: Snapshot,
    pub view: View,
    pub query: String,
    pub editing: bool,
    pub help: bool,
    pub paused: bool,
    pub loading: bool,
    pub error: Option<String>,
    pub jobs_table: TableState,
    pub transfers_table: TableState,
}

impl App {
    pub fn new(view: View) -> Self {
        Self {
            data: Snapshot::default(),
            view,
            query: String::new(),
            editing: false,
            help: false,
            paused: false,
            loading: true,
            error: None,
            jobs_table: TableState::default().with_selected(0),
            transfers_table: TableState::default().with_selected(0),
        }
    }

    pub fn jobs(&self) -> Vec<&Job> {
        let query = self.query.to_lowercase();
        self.data
            .jobs
            .iter()
            .filter(|row| {
                format!("{} {} {} {}", row.id, row.name, row.state, row.partition)
                    .to_lowercase()
                    .contains(&query)
            })
            .collect()
    }

    pub fn transfers(&self) -> Vec<&Transfer> {
        let query = self.query.to_lowercase();
        self.data
            .transfers
            .iter()
            .filter(|row| {
                format!("{} {} {} {}", row.id, row.name, row.state, row.direction)
                    .to_lowercase()
                    .contains(&query)
            })
            .collect()
    }

    pub fn apply(&mut self, snapshot: Snapshot) {
        let job = self
            .jobs()
            .get(self.jobs_table.selected().unwrap_or(0))
            .map(|row| row.id.clone());
        let transfer = self
            .transfers()
            .get(self.transfers_table.selected().unwrap_or(0))
            .map(|row| row.id.clone());
        self.data = snapshot;
        let job_index = self
            .jobs()
            .iter()
            .position(|row| Some(&row.id) == job.as_ref())
            .unwrap_or(0);
        let transfer_index = self
            .transfers()
            .iter()
            .position(|row| Some(&row.id) == transfer.as_ref())
            .unwrap_or(0);
        self.jobs_table.select(Some(job_index));
        self.transfers_table.select(Some(transfer_index));
        self.loading = false;
        self.error = None;
    }

    fn move_row(&mut self, delta: isize) {
        let (length, table) = match self.view {
            View::Jobs => (self.jobs().len(), &mut self.jobs_table),
            View::Transfers => (self.transfers().len(), &mut self.transfers_table),
            _ => return,
        };
        if length == 0 {
            table.select(None);
            return;
        }
        let selected = table.selected().unwrap_or(0) as isize;
        table.select(Some((selected + delta).rem_euclid(length as isize) as usize));
    }

    pub fn key(&mut self, key: KeyEvent) -> Action {
        if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
            return Action::Quit;
        }
        if self.editing {
            match key.code {
                KeyCode::Esc | KeyCode::Enter => self.editing = false,
                KeyCode::Backspace => {
                    self.query.pop();
                }
                KeyCode::Char(c) if !c.is_control() && self.query.chars().count() < 80 => {
                    self.query.push(c)
                }
                _ => {}
            }
            self.jobs_table.select(Some(0));
            self.transfers_table.select(Some(0));
            return Action::None;
        }
        if self.help {
            match key.code {
                KeyCode::Esc | KeyCode::Char('?') => self.help = false,
                KeyCode::Char('q') => return Action::Quit,
                _ => {}
            }
            return Action::None;
        }
        match key.code {
            KeyCode::Char('q') => return Action::Quit,
            KeyCode::Char('r') => return Action::Refresh,
            KeyCode::Char('p') => self.paused = !self.paused,
            KeyCode::Char('?') => self.help = true,
            KeyCode::Char('/') if matches!(self.view, View::Jobs | View::Transfers) => {
                self.editing = true
            }
            KeyCode::Esc => {
                self.query.clear();
                self.jobs_table.select(Some(0));
                self.transfers_table.select(Some(0));
            }
            KeyCode::Tab | KeyCode::Right => self.view = View::from_index(self.view.index() + 1),
            KeyCode::BackTab | KeyCode::Left => self.view = View::from_index(self.view.index() + 3),
            KeyCode::Char(c @ '1'..='4') => self.view = View::from_index(c as usize - '1' as usize),
            KeyCode::Down | KeyCode::Char('j') => self.move_row(1),
            KeyCode::Up | KeyCode::Char('k') => self.move_row(-1),
            KeyCode::Home => match self.view {
                View::Jobs => self.jobs_table.select(Some(0)),
                View::Transfers => self.transfers_table.select(Some(0)),
                _ => {}
            },
            KeyCode::End => match self.view {
                View::Jobs => self.jobs_table.select(self.jobs().len().checked_sub(1)),
                View::Transfers => self
                    .transfers_table
                    .select(self.transfers().len().checked_sub(1)),
                _ => {}
            },
            _ => {}
        }
        Action::None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::NONE)
    }

    fn job(id: &str) -> Job {
        Job {
            id: id.to_owned(),
            name: format!("Simulation {id}"),
            partition: "cpu".to_owned(),
            state: "RUNNING".to_owned(),
            submitted_at: None,
            observed_at: None,
            elapsed: String::new(),
            remaining: String::new(),
            exit_code: String::new(),
            result_validated: false,
        }
    }

    #[test]
    fn refresh_preserves_selected_identity_when_rows_reorder() {
        let mut app = App::new(View::Jobs);
        app.apply(Snapshot {
            jobs: vec![job("101"), job("102")],
            ..Snapshot::default()
        });
        app.key(key(KeyCode::Down));
        assert_eq!(app.jobs()[app.jobs_table.selected().unwrap()].id, "102");
        app.apply(Snapshot {
            jobs: vec![job("102"), job("101")],
            ..Snapshot::default()
        });
        assert_eq!(app.jobs_table.selected(), Some(0));
        assert_eq!(app.jobs()[app.jobs_table.selected().unwrap()].id, "102");
    }

    #[test]
    fn filter_and_disappearing_selection_remain_usable() {
        let mut app = App::new(View::Jobs);
        app.apply(Snapshot {
            jobs: vec![job("101"), job("102")],
            ..Snapshot::default()
        });
        app.query = "102".to_owned();
        assert_eq!(app.jobs().len(), 1);
        app.apply(Snapshot {
            jobs: vec![job("101")],
            ..Snapshot::default()
        });
        app.key(key(KeyCode::Down));
        assert_eq!(app.jobs_table.selected(), None);
        app.key(key(KeyCode::Esc));
        app.key(key(KeyCode::Down));
        assert_eq!(app.jobs_table.selected(), Some(0));
    }

    #[test]
    fn navigation_search_and_pause_do_not_request_mutations() {
        let mut app = App::new(View::Overview);
        app.key(key(KeyCode::Tab));
        assert_eq!(app.view, View::Jobs);
        app.key(key(KeyCode::Char('/')));
        assert_eq!(app.key(key(KeyCode::Char('q'))), Action::None);
        assert_eq!(app.query, "q");
        app.key(key(KeyCode::Enter));
        app.key(key(KeyCode::Esc));
        assert!(app.query.is_empty());
        app.key(key(KeyCode::Char('p')));
        assert!(app.paused);
        assert_eq!(app.key(key(KeyCode::Char('r'))), Action::Refresh);
        assert_eq!(app.key(key(KeyCode::Char('q'))), Action::Quit);
    }

    #[test]
    fn empty_lists_and_reverse_tabs_are_safe() {
        let mut app = App::new(View::Overview);
        app.key(key(KeyCode::BackTab));
        assert_eq!(app.view, View::Updates);
        app.key(key(KeyCode::Char('2')));
        app.key(key(KeyCode::Up));
        assert_eq!(app.jobs_table.selected(), None);
        assert_eq!(
            app.key(KeyEvent::new(KeyCode::Char('c'), KeyModifiers::CONTROL)),
            Action::Quit
        );
    }
}
