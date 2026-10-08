//! One Python reader, bounded channels and explicit cleanup on dashboard exit.
use crate::{app::ReadRequest, model::Snapshot, Options};
use std::{
    io::{BufRead, BufReader, Read, Write},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, SyncSender},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
};

const MAX_LINE: u64 = 2 * 1024 * 1024;
const BOOTSTRAP: &str = "import sys; sys.path.insert(0, sys.argv.pop(1)); from romeo_mcp.terminal_data import bridge; bridge()";

pub struct Reader {
    child: Child,
    requests: Option<SyncSender<String>>,
    pub responses: Receiver<Result<Snapshot, String>>,
    stopped: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
    progress: Arc<Mutex<Option<Progress>>>,
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Progress {
    message: String,
    pub request_id: u64,
    phase: String,
    processed: u64,
    total: Option<u64>,
}

impl Progress {
    fn parse(line: &str) -> Option<Self> {
        let value: Self = serde_json::from_str(line).ok()?;
        (value.message == "progress"
            && value.request_id <= (1 << 53)
            && matches!(value.phase.as_str(), "jobs" | "transfers" | "reports")
            && value.total.is_none_or(|total| value.processed <= total))
        .then_some(value)
    }
    pub fn label(&self) -> String {
        let source = match self.phase.as_str() {
            "jobs" => "jobs",
            "transfers" => "transferts",
            _ => "rapports",
        };
        format!(
            "Inventaire {source} : {}{}",
            self.processed,
            self.total
                .map(|total| format!("/{total}"))
                .unwrap_or_default()
        )
    }
}

impl Reader {
    pub fn start(options: &Options) -> std::io::Result<Self> {
        // The package root is a trusted launcher argument; Python -I excludes
        // ambient PYTHONPATH and the working directory. No shell is involved.
        let mut arguments = vec![
            "-X".into(),
            "utf8".into(),
            "-I".into(),
            "-u".into(),
            "-c".into(),
            BOOTSTRAP.into(),
            options.package_root.as_os_str().to_owned(),
            "--limit".into(),
            options.limit.to_string().into(),
        ];
        if options.demo {
            arguments.push("--demo".into());
        }
        if let Some(db) = &options.db {
            arguments.extend(["--db".into(), db.as_os_str().to_owned()]);
        }
        let mut command = Command::new(&options.python);
        command
            .args(arguments)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW, only for the private reader.
        }
        let mut child = command.spawn()?;
        let mut input = child.stdin.take().expect("piped stdin");
        let mut output = BufReader::new(child.stdout.take().expect("piped stdout"));
        let (requests, receive_request) = mpsc::sync_channel::<String>(1);
        let (send_response, responses) = mpsc::sync_channel(1);
        let stopped = Arc::new(AtomicBool::new(false));
        let thread_stopped = Arc::clone(&stopped);
        let progress = Arc::new(Mutex::new(None));
        let thread_progress = Arc::clone(&progress);
        let thread = thread::spawn(move || {
            while let Ok(request) = receive_request.recv() {
                let result = (|| {
                    input
                        .write_all(request.as_bytes())
                        .map_err(|_| "Lecteur local arrêté.")?;
                    input
                        .write_all(b"\n")
                        .map_err(|_| "Lecteur local arrêté.")?;
                    input.flush().map_err(|_| "Lecteur local arrêté.")?;
                    loop {
                        let mut line = String::new();
                        (&mut output)
                            .take(MAX_LINE + 1)
                            .read_line(&mut line)
                            .map_err(|_| "Réponse du lecteur local illisible.")?;
                        if line.is_empty() || line.len() as u64 > MAX_LINE || !line.ends_with('\n')
                        {
                            return Err(
                                "Lecteur local arrêté ou réponse trop volumineuse.".to_owned()
                            );
                        }
                        if let Some(value) = Progress::parse(&line) {
                            if let Ok(mut slot) = thread_progress.lock() {
                                *slot = Some(value);
                            }
                            continue;
                        }
                        return Snapshot::parse(&line);
                    }
                })();
                let failed = result.is_err();
                if send_response.try_send(result).is_err() || failed {
                    break;
                }
            }
            thread_stopped.store(true, Ordering::Release);
        });
        Ok(Self {
            child,
            requests: Some(requests),
            responses,
            stopped,
            thread: Some(thread),
            progress,
        })
    }

    pub fn refresh(&self, request: &ReadRequest) -> bool {
        let Ok(request) = serde_json::to_string(request) else {
            return false;
        };
        if request.len() > 4096 {
            return false;
        }
        !self.stopped()
            && self
                .requests
                .as_ref()
                .is_some_and(|requests| requests.try_send(request).is_ok())
    }

    pub fn stopped(&self) -> bool {
        self.stopped.load(Ordering::Acquire)
    }

    pub fn progress(&self) -> Option<Progress> {
        self.progress.lock().ok()?.take()
    }
}

impl Drop for Reader {
    fn drop(&mut self) {
        // A blocked filesystem read cannot keep an orphan alive after q/Ctrl-C.
        self.requests.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::Progress;
    #[test]
    fn progress_is_bounded_to_inventory_messages() {
        let line = r#"{"message":"progress","request_id":3,"phase":"transfers","processed":50,"total":100}"#;
        let value = Progress::parse(line).unwrap();
        assert_eq!(value.label(), "Inventaire transferts : 50/100");
        assert!(Progress::parse(&line.replace("100}", "40}")).is_none());
        assert!(Progress::parse(&line.replace("transfers", "private-path")).is_none());
    }
}
