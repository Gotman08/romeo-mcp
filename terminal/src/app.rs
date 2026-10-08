//! View-local filters and keyboard navigation, independent of terminal IO.
use crate::{
    color::Palette,
    model::{now, Job, Report, Snapshot, Transfer},
    query::{self, Key, SortOrder},
    status::{self, job_state, report_state, transfer_state},
};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::widgets::TableState;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum View {
    Overview,
    Jobs,
    Transfers,
    Updates,
    Reports,
}

impl View {
    pub fn index(self) -> usize {
        match self {
            Self::Overview => 0,
            Self::Jobs => 1,
            Self::Transfers => 2,
            Self::Updates => 3,
            Self::Reports => 4,
        }
    }
    pub fn from_index(index: usize) -> Self {
        [
            Self::Overview,
            Self::Jobs,
            Self::Transfers,
            Self::Updates,
            Self::Reports,
        ][index % 5]
    }
    fn filter_index(self) -> Option<usize> {
        match self {
            Self::Jobs => Some(0),
            Self::Transfers => Some(1),
            Self::Reports => Some(2),
            _ => None,
        }
    }
}

#[derive(Default, Debug, PartialEq, Eq)]
pub enum Action {
    #[default]
    None,
    Refresh,
    Quit,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Overlay {
    #[default]
    None,
    Help,
    Details,
    Alerts,
}

pub struct App {
    pub data: Snapshot,
    pub view: View,
    filters: [String; 3],
    sorts: [SortOrder; 3],
    sort_at: f64,
    pub editing: bool,
    replace_filter: bool,
    pub overlay: Overlay,
    pub scroll: u16,
    pub scroll_max: u16,
    pub scroll_page: u16,
    saved_scroll: (u16, u16, u16),
    pub paused: bool,
    pub loading: bool,
    pub error: Option<String>,
    pub jobs_table: TableState,
    pub transfers_table: TableState,
    pub reports_table: TableState,
    pub page_rows: usize,
    pub refresh_seconds: u64,
    pub palette: Palette,
}

impl App {
    pub fn new(view: View) -> Self {
        Self {
            data: Snapshot::default(),
            view,
            filters: Default::default(),
            sorts: Default::default(),
            sort_at: now(),
            editing: false,
            replace_filter: false,
            overlay: Overlay::None,
            scroll: 0,
            scroll_max: 0,
            scroll_page: 8,
            saved_scroll: (0, 0, 8),
            paused: false,
            loading: true,
            error: None,
            jobs_table: TableState::default().with_selected(0),
            transfers_table: TableState::default().with_selected(0),
            reports_table: TableState::default().with_selected(0),
            page_rows: 8,
            refresh_seconds: 5,
            palette: Palette::default(),
        }
    }

    pub fn query(&self) -> &str {
        self.view
            .filter_index()
            .map(|index| self.filters[index].as_str())
            .unwrap_or("")
    }

    pub fn jobs(&self) -> Vec<&Job> {
        let query = query::normalize(&self.filters[0]);
        self.ordered_jobs(&query, self.sorts[0])
    }

    pub fn recent_jobs(&self) -> Vec<&Job> {
        self.ordered_jobs("", SortOrder::Date)
    }

    fn ordered_jobs(&self, query: &str, sort: SortOrder) -> Vec<&Job> {
        let rows = self
            .data
            .jobs
            .iter()
            .filter(|row| {
                query::matches(
                    query,
                    &[
                        &row.id,
                        &row.name,
                        &row.state,
                        &row.partition,
                        job_state(&row.state),
                        status::job_validation(row).label(),
                    ],
                )
            })
            .collect();
        let at = self.sort_at;
        query::order(rows, sort, |row| {
            Key::new(
                status::priority(&row.state, status::job_attention(row, at).is_some()),
                row.observed_at.or(row.submitted_at),
                job_state(&row.state),
                &row.id,
            )
        })
    }

