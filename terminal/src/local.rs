//! Explicit local actions, independent of collection and MCP execution.
use std::{
    fs,
    io::{self, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub fn export(path: &Path, text: &str) -> io::Result<()> {
    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let mut directories = fs::DirBuilder::new();
    directories.recursive(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        directories.mode(0o700);
    }
    directories.create(parent)?;
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(path)?;
    file.write_all(text.as_bytes())?;
    file.sync_all()
}

pub fn export_path() -> Option<PathBuf> {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .ok()?
        .as_nanos();
    crate::preferences::directory()
        .map(|root| root.join("exports").join(format!("romeo-{stamp}.txt")))
}

struct OwnedChild(Child);
impl Drop for OwnedChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn send(command: &mut Command, value: &str, deadline: Instant) -> io::Result<()> {
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    let mut child = OwnedChild(command.spawn()?);
    child
        .0
        .stdin
        .take()
        .ok_or_else(|| io::Error::other("Entrée du presse-papiers absente."))?
        .write_all(value.as_bytes())?;
    loop {
        if let Some(status) = child.0.try_wait()? {
            return if status.success() {
                Ok(())
            } else {
                Err(io::Error::other("Presse-papiers indisponible."))
            };
        }
        if Instant::now() >= deadline {
            return Err(io::Error::other("Le presse-papiers ne répond pas."));
        }
        thread::sleep(Duration::from_millis(20));
    }
}

pub fn copy(value: &str) -> io::Result<()> {
    if value.is_empty() || value.len() > 4096 {
        return Err(io::Error::other("Valeur à copier absente ou trop longue."));
    }
    let deadline = Instant::now() + Duration::from_secs(2);
    #[cfg(windows)]
    {
        let mut command = Command::new("powershell.exe");
        command.args(["-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
            "[Console]::InputEncoding=[Text.UTF8Encoding]::new($false); $v=[Console]::In.ReadToEnd(); Set-Clipboard -Value $v"]);
        send(&mut command, value, deadline)
    }
    #[cfg(not(windows))]
    {
        let backends: &[(&str, &[&str])] = if cfg!(target_os = "macos") {
            &[("pbcopy", &[])]
        } else {
            &[
                ("wl-copy", &[]),
                ("xclip", &["-selection", "clipboard"]),
                ("xsel", &["--clipboard", "--input"]),
            ]
        };
        for (program, args) in backends {
            if Instant::now() >= deadline {
                break;
            }
            if send(Command::new(program).args(*args), value, deadline).is_ok() {
                return Ok(());
            }
        }
        Err(io::Error::other(
            "Presse-papiers indisponible ; e exporte un résumé.",
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn an_export_never_overwrites_an_existing_file() {
        let path =
            std::env::temp_dir().join(format!("romeo-export-test-{}.txt", std::process::id()));
        export(&path, "Première observation — état à vérifier").unwrap();
        assert!(export(&path, "must not replace").is_err());
        assert!(fs::read_to_string(&path)
            .unwrap()
            .starts_with("Première observation"));
        fs::remove_file(path).unwrap();
    }
    #[test]
    fn a_blocked_clipboard_helper_is_bounded_and_reaped() {
        let mut command = Command::new(std::env::current_exe().unwrap());
        command.args([
            "--ignored",
            "--exact",
            "local::tests::blocked_clipboard_fixture",
        ]);
        let started = Instant::now();
        assert!(send(
            &mut command,
            "Synthetic test only",
            started + Duration::from_millis(50)
        )
        .is_err());
        assert!(started.elapsed() < Duration::from_secs(2));
    }
    #[test]
    #[ignore]
    fn blocked_clipboard_fixture() {
        thread::sleep(Duration::from_secs(5));
    }
}
