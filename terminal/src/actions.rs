//! UI-owned helper processes keep filesystem, clipboard and SSH off the event loop.
use crate::Options;
use std::{
    io::{self, Read, Write},
    process::{Child, Command, Stdio},
    sync::{mpsc, Arc, Mutex},
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

pub struct Task {
    child: Arc<Mutex<Child>>,
    thread: Option<JoinHandle<()>>,
    pub result: mpsc::Receiver<Result<String, String>>,
    pub remote: bool,
}

fn kill_owned(child: &mut Child) {
    if child.try_wait().ok().flatten().is_some() {
        return;
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let _ = Command::new("taskkill.exe")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .creation_flags(0x08000000)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(unix)]
    {
        let _ = Command::new("kill")
            .args(["-KILL", "--", &format!("-{}", child.id())])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}

impl Task {
    fn spawn(mut command: Command, input: Option<String>, remote: bool) -> io::Result<Self> {
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        let mut child = command.spawn()?;
        let mut stdin = child.stdin.take();
        let mut stdout = child.stdout.take().expect("piped stdout");
        let child = Arc::new(Mutex::new(child));
        let owned = Arc::clone(&child);
        let (send, result) = mpsc::sync_channel(1);
        let thread = thread::spawn(move || {
            let outcome = (|| {
                if let (Some(stream), Some(input)) = (stdin.as_mut(), input) {
                    stream
                        .write_all(input.as_bytes())
                        .map_err(|_| "Action locale interrompue.")?;
                }
                drop(stdin);
                let deadline = Instant::now() + Duration::from_secs(if remote { 75 } else { 10 });
                loop {
                    if let Some(status) = owned
                        .lock()
                        .map_err(|_| "Action interrompue.")?
                        .try_wait()
                        .map_err(|_| "Action interrompue.")?
                    {
                        let mut bytes = Vec::new();
                        (&mut stdout)
                            .take(16385)
                            .read_to_end(&mut bytes)
                            .map_err(|_| "Réponse d'action illisible.")?;
                        if bytes.len() > 16384 || !status.success() {
                            return Err("Action impossible ; dernières preuves conservées.".into());
                        }
                        let value: serde_json::Value = serde_json::from_slice(&bytes)
                            .map_err(|_| "Réponse d'action incompatible.")?;
                        if value["ok"].as_bool() != Some(true) {
                            return Err("Action impossible ; dernières preuves conservées.".into());
                        }
                        let mut message = value["message"]
                            .as_str()
                            .unwrap_or("Action terminée.")
                            .to_owned();
                        if let Some(source) = value["source"].as_str() {
                            message.push_str(&format!(" · {}", crate::model::clean(source)));
                        }
                        if let Some(at) = value["observed_at"].as_f64() {
                            message.push_str(&format!(
                                " · {}",
                                crate::model::timestamp_exact(Some(at))
                            ));
                        }
                        return Ok(message);
                    }
                    if Instant::now() >= deadline {
                        if let Ok(mut child) = owned.lock() {
                            kill_owned(&mut child);
                        }
                        return Err("Action arrêtée : délai dépassé.".into());
                    }
                    thread::sleep(Duration::from_millis(20));
                }
            })();
            let _ = send.try_send(outcome);
        });
        Ok(Self {
            child,
            thread: Some(thread),
            result,
            remote,
        })
    }
    pub fn local(
        options: &Options,
        kind: &str,
        value: String,
        path: Option<std::path::PathBuf>,
    ) -> io::Result<Self> {
        let mut command = Command::new(std::env::current_exe()?);
        command
            .arg("--python")
            .arg(&options.python)
            .arg("--package-root")
            .arg(&options.package_root)
            .arg("--helper")
            .arg(kind);
        Self::spawn(
            command,
            Some(serde_json::json!({"value":value,"path":path}).to_string()),
            false,
        )
    }
    pub fn remote(options: &Options, kind: &str, identifier: &str) -> io::Result<Self> {
        let mut command = Command::new(&options.python);
        command.args(["-X","utf8","-I","-u","-c","import sys; sys.path.insert(0,sys.argv.pop(1)); from romeo_mcp.terminal_remote import main; main()"])
            .arg(&options.package_root).args(["--action",kind,"--identifier",identifier]);
        if options.demo {
            command.arg("--demo");
        }
        if let Some(db) = &options.db {
            command.arg("--db").arg(db);
        }
        Self::spawn(command, None, true)
    }
}
impl Drop for Task {
    fn drop(&mut self) {
        if let Ok(mut child) = self.child.lock() {
            kill_owned(&mut child);
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

pub fn dispatch(
    action: crate::app::Action,
    options: &Options,
    app: &mut crate::app::App,
    task: &mut Option<Task>,
) {
    use crate::{app::Action, local, ui};
    if action == Action::Cancel {
        task.take();
        app.action_busy = false;
        app.confirm("Action locale/d'observation arrêtée. Aucun job annulé.");
        return;
    }
    if task.is_some() {
        app.confirm("Une action est déjà en cours ; X pour l'arrêter.");
        return;
    }
    let started = match action {
        Action::Copy(path) => {
            let Some(mut value) = app.copy_value(path) else {
                app.confirm("Aucune valeur à copier.");
                return;
            };
            if path && app.anonymized {
                value = "[chemin masqué]".into();
            }
            Task::local(options, "copy", value, None)
        }
        Action::Export => {
            let Some(path) = local::export_path() else {
                app.confirm("Dossier local d'export indisponible.");
                return;
            };
            Task::local(options, "export", ui::summary(app), Some(path))
        }
        Action::Remote(kind) => {
            let identifier = if matches!(kind, "service" | "allocation") {
                app.data
                    .sessions
                    .get(app.sessions_table.selected().unwrap_or(0))
                    .map(|row| {
                        if kind == "allocation" {
                            row.job_id.clone()
                        } else {
                            row.id.clone()
                        }
                    })
            } else {
                app.selected_job().map(|row| row.id.clone())
            };
            let Some(identifier) = identifier.filter(|id| !id.is_empty()) else {
                app.confirm("Aucune opération soumise à interroger.");
                return;
            };
            Task::remote(
                options,
                if kind == "allocation" { "status" } else { kind },
                &identifier,
            )
        }
        _ => return,
    };
    match started {
        Ok(started) => {
            *task = Some(started);
            app.action_busy = true;
            app.notice = None;
        }
        Err(_) => app.confirm("Action indisponible ; dernières preuves conservées."),
    }
}

/// Restores mouse tracking even if the event loop returns an IO error.
#[derive(Default)]
pub struct MouseCapture(bool);

impl MouseCapture {
    pub fn update(&mut self, enabled: bool) -> io::Result<()> {
        if self.0 != enabled {
            if enabled {
                crossterm::execute!(std::io::stdout(), crossterm::event::EnableMouseCapture)?;
            } else {
                crossterm::execute!(std::io::stdout(), crossterm::event::DisableMouseCapture)?;
            }
            self.0 = enabled;
        }
        Ok(())
    }
}
impl Drop for MouseCapture {
    fn drop(&mut self) {
        let _ = self.update(false);
    }
}

pub fn helper(kind: &str) -> io::Result<()> {
    let mut bytes = Vec::new();
    std::io::stdin().take(131073).read_to_end(&mut bytes)?;
    if bytes.len() > 131072 {
        return Err(io::Error::other("Action trop volumineuse."));
    }
    let value: serde_json::Value = serde_json::from_slice(&bytes).map_err(io::Error::other)?;
    let text = value["value"]
        .as_str()
        .ok_or_else(|| io::Error::other("Valeur d'action absente."))?;
    let message = match kind {
        "copy" => {
            crate::local::copy(text)?;
            "Valeur copiée.".to_owned()
        }
        "export" => {
            let path = value["path"]
                .as_str()
                .ok_or_else(|| io::Error::other("Destination absente."))?;
            crate::local::export(std::path::Path::new(path), text)?;
            format!("Résumé exporté : {path}")
        }
        _ => return Err(io::Error::other("Action locale inconnue.")),
    };
    println!("{}", serde_json::json!({"ok":true,"message":message}));
    Ok(())
}
