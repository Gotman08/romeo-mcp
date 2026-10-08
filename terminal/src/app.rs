//! View-local state, identity preservation and cached records.
mod interaction;
use crate::{
    color::Palette,
    model::{now, Job, Report, Snapshot, Transfer},
    query::{self, Key, SortOrder},
    status::{self, job_state, report_state, transfer_state},
};
use crate::{
    preferences::{LayoutMode, Panel, Preferences},
    view_cache::{Key as CacheKey, Rows},
};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::widgets::TableState;
use serde::{Deserialize, Serialize};
use std::{cell::RefCell, collections::BTreeMap};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum View {
    Overview,
    Jobs,
    Transfers,
    Updates,
    Reports,
    Dossier,
    Recovery,
    Groups,
    Sessions,
}

impl View {
    pub fn index(self) -> usize {
        match self {
            Self::Overview => 0,
            Self::Jobs => 1,
            Self::Transfers => 2,
            Self::Updates => 3,
            Self::Reports => 4,
            Self::Dossier => 5,
            Self::Recovery => 6,
            Self::Groups => 7,
            Self::Sessions => 8,
        }
    }
    pub fn from_index(index: usize) -> Self {
        [
            Self::Overview,
            Self::Jobs,
            Self::Transfers,
            Self::Updates,
            Self::Reports,
            Self::Dossier,
            Self::Recovery,
            Self::Groups,
            Self::Sessions,
        ][index % 9]
    }
    fn filter_index(self) -> Option<usize> {
        match self {
            Self::Jobs | Self::Dossier | Self::Recovery | Self::Groups => Some(0),
            Self::Transfers => Some(1),
            Self::Reports => Some(2),
            Self::Sessions => Some(3),
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
    Copy(bool),
    Export,
    Remote(&'static str),
    Cancel,
}

#[derive(Serialize)]
pub struct ReadRequest {
    pub request_id: u64,
    pub queries: BTreeMap<&'static str, String>,
    pub pages: BTreeMap<&'static str, usize>,
    pub sorts: BTreeMap<&'static str, SortOrder>,
    pub anchors: BTreeMap<&'static str, String>,
    pub force: bool,
    pub job_stale_after: u64,
    pub transfer_stale_after: u64,
    pub collect: bool,
    pub detail_job: String,
    pub progressive: bool,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Overlay {
    #[default]
    None,
    Help,
    Details,
    Alerts,
    Actions,
    Note,
    Logs,
    Favorites,
}

pub struct App {
    pub data: Snapshot,
    pub view: View,
    filters: [String; 4],
    sorts: [SortOrder; 4],
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
    pub layout: LayoutMode,
    pub focus: Panel,
    pub split_visible: bool,
    pub detail_percent: u16,
    pub job_stale_after: u64,
    pub transfer_stale_after: u64,
    pub alerts_table: TableState,
    pub notice: Option<String>,
    pub last_confirmation: Option<String>,
    notice_until: Option<std::time::Instant>,
    pub revision: u64,
    pub pending_read: bool,
    pub force_read: bool,
    pub read_phase: Option<String>,
    pages: [usize; 5],
    anchor_allowed: [bool; 5],
    pending_detail: Option<(View, String)>,
    data_revision: u64,
    rows: RefCell<Rows>,
    pub sessions_table: TableState,
    pub favorites: std::collections::BTreeSet<String>,
    pub notes: BTreeMap<String, String>,
    pub notifications: bool,
    pub notification_log: Vec<String>,
    pub anonymized: bool,
    pub mouse_enabled: bool,
    pub id_width: u16,
    pub note_edit: String,
    pub note_target: Option<String>,
    pub menu_selected: usize,
    pub collect_read: bool,
    pub debounce_until: Option<std::time::Instant>,
    pub action_busy: bool,
    pub table_area: Option<ratatui::layout::Rect>,
    pub detail_area: Option<ratatui::layout::Rect>,
    pub tab_hits: Vec<(ratatui::layout::Rect, View)>,
    seen_notifications: std::collections::BTreeSet<String>,
}

impl App {
    pub fn new(view: View) -> Self {
        Self {
            data: Snapshot::default(),
            view,
            filters: Default::default(),
            sorts: [
                SortOrder::Activity,
                SortOrder::Date,
                SortOrder::Date,
                SortOrder::Date,
            ],
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
            layout: LayoutMode::Split,
            focus: Panel::List,
            split_visible: false,
            detail_percent: 40,
            job_stale_after: 300,
            transfer_stale_after: 60,
            alerts_table: TableState::default().with_selected(0),
            notice: None,
            last_confirmation: None,
            notice_until: None,
            revision: 0,
            pending_read: true,
            force_read: false,
            read_phase: None,
            pages: [0; 5],
            anchor_allowed: [false; 5],
            pending_detail: None,
            data_revision: 0,
            rows: RefCell::new(Rows::default()),
            sessions_table: TableState::default().with_selected(0),
            favorites: Default::default(),
            notes: Default::default(),
            notifications: false,
            notification_log: vec![],
            anonymized: false,
            mouse_enabled: false,
            id_width: 8,
            note_edit: String::new(),
            note_target: None,
            menu_selected: 0,
            collect_read: true,
            debounce_until: None,
            action_busy: false,
            table_area: None,
            detail_area: None,
            tab_hits: vec![],
            seen_notifications: Default::default(),
        }
    }

    pub fn query(&self) -> &str {
        self.view
            .filter_index()
            .map(|index| self.filters[index].as_str())
            .unwrap_or("")
    }

    pub fn jobs(&self) -> Vec<&Job> {
        if self.current_page() {
            return self.data.jobs.iter().collect();
        }
        let indexes = self.cached(0, &self.data.jobs, || {
            self.ordered_jobs(&query::normalize(&self.filters[0]), self.sorts[0])
        });
        indexes
            .into_iter()
            .map(|index| &self.data.jobs[index])
            .collect()
    }

    pub fn selected_job(&self) -> Option<&Job> {
        self.jobs()
            .get(self.jobs_table.selected().unwrap_or(0))
            .copied()
    }

    pub fn confirm(&mut self, message: impl Into<String>) {
        let message = message.into();
        self.last_confirmation = Some(message.clone());
        self.notice = Some(message);
        self.notice_until = Some(std::time::Instant::now() + std::time::Duration::from_secs(5));
    }

    pub fn expire_confirmation(&mut self) -> bool {
        if self
            .notice_until
            .is_some_and(|deadline| std::time::Instant::now() >= deadline)
        {
            self.notice = None;
            self.notice_until = None;
            return true;
        }
        false
    }

    fn notify_changes(&mut self, snapshot: &Snapshot) {
        for event in &snapshot.notifications {
            if self.seen_notifications.insert(event.key.clone())
                && self.notifications
                && self.data.generated_at > 0.0
            {
                let text = format!(
                    "Job {} · {} · {}",
                    event.job_id,
                    event.message,
                    crate::model::timestamp_exact(event.observed_at)
                );
                self.confirm(text.clone());
                self.notification_log.push(text);
                if self.notification_log.len() > 50 {
                    self.notification_log.remove(0);
                }
            }
        }
        if self.seen_notifications.len() > 5000 {
            self.seen_notifications
                .retain(|key| snapshot.notifications.iter().any(|event| &event.key == key));
        }
    }

    pub fn recent_jobs(&self) -> Vec<&Job> {
        if self.data.schema == 3 {
            return self.data.recent_jobs.iter().collect();
        }
        self.ordered_jobs("", SortOrder::Date)
    }

    fn cached<'a, T>(
        &self,
        index: usize,
        source: &'a [T],
        build: impl FnOnce() -> Vec<&'a T>,
    ) -> Vec<usize> {
        self.rows.borrow_mut().get(
            index,
            CacheKey {
                revision: self.data_revision,
                source: (source.as_ptr() as usize, source.len()),
                query: self.filters[index].clone(),
                sort: self.sorts[index],
                at: self.sort_at.to_bits(),
            },
            || {
                build()
                    .into_iter()
                    .filter_map(|row| {
                        source
                            .iter()
                            .position(|candidate| std::ptr::eq(candidate, row))
                    })
                    .collect()
            },
        )
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
            let mut key = Key::new(
                status::priority(
                    &row.state,
                    status::job_attention_after(row, at, self.job_stale_after as f64).is_some(),
                ),
                row.observed_at.or(row.submitted_at),
                job_state(&row.state),
                &row.id,
            );
            key.active = status::job_active(&row.state);
            key
        })
    }

    pub fn transfers(&self) -> Vec<&Transfer> {
        if self.current_page() {
            return self.data.transfers.iter().collect();
        }
        let indexes = self.cached(1, &self.data.transfers, || self.ordered_transfers());
        indexes
            .into_iter()
            .map(|index| &self.data.transfers[index])
            .collect()
    }

    fn ordered_transfers(&self) -> Vec<&Transfer> {
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
                        status::transfer_validation(row).label(),
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
                status::priority(
                    &row.state,
                    status::transfer_attention_after(row, at, self.transfer_stale_after as f64)
                        .is_some(),
                ),
                row.observed_at.or(row.created_at),
                transfer_state(&row.state),
                &row.id,
            )
        })
    }

    pub fn reports(&self) -> Vec<&Report> {
        if self.current_page() {
            return self.data.reports.items.iter().collect();
        }
        let indexes = self.cached(2, &self.data.reports.items, || self.ordered_reports());
        indexes
            .into_iter()
            .map(|index| &self.data.reports.items[index])
            .collect()
    }

    fn ordered_reports(&self) -> Vec<&Report> {
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

    pub fn apply(&mut self, snapshot: Snapshot) -> bool {
        if snapshot.schema == 3 && snapshot.request_id != self.revision {
            self.loading = false;
            self.pending_read = true;
            return false;
        }
        let selection = self.selected_ids();
        let session_id = self
            .data
            .sessions
            .get(self.sessions_table.selected().unwrap_or(0))
            .map(|row| row.id.clone());
        let old_alert = self
            .data
            .attention
            .get(self.alerts_table.selected().unwrap_or(0))
            .map(|row| (row.kind.clone(), row.id.clone()));
        if !snapshot.partial {
            self.notify_changes(&snapshot);
        }
        self.data = snapshot;
        self.read_phase = None;
        self.data_revision += 1;
        self.sort_at = now();
        self.restore_selection(selection);
        if self.data.schema == 3 {
            for index in 0..5 {
                self.pages[index] = self.page_info(index).page;
            }
            let alert_index =
                self.data.attention.iter().position(|row| {
                    Some(&(row.kind.clone(), row.id.clone())) == old_alert.as_ref()
                });
            self.alerts_table.select(alert_index.or(Some(0)));
        }
        self.sessions_table.select(
            self.data
                .sessions
                .iter()
                .position(|row| Some(&row.id) == session_id.as_ref())
                .or(Some(0)),
        );
        self.anchor_allowed = [true; 5];
        self.loading = self.data.partial;
        self.error = None;
        if let Some((view, id)) = if self.data.partial {
            None
        } else {
            self.pending_detail.take()
        } {
            let position = match view {
                View::Jobs | View::Dossier | View::Recovery | View::Groups => {
                    self.jobs().iter().position(|row| row.id == id)
                }
                View::Transfers => self.transfers().iter().position(|row| row.id == id),
                View::Reports => self.reports().iter().position(|row| row.id == id),
                _ => None,
            };
            if let Some(position) = position {
                if let Some(table) = self.table() {
                    table.select(Some(position));
                }
                self.open(Overlay::Details);
            } else {
                self.confirm("La trace ciblée n'est plus disponible dans le registre.");
            }
        }
        true
    }

    fn current_page(&self) -> bool {
        // The catalog already searches and sorts the complete registry. Do not
        // run a different local filter over an authoritative page of matches.
        // While a new query is loading, keep the previous page and selection
        // together. Reordering it locally would change the selected identity
        // before that identity is sent as the anchor of the new global sort.
        self.data.schema == 3
    }

    pub fn preferences(&self) -> Preferences {
        Preferences {
            schema: 2,
            view: self.view,
            sorts: self.sorts,
            layout: self.layout,
            detail_percent: self.detail_percent,
            job_stale_after: self.job_stale_after,
            transfer_stale_after: self.transfer_stale_after,
            favorites: self.favorites.clone(),
            notes: self.notes.clone(),
            notifications: self.notifications,
            mouse: self.mouse_enabled,
            anonymized: self.anonymized,
            id_width: self.id_width,
        }
    }

    pub fn configure(&mut self, value: &Preferences) {
        self.view = value.view;
        self.sorts = value.sorts;
        self.layout = value.layout;
        self.detail_percent = value.detail_percent;
        self.job_stale_after = value.job_stale_after;
        self.transfer_stale_after = value.transfer_stale_after;
        self.favorites = value.favorites.clone();
        self.notes = value.notes.clone();
        self.notifications = value.notifications;
        self.mouse_enabled = value.mouse;
        self.anonymized = value.anonymized;
        self.id_width = value.id_width;
    }

    pub fn collection_index(&self) -> Option<usize> {
        if self.view == View::Sessions {
            return Some(4);
        }
        self.view.filter_index().or(if self.view == View::Overview {
            Some(3)
        } else {
            None
        })
    }

    pub fn page_info(&self, index: usize) -> crate::model::Page {
        if self.data.schema == 3 {
            return match index {
                0 => &self.data.coverage.jobs,
                1 => &self.data.coverage.transfers,
                2 => &self.data.coverage.reports,
                4 => &self.data.coverage.sessions,
                _ => &self.data.coverage.alerts,
            }
            .clone();
        }
        let loaded = match index {
            0 => self.data.jobs.len(),
            1 => self.data.transfers.len(),
            2 => self.data.reports.items.len(),
            4 => self.data.sessions.len(),
            _ => self.data.attention.len(),
        };
        crate::model::Page {
            page: 0,
            pages: 1,
            loaded,
            matched: loaded,
            total: loaded,
            page_size: 100,
        }
    }

    pub fn set_query(&mut self, query: String) {
        if let Some(index) = self.view.filter_index() {
            self.filters[index] = query;
            let page = self.collection_index().unwrap_or(index);
            self.pages[page] = 0;
            self.anchor_allowed[page] = false;
            self.mark_read(false);
        }
    }

    pub fn set_page(&mut self, page: usize) {
        if let Some(index) = self.collection_index() {
            self.pages[index] = page;
            self.anchor_allowed[index] = false;
        }
    }

    pub fn set_sort(&mut self, sort: SortOrder) {
        if let Some(index) = self.view.filter_index() {
            self.sorts[index] = sort;
        }
    }

    fn mark_read(&mut self, force: bool) {
        self.revision = (self.revision + 1) % (1 << 53);
        self.pending_read = true;
        self.force_read |= force;
        self.collect_read |= force;
    }

    pub fn read_request(&self) -> ReadRequest {
        let names = ["jobs", "transfers", "reports", "alerts", "sessions"];
        let selected = self.selected_ids();
        let mut anchors = BTreeMap::new();
        for index in 0..3 {
            if self.anchor_allowed[index] {
                if let Some(id) = &selected[index] {
                    anchors.insert(names[index], id.clone());
                }
            }
        }
        if self.anchor_allowed[3] {
            if let Some(alert) = self
                .data
                .attention
                .get(self.alerts_table.selected().unwrap_or(0))
            {
                anchors.insert("alerts", format!("{}:{}", alert.kind, alert.id));
            }
        }
        if self.anchor_allowed[4] {
            if let Some(row) = self
                .data
                .sessions
                .get(self.sessions_table.selected().unwrap_or(0))
            {
                anchors.insert("sessions", row.id.clone());
            }
        }
        if let Some((view, id)) = &self.pending_detail {
            if let Some(index) = view.filter_index() {
                anchors.insert(names[index], id.clone());
            }
        }
        ReadRequest {
            request_id: self.revision,
            queries: names
                .iter()
                .enumerate()
                .map(|(index, name)| {
                    (
                        *name,
                        if index == 4 {
                            self.filters[3].clone()
                        } else if index < 3 {
                            self.filters[index].clone()
                        } else {
                            String::new()
                        },
                    )
                })
                .collect(),
            pages: names
                .iter()
                .enumerate()
                .map(|(index, name)| (*name, self.pages[index]))
                .collect(),
            sorts: names
                .iter()
                .enumerate()
                .map(|(index, name)| {
                    (
                        *name,
                        if index == 4 {
                            self.sorts[3]
                        } else if index < 3 {
                            self.sorts[index]
                        } else {
                            SortOrder::Priority
                        },
                    )
                })
                .collect(),
            anchors,
            force: self.force_read,
            job_stale_after: self.job_stale_after,
            transfer_stale_after: self.transfer_stale_after,
            collect: self.collect_read,
            progressive: true,
            detail_job: self
                .pending_detail
                .as_ref()
                .filter(|(view, _)| {
                    matches!(
                        view,
                        View::Jobs | View::Dossier | View::Recovery | View::Groups
                    )
                })
                .map(|(_, id)| id.clone())
                .or_else(|| self.selected_job().map(|row| row.id.clone()))
                .unwrap_or_default(),
        }
    }

    pub fn page(&mut self, forward: bool) {
        if let Some(index) = self.collection_index() {
            let info = self.page_info(index);
            let next = if forward {
                self.pages[index]
                    .saturating_add(1)
                    .min(info.pages.saturating_sub(1))
            } else {
                self.pages[index].saturating_sub(1)
            };
            if next != self.pages[index] {
                self.pages[index] = next;
                self.anchor_allowed[index] = false;
                if let Some(table) = self.table() {
                    table.select(Some(0));
                }
                self.scroll = 0;
                self.mark_read(false);
            }
        }
    }

    fn open_alert(&mut self) {
        if let Some(alert) = self
            .data
            .attention
            .get(self.alerts_table.selected().unwrap_or(0))
            .cloned()
        {
            let view = match alert.kind.as_str() {
                "jobs" => View::Jobs,
                "transfers" => View::Transfers,
                "reports" => View::Reports,
                _ => return,
            };
            self.switch_view(view);
            self.set_query(alert.id.chars().take(80).collect());
            self.pending_detail = Some((view, alert.id));
        }
    }

    pub fn copy_value(&self, path: bool) -> Option<String> {
        if path {
            if self.view == View::Transfers {
                return self
                    .transfers()
                    .get(self.transfers_table.selected().unwrap_or(0))
                    .map(|row| row.local_path.clone());
            }
            return None;
        }
        match self.view {
            View::Overview => self
                .data
                .attention
                .get(self.alerts_table.selected().unwrap_or(0))
                .map(|row| row.id.clone()),
            View::Jobs | View::Dossier | View::Recovery | View::Groups => self
                .jobs()
                .get(self.jobs_table.selected().unwrap_or(0))
                .map(|row| row.id.clone()),
            View::Sessions => self
                .data
                .sessions
                .get(self.sessions_table.selected().unwrap_or(0))
                .map(|row| row.id.clone()),
            View::Transfers => self
                .transfers()
                .get(self.transfers_table.selected().unwrap_or(0))
                .map(|row| row.id.clone()),
            View::Reports => self
                .reports()
                .get(self.reports_table.selected().unwrap_or(0))
                .map(|row| row.id.clone()),
            _ => None,
        }
    }

    fn cycle_sort(&mut self) {
        if let Some(index) = self.view.filter_index() {
            let selection = self.selected_ids();
            self.sorts[index] = self.sorts[index].next();
            self.restore_selection(selection);
            self.mark_read(false);
        }
    }

    fn table(&mut self) -> Option<&mut TableState> {
        match self.view {
            View::Jobs | View::Dossier | View::Recovery | View::Groups => {
                Some(&mut self.jobs_table)
            }
            View::Sessions => Some(&mut self.sessions_table),
            View::Transfers => Some(&mut self.transfers_table),
            View::Reports => Some(&mut self.reports_table),
            View::Overview if self.data.schema == 3 => Some(&mut self.alerts_table),
            _ => None,
        }
    }

    fn row_count(&self) -> usize {
        match self.view {
            View::Jobs | View::Dossier | View::Recovery | View::Groups => self.jobs().len(),
            View::Sessions => self.data.sessions.len(),
            View::Transfers => self.transfers().len(),
            View::Reports => self.reports().len(),
            View::Overview => self.data.attention.len(),
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
            self.scroll = 0;
            if matches!(
                self.view,
                View::Jobs | View::Dossier | View::Recovery | View::Groups
            ) {
                self.mark_read(false);
            }
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
        if self.overlay == Overlay::Note {
            self.note_target = None;
            self.note_edit.clear();
        }
        self.overlay = Overlay::None;
        (self.scroll, self.scroll_max, self.scroll_page) = self.saved_scroll;
    }

    fn switch_view(&mut self, view: View) {
        self.view = view;
        self.focus = Panel::List;
        self.split_visible = false;
        self.scroll = 0;
        self.scroll_max = 0;
        self.mark_read(false);
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
    fn global_pages_reject_late_responses_and_trust_catalog_matches() {
        let mut app = App::new(View::Jobs);
        app.set_query("recent".into());
        let page = crate::model::Page {
            pages: 3,
            loaded: 1,
            matched: 81,
            total: 81,
            page_size: 40,
            ..Default::default()
        };
        let current = Snapshot {
            schema: 3,
            request_id: app.revision,
            jobs: vec![job("1")],
            coverage: crate::model::Coverage {
                jobs: page,
                ..Default::default()
            },
            ..Default::default()
        };
        assert!(app.apply(current.clone()));
        assert_eq!(app.jobs().len(), 1); // The word is a computed badge, not a job name.
        app.page(true);
        assert_eq!(app.read_request().pages["jobs"], 1);
        assert!(!app.read_request().anchors.contains_key("jobs"));
        assert!(!app.apply(current));
        assert_eq!(app.data.jobs[0].id, "1");
        assert!(app.pending_read);
    }

    #[test]
    fn global_sort_anchors_the_selected_identity_before_new_page_arrives() {
        let mut app = App::new(View::Jobs);
        app.apply(Snapshot {
            schema: 3,
            jobs: vec![
                Job {
                    observed_at: Some(100.0),
                    ..job("101")
                },
                Job {
                    state: "COMPLETED".into(),
                    observed_at: Some(200.0),
                    ..job("102")
                },
            ],
            ..Default::default()
        });
        app.key(key(KeyCode::Down));
        app.key(key(KeyCode::Char('s')));
        assert_eq!(app.read_request().anchors["jobs"], "102");
        assert_eq!(app.jobs()[app.jobs_table.selected().unwrap()].id, "102");
    }

    #[test]
    fn overview_targets_exact_transfer_and_opens_its_detail_after_read() {
        let mut app = App::new(View::Overview);
        let id = "a".repeat(32);
        app.apply(Snapshot {
            schema: 3,
            attention: vec![crate::model::Alert {
                kind: "transfers".into(),
                id: id.clone(),
                ..Default::default()
            }],
            ..Default::default()
        });
        assert_eq!(app.key(key(KeyCode::Enter)), Action::Refresh);
        assert_eq!(app.view, View::Transfers);
        assert_eq!(app.read_request().anchors["transfers"], id);
        app.apply(Snapshot {
            schema: 3,
            request_id: app.revision,
            transfers: vec![Transfer {
                id: id.clone(),
                ..Default::default()
            }],
            ..Default::default()
        });
        assert_eq!(app.overlay, Overlay::Details);
        assert_eq!(app.copy_value(false), Some(id));
        app.key(key(KeyCode::Esc));
        app.split_visible = true;
        app.key(key(KeyCode::F(6)));
        assert_eq!(app.focus, Panel::Detail);
        app.key(key(KeyCode::Char('v')));
        assert_eq!(app.layout, LayoutMode::List);
        assert_eq!(app.focus, Panel::List);
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
        assert_eq!(app.view, View::Sessions);
        app.key(key(KeyCode::Char('p')));
        assert!(app.paused);
        assert_eq!(app.key(key(KeyCode::Char('r'))), Action::Refresh);
        app.key(key(KeyCode::Char('2')));
        app.key(key(KeyCode::Char('/')));
        assert_eq!(app.key(key(KeyCode::Char('q'))), Action::None);
        assert!(app.pending_read && app.debounce_until.is_some());
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
        app.transfer_stale_after = 300;
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