    pub fn transfers(&self) -> Vec<&Transfer> {
        let query = query::normalize(&self.filters[1]);
        let rows = self
            .data
            .transfers
            .iter()
            .filter(|row| {
                query::matches(
                    &query,
                    &[
                        &row.id,
                        &row.name,
                        &row.state,
                        &row.direction,
                        transfer_state(&row.state),
                        &row.local_path,
                        &row.remote_path,
                        if row.direction == "upload" {
                            "vers ROMEO"
                        } else {
                            "depuis ROMEO"
                        },
                    ],
                )
            })
            .collect();
        let at = self.sort_at;
        query::order(rows, self.sorts[1], |row| {
            Key::new(
                status::priority(&row.state, status::transfer_attention(row, at).is_some()),
                row.observed_at,
                transfer_state(&row.state),
                &row.id,
            )
        })
    }

    pub fn reports(&self) -> Vec<&Report> {
        let query = query::normalize(&self.filters[2]);
        let rows = self
            .data
            .reports
            .items
            .iter()
            .filter(|row| {
                query::matches(
                    &query,
                    &[
                        &row.id,
                        &row.summary,
                        &row.state,
                        &row.category,
                        report_state(&row.state),
                    ],
                )
            })
            .collect();
        query::order(rows, self.sorts[2], |row| {
            Key::new(
                status::priority(&row.state, !row.result_validated),
                row.observed_at,
                report_state(&row.state),
                &row.id,
            )
        })
    }

    pub fn sort_order(&self) -> SortOrder {
        self.view
            .filter_index()
            .map(|index| self.sorts[index])
            .unwrap_or_default()
    }

    fn selected_ids(&self) -> [Option<String>; 3] {
        let job = self
            .jobs()
            .get(self.jobs_table.selected().unwrap_or(0))
            .map(|row| row.id.clone());
        let transfer = self
            .transfers()
            .get(self.transfers_table.selected().unwrap_or(0))
            .map(|row| row.id.clone());
        let report = self
            .reports()
            .get(self.reports_table.selected().unwrap_or(0))
            .map(|row| row.id.clone());
        [job, transfer, report]
    }

    fn restore_selection(&mut self, [job, transfer, report]: [Option<String>; 3]) {
        self.jobs_table.select(
            self.jobs()
                .iter()
                .position(|row| Some(&row.id) == job.as_ref())
                .or(Some(0)),
        );
        self.transfers_table.select(
            self.transfers()
                .iter()
                .position(|row| Some(&row.id) == transfer.as_ref())
                .or(Some(0)),
        );
        self.reports_table.select(
            self.reports()
                .iter()
                .position(|row| Some(&row.id) == report.as_ref())
                .or(Some(0)),
        );
    }

    pub fn apply(&mut self, snapshot: Snapshot) {
        let selection = self.selected_ids();
        self.data = snapshot;
        self.sort_at = now();
        self.restore_selection(selection);
        self.loading = false;
        self.error = None;
    }

    fn cycle_sort(&mut self) {
        if let Some(index) = self.view.filter_index() {
            let selection = self.selected_ids();
            self.sorts[index] = self.sorts[index].next();
            self.restore_selection(selection);
        }
    }

    fn table(&mut self) -> Option<&mut TableState> {
        match self.view {
            View::Jobs => Some(&mut self.jobs_table),
            View::Transfers => Some(&mut self.transfers_table),
            View::Reports => Some(&mut self.reports_table),
            _ => None,
        }
    }

    fn row_count(&self) -> usize {
        match self.view {
            View::Jobs => self.jobs().len(),
            View::Transfers => self.transfers().len(),
            View::Reports => self.reports().len(),
            _ => 0,
        }
    }

    fn move_row(&mut self, delta: isize) {
        let length = self.row_count();
        if let Some(table) = self.table() {
            if length == 0 {
                table.select(None);
                return;
            }
            let selected = table.selected().unwrap_or(0) as isize;
            table.select(Some(
                (selected + delta).clamp(0, length as isize - 1) as usize
            ));
        }
    }

