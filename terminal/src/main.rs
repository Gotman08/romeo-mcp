//! Optional terminal client. The Python MCP entry point stays a separate process.
mod app;
mod bridge;
mod color;
mod model;
mod query;
mod status;
mod ui;

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
    #[arg(long, default_value = "overview", value_parser = ["overview", "jobs", "transfers", "updates", "reports"])]
    view: String,
    #[arg(long)]
    snapshot: bool,
    #[arg(long, default_value_t = 100, value_parser = clap::value_parser!(u16).range(40..=240))]
    width: u16,
    #[arg(long, default_value_t = 30, value_parser = clap::value_parser!(u16).range(10..=80))]
    height: u16,
}

fn run() -> io::Result<()> {
    let options = Options::parse();
    if !options.snapshot && (!io::stdin().is_terminal() || !io::stdout().is_terminal()) {
        return Err(io::Error::other(
            "Ouvrir un terminal interactif ou utiliser --snapshot.",
        ));
    }
    let view = match options.view.as_str() {
        "jobs" => View::Jobs,
        "transfers" => View::Transfers,
        "updates" => View::Updates,
        "reports" => View::Reports,
        _ => View::Overview,
    };
    let mut app = App::new(view);
    app.data.demo = options.demo;
    app.refresh_seconds = options.refresh;
    app.palette = options
        .color
        .palette(std::env::var("NO_COLOR").ok().as_deref());
    crossterm::style::force_color_output(app.palette == color::Palette::Color);
    let mut reader = None;
    let mut last_refresh = Instant::now();
    request_refresh(&mut reader, &options, &mut app, &mut last_refresh);
    if options.snapshot {
        let data = reader
            .as_ref()
            .ok_or_else(|| io::Error::other("Le lecteur local n'a pas pu demarrer."))?
            .responses
            .recv_timeout(Duration::from_secs(10))
            .map_err(|_| io::Error::other("Le lecteur local ne répond pas."))?
            .map_err(io::Error::other)?;
        app.apply(data);
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
        let mut last_draw = Instant::now();
        let mut dirty = true;
        loop {
            let mut reader_failed = false;
            while let Some(result) = reader
                .as_ref()
                .and_then(|reader| reader.responses.try_recv().ok())
            {
                match result {
                    Ok(data) => app.apply(data),
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
            if app.loading && last_refresh.elapsed() >= Duration::from_secs(10) {
                reader.take();
                app.loading = false;
                app.error = Some("Le lecteur local ne répond pas (10 s).".into());
                dirty = true;
            }
            if !app.paused
                && !app.loading
                && app.error.is_none()
                && last_refresh.elapsed() >= Duration::from_secs(options.refresh)
            {
                request_refresh(&mut reader, &options, &mut app, &mut last_refresh);
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
                                }
                            }
                            Action::None => {}
                        }
                        dirty = true;
                    }
                    Event::Resize(_, _) => dirty = true,
                    _ => {}
                }
            }
        }
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
    app.loading = reader.as_ref().is_some_and(Reader::refresh);
    if app.loading {
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
