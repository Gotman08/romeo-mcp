//! Optional terminal client. The Python MCP entry point stays a separate process.
mod app;
mod bridge;
mod model;
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
    #[arg(long)]
    db: Option<PathBuf>,
    #[arg(long, default_value_t = 5, value_parser = clap::value_parser!(u64).range(1..=300))]
    refresh: u64,
    #[arg(long, default_value_t = 40, value_parser = clap::value_parser!(u16).range(1..=100))]
    limit: u16,
    #[arg(long, default_value = "overview", value_parser = ["overview", "jobs", "transfers", "updates"])]
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
        _ => View::Overview,
    };
    let mut app = App::new(view);
    app.data.demo = options.demo;
    let reader = Reader::start(&options)?;
    reader.refresh();
    if options.snapshot {
        let data = reader
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
        let mut last_refresh = Instant::now();
        let mut last_draw = Instant::now();
        let mut dirty = true;
        loop {
            while let Ok(result) = reader.responses.try_recv() {
                match result {
                    Ok(data) => app.apply(data),
                    Err(message) => {
                        app.error = Some(message);
                        app.loading = false;
                    }
                }
                dirty = true;
            }
            if !app.paused
                && !app.loading
                && last_refresh.elapsed() >= Duration::from_secs(options.refresh)
            {
                app.loading = reader.refresh();
                last_refresh = Instant::now();
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
                                if reader.refresh() {
                                    app.loading = true;
                                }
                                last_refresh = Instant::now();
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

fn main() {
    if let Err(error) = run() {
        eprintln!("Interface ROMEO : {error}");
        std::process::exit(1);
    }
}
