//! Optional terminal client. The Python MCP entry point stays a separate process.
mod actions;
mod app;
mod bridge;
mod color;
mod local;
mod model;
mod preferences;
mod presentation;
mod query;
mod status;
mod ui;
mod view_cache;

use app::{Action, App, View};
use bridge::Reader;
use clap::Parser;
use crossterm::event::{self, Event, KeyEventKind};
use ratatui::{backend::TestBackend, Terminal};
use std::{
    io::{self, IsTerminal},
    path::PathBuf,
    time::{Duration, Instant},
};

#[derive(Parser, Debug)]
#[command(
    version,
    about = "ROMEO MCP — tableau de bord local facultatif (Ratatui)"
)]
pub struct Options {
    #[arg(long)]
    python: PathBuf,
    #[arg(long)]
    package_root: PathBuf,
    #[arg(long)]
    demo: bool,
    #[arg(long, value_enum, default_value_t = color::ColorMode::Auto)]
    color: color::ColorMode,
    #[arg(long)]
    db: Option<PathBuf>,
    #[arg(long, default_value_t = 5, value_parser = clap::value_parser!(u64).range(1..=300))]
    refresh: u64,
    #[arg(long, default_value_t = 40, value_parser = clap::value_parser!(u16).range(1..=100))]
    limit: u16,
    #[arg(long, value_parser = ["overview", "jobs", "transfers", "updates", "reports", "dossier", "recovery", "groups", "sessions"])]
    view: Option<String>,
    #[arg(long, default_value = "", value_parser = query_argument)]
    query: String,
    #[arg(long, default_value_t = 1, value_parser = clap::value_parser!(u32).range(1..=2147483648))]
    page: u32,
    #[arg(long, value_parser = ["activity", "date", "state", "priority"])]
    sort: Option<String>,
    #[arg(long, value_enum)]
    layout: Option<preferences::LayoutMode>,
    #[arg(long, value_parser = clap::value_parser!(u16).range(25..=65))]
    detail_width: Option<u16>,
    #[arg(long, value_parser = clap::value_parser!(u64).range(1..=86400))]
    job_stale_after: Option<u64>,
    #[arg(long, value_parser = clap::value_parser!(u64).range(1..=86400))]
    transfer_stale_after: Option<u64>,
    #[arg(long)]
    preferences: Option<PathBuf>,
    #[arg(long, conflicts_with = "preferences")]
    no_preferences: bool,
    #[arg(long, conflicts_with = "snapshot")]
    export: Option<PathBuf>,
    #[arg(long)]
    snapshot: bool,
    #[arg(long, default_value_t = 100, value_parser = clap::value_parser!(u16).range(40..=240))]
    width: u16,
    #[arg(long, default_value_t = 30, value_parser = clap::value_parser!(u16).range(10..=80))]
    height: u16,
    #[arg(long, hide=true, value_parser=["copy","export"])]
    helper: Option<String>,
    #[arg(long)]
    notifications: bool,
    #[arg(long)]
    mouse: bool,
    #[arg(long)]
    anonymize: bool,
}

fn query_argument(value: &str) -> Result<String, String> {
    if value.chars().count() <= 80
        && !value.chars().any(char::is_control)
        && crate::model::clean(value) == value
    {
        Ok(value.trim().into())
    } else {
        Err("La recherche doit contenir au plus 80 caractères imprimables.".into())
    }
}

/// Disable bracketed paste before Ratatui restores the terminal, including IO errors.
struct PasteCapture(bool);

impl PasteCapture {
    fn enable() -> io::Result<Self> {
        if cfg!(windows) {
            // ReadConsoleInput consumes the paste boundaries on Windows.
            // Explicit F2 note saving keeps multiline text inside the editor.
            return Ok(Self(false));
        }
        let guard = Self(true);
        crossterm::execute!(io::stdout(), event::EnableBracketedPaste)?;
        Ok(guard)
    }
}

impl Drop for PasteCapture {
    fn drop(&mut self) {
        if self.0 {
            let _ = crossterm::execute!(io::stdout(), event::DisableBracketedPaste);
        }
    }
}