    fn scroll_key(&mut self, code: KeyCode) {
        self.scroll = match code {
            KeyCode::Up | KeyCode::Char('k') => self.scroll.saturating_sub(1),
            KeyCode::Down | KeyCode::Char('j') => self.scroll.saturating_add(1),
            KeyCode::PageUp => self.scroll.saturating_sub(self.scroll_page),
            KeyCode::PageDown => self.scroll.saturating_add(self.scroll_page),
            KeyCode::Home => 0,
            KeyCode::End => self.scroll_max,
            _ => self.scroll,
        }
        .min(self.scroll_max);
    }

    fn open(&mut self, overlay: Overlay) {
        self.saved_scroll = (self.scroll, self.scroll_max, self.scroll_page);
        self.overlay = overlay;
        self.scroll = 0;
    }

    fn close_overlay(&mut self) {
        self.overlay = Overlay::None;
        (self.scroll, self.scroll_max, self.scroll_page) = self.saved_scroll;
    }

    fn switch_view(&mut self, view: View) {
        self.view = view;
        self.scroll = 0;
        self.scroll_max = 0;
    }

    pub fn key(&mut self, key: KeyEvent) -> Action {
        if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
            return Action::Quit;
        }
        if self.editing {
            let index = self.view.filter_index().expect("Only lists have an editor");
            match key.code {
                KeyCode::Esc => {
                    self.filters[index].clear();
                    self.editing = false;
                }
                KeyCode::Enter => self.editing = false,
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
            return Action::None;
        }
        if key.code == KeyCode::Char('q') {
            return Action::Quit;
        }
        if key.code == KeyCode::Char('r') {
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
        if matches!(self.view, View::Overview | View::Updates)
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
            KeyCode::Char('s') => self.cycle_sort(),
            KeyCode::Char('?') => self.open(Overlay::Help),
            KeyCode::Char('!') => self.open(Overlay::Alerts),
            KeyCode::Enter if self.view != View::Updates => self.open(Overlay::Details),
            KeyCode::Char('/') if self.view.filter_index().is_some() => {
                self.editing = true;
                self.replace_filter = true;
            }
            KeyCode::Esc => {
                if let Some(index) = self.view.filter_index() {
                    self.filters[index].clear();
                }
                if let Some(table) = self.table() {
                    table.select(Some(0));
                }
            }
            KeyCode::Tab | KeyCode::Right => {
                self.switch_view(View::from_index(self.view.index() + 1))
            }
            KeyCode::BackTab | KeyCode::Left => {
                self.switch_view(View::from_index(self.view.index() + 4))
            }
            KeyCode::Char(c @ '1'..='5') => {
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
            }
            KeyCode::End => {
                let last = self.row_count().checked_sub(1);
                if let Some(table) = self.table() {
                    table.select(last);
                }
            }
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
            id: id.into(),
            name: format!("Simulation {id}"),
            state: "RUNNING".into(),
            ..Job::default()
        }
    }

    #[test]
    fn refresh_preserves_selection_by_identity() {
        let mut app = App::new(View::Jobs);
        app.apply(Snapshot {
            jobs: vec![job("101"), job("102")],
            ..Snapshot::default()
        });
        app.key(key(KeyCode::Down));
        app.apply(Snapshot {
            jobs: vec![job("102"), job("101")],
            ..Snapshot::default()
        });
        assert_eq!(app.jobs()[app.jobs_table.selected().unwrap()].id, "102");
    }

    #[test]
    fn filters_do_not_leak_across_views_and_escape_clears_once() {
        let mut app = App::new(View::Jobs);
        app.key(key(KeyCode::Char('/')));
        app.key(key(KeyCode::Char('x')));
        app.key(key(KeyCode::Enter));
        assert_eq!(app.query(), "x");
        app.key(key(KeyCode::Char('3')));
        assert_eq!(app.query(), "");
        app.key(key(KeyCode::Char('2')));
        assert_eq!(app.query(), "x");
        app.key(key(KeyCode::Char('/')));
        app.key(key(KeyCode::Char('y')));
        assert_eq!(app.query(), "y");
        app.key(key(KeyCode::Esc));
        assert_eq!(app.query(), "");
        assert!(!app.editing);
    }

