//! One Python reader, bounded channels and explicit cleanup on dashboard exit.
use crate::{model::Snapshot, Options};
use std::{
    io::{BufRead, BufReader, Read, Write},
    process::{Child, Command, Stdio},
    sync::mpsc::{self, Receiver, SyncSender},
    thread,
};

const MAX_LINE: u64 = 2 * 1024 * 1024;
const BOOTSTRAP: &str = "import sys; sys.path.insert(0, sys.argv.pop(1)); from romeo_mcp.terminal_data import bridge; bridge()";

pub struct Reader {
    child: Child,
    requests: SyncSender<()>,
    pub responses: Receiver<Result<Snapshot, String>>,
}

impl Reader {
    pub fn start(options: &Options) -> std::io::Result<Self> {
        // The package root is a trusted launcher argument; Python -I excludes
        // ambient PYTHONPATH and the working directory. No shell is involved.
        let mut arguments = vec![
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
        let (requests, receive_request) = mpsc::sync_channel(1);
        let (send_response, responses) = mpsc::sync_channel(1);
        thread::spawn(move || {
            while receive_request.recv().is_ok() {
                let result = (|| {
                    input
                        .write_all(b"snapshot\n")
                        .map_err(|_| "Lecteur local arrêté.")?;
                    input.flush().map_err(|_| "Lecteur local arrêté.")?;
                    let mut line = String::new();
                    (&mut output)
                        .take(MAX_LINE + 1)
                        .read_line(&mut line)
                        .map_err(|_| "Réponse du lecteur local illisible.")?;
                    if line.is_empty() || line.len() as u64 > MAX_LINE || !line.ends_with('\n') {
                        return Err("Lecteur local arrêté ou réponse trop volumineuse.".to_owned());
                    }
                    Snapshot::parse(&line)
                })();
                let failed = result.is_err();
                if send_response.send(result).is_err() || failed {
                    break;
                }
            }
        });
        Ok(Self {
            child,
            requests,
            responses,
        })
    }

    pub fn refresh(&self) -> bool {
        self.requests.try_send(()).is_ok()
    }
}

impl Drop for Reader {
    fn drop(&mut self) {
        // A blocked filesystem read cannot keep an orphan alive after q/Ctrl-C.
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