fn run() -> io::Result<()> {
    let options = Options::parse();
    if let Some(kind) = &options.helper {
        return actions::helper(kind);
    }
    if !options.snapshot
        && options.export.is_none()
        && (!io::stdin().is_terminal() || !io::stdout().is_terminal())
    {
        return Err(io::Error::other(
            "Ouvrir un terminal interactif ou utiliser --snapshot.",
        ));
    }
    let preference_path = if options.no_preferences || options.snapshot || options.export.is_some()
    {
        None
    } else {
        options.preferences.clone().or_else(|| {
            preferences::directory().map(|root| {
                root.join(if options.demo {
                    "demo.json"
                } else {
                    "preferences.json"
                })
            })
        })
    };
    let mut preferred = preferences::Preferences::default();
    let mut preference_error = None;
    if let Some(path) = &preference_path {
        match preferences::load(path) {
            Ok(value) => preferred = value,
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(_) => {
                preference_error = Some("Préférences illisibles ; réglages par défaut.".into())
            }
        }
    }
    let view = match options.view.as_deref() {
        Some("jobs") => View::Jobs,
        Some("transfers") => View::Transfers,
        Some("updates") => View::Updates,
        Some("reports") => View::Reports,
        Some("dossier") => View::Dossier,
        Some("recovery") => View::Recovery,
        Some("groups") => View::Groups,
        Some("sessions") => View::Sessions,
        Some(_) => View::Overview,
        None => preferred.view,
    };
    let mut app = App::new(view);
    app.configure(&preferred);
    app.view = view;
    app.notifications |= options.notifications;
    app.mouse_enabled |= options.mouse;
    app.anonymized |= options.anonymize;
    app.notice = preference_error;
    if let Some(layout) = options.layout {
        app.layout = layout;
    }
    if let Some(width) = options.detail_width {
        app.detail_percent = width;
    }
    if let Some(after) = options.job_stale_after {
        app.job_stale_after = after;
    }
    if let Some(after) = options.transfer_stale_after {
        app.transfer_stale_after = after;
    }
    if let Some(sort) = &options.sort {
        app.set_sort(
            serde_json::from_value(serde_json::Value::String(sort.clone()))
                .map_err(io::Error::other)?,
        );
    }
    if !options.query.is_empty() {
        app.set_query(options.query.clone());
    }
    app.set_page(options.page.saturating_sub(1) as usize);
    let mut last_preferences = preferred;
    app.data.demo = options.demo;
    app.refresh_seconds = options.refresh;
    app.palette = options
        .color
        .palette(std::env::var("NO_COLOR").ok().as_deref());
    crossterm::style::force_color_output(app.palette == color::Palette::Color);
    let mut reader = None;
    let mut last_refresh = Instant::now();
    request_refresh(&mut reader, &options, &mut app, &mut last_refresh);
    if options.snapshot || options.export.is_some() {
        let reader = reader
            .as_ref()
            .ok_or_else(|| io::Error::other("Le lecteur local n'a pas pu demarrer."))?;
        let mut contact = Instant::now();
        let data = loop {
            if reader.progress().is_some() {
                contact = Instant::now();
            }
            match reader.responses.recv_timeout(Duration::from_millis(100)) {
                Ok(result) => break result.map_err(io::Error::other)?,
                Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                    return Err(io::Error::other("Lecteur local arrêté."))
                }
                Err(_) if contact.elapsed() >= Duration::from_secs(10) => {
                    return Err(io::Error::other("Le lecteur local ne répond pas."))
                }
                Err(_) => {}
            }
        };
        app.apply(data);
        if let Some(path) = &options.export {
            local::export(path, &ui::summary(&mut app))?;
            println!("Résumé exporté : {}", path.display());
            return Ok(());
        }
        let mut terminal = Terminal::new(TestBackend::new(options.width, options.height)).unwrap();
        terminal.draw(|frame| ui::draw(frame, &mut app)).unwrap();
        let buffer = terminal.backend().buffer();
        for y in 0..options.height {
            let line: String = (0..options.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect();
            println!("{}", line.trim_end());
        }
        return Ok(());
    }
    ratatui::run(|terminal| {
        let _paste_capture = PasteCapture::enable()?;
        let mut last_draw = Instant::now();
        let mut dirty = true;
        let mut last_contact = Instant::now();
        let mut last_collection = Instant::now();
        let mut task: Option<actions::Task> = None;
        let mut mouse_capture = actions::MouseCapture::default();
        loop {
            mouse_capture.update(app.mouse_enabled)?;
            dirty |= app.expire_confirmation();
            if let Some(partial) = reader.as_ref().and_then(Reader::partial) {
                last_contact = Instant::now();
                app.apply(partial);
                dirty = true;
            }
            if let Some(result) = task.as_ref().and_then(|task| task.result.try_recv().ok()) {
                let remote = task.as_ref().is_some_and(|task| task.remote);
                app.confirm(result.unwrap_or_else(|message| message));
                task.take();
                app.action_busy = false;
                dirty = true;
                if remote {
                    app.collect_read = true;
                    app.pending_read = true;
                }
            }
            if let Some(progress) = reader.as_ref().and_then(Reader::progress) {
                last_contact = Instant::now();
                if progress.request_id == app.revision {
                    app.read_phase = Some(progress.label());
                }
                dirty = true;
            }
            let mut reader_failed = false;
            while let Some(result) = reader
                .as_ref()
                .and_then(|reader| reader.responses.try_recv().ok())
            {
                match result {
                    Ok(data) => {
                        app.apply(data);
                    }
                    Err(message) => {
                        app.error = Some(message);
                        app.loading = false;
                        reader_failed = true;
                    }
                }
                dirty = true;
            }
            if reader_failed {
                reader.take();
            }
            if app.loading && last_contact.max(last_refresh).elapsed() >= Duration::from_secs(10) {
                reader.take();
                app.loading = false;
                app.error = Some("Le lecteur local ne répond pas (10 s).".into());
                dirty = true;
            }
            if !app.paused
                && !app.loading
                && app.error.is_none()
                && last_collection.elapsed() >= Duration::from_secs(options.refresh)
            {
                app.collect_read = true;
                request_refresh(&mut reader, &options, &mut app, &mut last_refresh);
                last_collection = Instant::now();
            }
            if app.pending_read
                && !app.loading
                && app.error.is_none()
                && app
                    .debounce_until
                    .is_none_or(|deadline| Instant::now() >= deadline)
            {
                request_refresh(&mut reader, &options, &mut app, &mut last_refresh);
            }
            if let Some(path) = &preference_path {
                let preferred = app.preferences();
                if preferred != last_preferences {
                    if preferences::save(path, &preferred).is_err() {
                        app.confirm("Préférences non sauvegardées ; vérifier le dossier local.");
                    }
                    last_preferences = preferred;
                }
            }
            if dirty || last_draw.elapsed() >= Duration::from_secs(1) {
                terminal.draw(|frame| ui::draw(frame, &mut app))?;
                last_draw = Instant::now();
                dirty = false;
            }
            if event::poll(Duration::from_millis(100))? {
                match event::read()? {
                    Event::Key(key) if key.kind == KeyEventKind::Press => {
                        match app.key(key) {
                            Action::Quit => break,
                            Action::Refresh => {
                                if !app.loading {
                                    request_refresh(
                                        &mut reader,
                                        &options,
                                        &mut app,
                                        &mut last_refresh,
                                    );
                                    last_collection = Instant::now();
                                }
                            }
                            Action::None => {}
                            action => actions::dispatch(action, &options, &mut app, &mut task),
                        }
                        dirty = true;
                    }
                    Event::Resize(_, _) => dirty = true,
                    Event::Mouse(event) => {
                        app.mouse(event);
                        dirty = true;
                    }
                    Event::Paste(text) => {
                        app.paste(&text);
                        dirty = true;
                    }
                    _ => {}
                }
            }
        }
        drop(task);
        Ok(())
    })
}

fn request_refresh(
    reader: &mut Option<Reader>,
    options: &Options,
    app: &mut App,
    started: &mut Instant,
) {
    if reader.as_ref().is_none_or(Reader::stopped) {
        reader.take();
        match Reader::start(options) {
            Ok(new_reader) => *reader = Some(new_reader),
            Err(_) => {
                app.loading = false;
                app.error = Some("Impossible de démarrer le lecteur local.".into());
                return;
            }
        }
    }
    app.loading = reader
        .as_ref()
        .is_some_and(|reader| reader.refresh(&app.read_request()));
    if app.loading {
        app.pending_read = false;
        app.force_read = false;
        app.collect_read = false;
        *started = Instant::now();
    } else {
        app.error = Some("Lecteur local indisponible ; r pour reconnecter.".into());
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("Interface ROMEO : {error}");
        std::process::exit(1);
    }
}