    #[test]
    fn pagination_empty_lists_and_overlays_remain_usable() {
        let mut app = App::new(View::Jobs);
        app.apply(Snapshot {
            jobs: (0..30).map(|id| job(&id.to_string())).collect(),
            ..Snapshot::default()
        });
        app.page_rows = 5;
        app.key(key(KeyCode::PageDown));
        assert_eq!(app.jobs_table.selected(), Some(5));
        app.key(key(KeyCode::End));
        app.key(key(KeyCode::Down));
        assert_eq!(app.jobs_table.selected(), Some(29));
        app.key(key(KeyCode::Enter));
        assert_eq!(app.overlay, Overlay::Details);
        app.key(key(KeyCode::Esc));
        app.key(key(KeyCode::Char('3')));
        app.key(key(KeyCode::Down));
        assert_eq!(app.transfers_table.selected(), None);
        app.key(key(KeyCode::Char('?')));
        app.scroll_max = 20;
        app.key(key(KeyCode::PageDown));
        assert_eq!(app.scroll, 8);
        assert_eq!(app.key(key(KeyCode::Char('q'))), Action::Quit);
    }

    #[test]
    fn pause_refresh_reverse_tab_and_editor_quit_are_explicit() {
        let mut app = App::new(View::Overview);
        app.key(key(KeyCode::BackTab));
        assert_eq!(app.view, View::Reports);
        app.key(key(KeyCode::Char('p')));
        assert!(app.paused);
        assert_eq!(app.key(key(KeyCode::Char('r'))), Action::Refresh);
        app.key(key(KeyCode::Char('2')));
        app.key(key(KeyCode::Char('/')));
        assert_eq!(app.key(key(KeyCode::Char('q'))), Action::None);
        assert_eq!(app.query(), "q");
        assert_eq!(
            app.key(KeyEvent::new(KeyCode::Char('c'), KeyModifiers::CONTROL)),
            Action::Quit
        );
    }

    fn filter(app: &mut App, value: &str) {
        app.key(key(KeyCode::Char('/')));
        for c in value.chars() {
            app.key(key(KeyCode::Char(c)));
        }
        app.key(key(KeyCode::Enter));
    }

    #[test]
    fn searches_match_displayed_states_technical_states_and_accents() {
        let mut app = App::new(View::Transfers);
        app.data.transfers = vec![
            Transfer {
                id: "a".into(),
                state: "running".into(),
                ..Transfer::default()
            },
            Transfer {
                id: "b".into(),
                state: "completed".into(),
                ..Transfer::default()
            },
        ];
        filter(&mut app, "EN COURS");
        assert_eq!(
            app.transfers()
                .iter()
                .map(|row| row.id.as_str())
                .collect::<Vec<_>>(),
            ["a"]
        );
        filter(&mut app, "TERMINE");
        assert_eq!(app.transfers()[0].id, "b");
        filter(&mut app, "completed");
        assert_eq!(app.transfers()[0].id, "b");
        app.data.reports.items.push(Report {
            id: "report".into(),
            state: "published".into(),
            ..Report::default()
        });
        app.key(key(KeyCode::Char('5')));
        filter(&mut app, "publie");
        assert_eq!(app.reports().len(), 1);
        app.data.jobs.push(Job {
            state: "OUT_OF_MEMORY".into(),
            ..job("oom")
        });
        app.key(key(KeyCode::Char('2')));
        filter(&mut app, "memoire depassee");
        assert_eq!(app.jobs()[0].id, "oom");
    }

    #[test]
    fn sorting_preserves_identity_and_is_independent_per_view() {
        let mut app = App::new(View::Jobs);
        app.data.jobs = vec![
            Job {
                observed_at: Some(200.0),
                ..job("a")
            },
            Job {
                observed_at: Some(100.0),
                state: "NODE_FAIL".into(),
                ..job("b")
            },
        ];
        assert_eq!(app.jobs()[0].id, "a");
        app.key(key(KeyCode::Char('s')));
        app.key(key(KeyCode::Char('s')));
        assert_eq!(app.sort_order(), SortOrder::Priority);
        assert_eq!(app.jobs()[0].id, "b");
        assert_eq!(app.jobs()[app.jobs_table.selected().unwrap()].id, "a");
        app.key(key(KeyCode::Char('3')));
        assert_eq!(app.sort_order(), SortOrder::Date);
        app.key(key(KeyCode::Char('2')));
        app.apply(Snapshot {
            jobs: vec![
                Job {
                    observed_at: Some(100.0),
                    state: "NODE_FAIL".into(),
                    ..job("b")
                },
                Job {
                    observed_at: Some(200.0),
                    ..job("a")
                },
            ],
            ..Snapshot::default()
        });
        assert_eq!(app.jobs()[app.jobs_table.selected().unwrap()].id, "a");
    }

    #[test]
    fn priority_uses_a_fixed_instant_until_refresh_and_preserves_identity_when_age_changes() {
        let mut app = App::new(View::Transfers);
        app.sort_at = 1000.0;
        app.sorts[1] = SortOrder::Priority;
        app.data.transfers = vec![
            Transfer {
                id: "b".into(),
                state: "running".into(),
                observed_at: Some(995.0),
                ..Transfer::default()
            },
            Transfer {
                id: "a".into(),
                state: "running".into(),
                observed_at: Some(700.1),
                ..Transfer::default()
            },
            Transfer {
                id: "c".into(),
                state: "completed_unverified".into(),
                observed_at: Some(600.0),
                ..Transfer::default()
            },
        ];
        assert_eq!(
            app.transfers()
                .iter()
                .map(|row| row.id.as_str())
                .collect::<Vec<_>>(),
            ["c", "b", "a"]
        );
        app.key(key(KeyCode::Down));
        assert!(status::transfer_attention(&app.data.transfers[1], 1001.0).is_some());
        // Clock-based rendering does not reorder indices between observations.
        assert_eq!(
            app.transfers()[app.transfers_table.selected().unwrap()].id,
            "b"
        );
        let transfers = app.data.transfers.clone();
        app.apply(Snapshot {
            transfers,
            ..Snapshot::default()
        });
        assert_eq!(
            app.transfers()[app.transfers_table.selected().unwrap()].id,
            "b"
        );
    }

    #[test]
    fn overview_recent_jobs_ignore_list_filters_and_sort_preferences() {
        let mut app = App::new(View::Jobs);
        app.data.jobs = vec![
            Job {
                id: "old".into(),
                state: "NODE_FAIL".into(),
                observed_at: Some(100.0),
                ..job("old")
            },
            Job {
                id: "new".into(),
                observed_at: Some(200.0),
                ..job("new")
            },
        ];
        filter(&mut app, "does not match");
        assert!(app.jobs().is_empty());
        assert_eq!(app.recent_jobs()[0].id, "new");
        app.key(key(KeyCode::Esc));
        app.key(key(KeyCode::Char('s')));
        app.key(key(KeyCode::Char('s')));
        assert_eq!(app.jobs()[0].id, "old");
        assert_eq!(app.recent_jobs()[0].id, "new");
    }

    #[test]
    fn closing_an_overlay_restores_the_underlying_scroll_position() {
        let mut app = App::new(View::Overview);
        app.scroll = 12;
        app.scroll_max = 30;
        app.scroll_page = 10;
        app.key(key(KeyCode::Char('?')));
        app.scroll_max = 40;
        app.key(key(KeyCode::PageDown));
        app.key(key(KeyCode::Esc));
        assert_eq!((app.scroll, app.scroll_max, app.scroll_page), (12, 30, 10));
    }
}
