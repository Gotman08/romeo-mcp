//! Viewer preferences only. These files never contain MCP credentials or filters.
use crate::{app::View, query::SortOrder};
use serde::{Deserialize, Serialize};
use std::{
    fs,
    io::{self, Read, Write},
    path::{Path, PathBuf},
};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize, clap::ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum LayoutMode {
    #[default]
    Split,
    List,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Panel {
    #[default]
    List,
    Detail,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Preferences {
    pub schema: u8,
    pub view: View,
    pub sorts: [SortOrder; 3],
    pub layout: LayoutMode,
    pub detail_percent: u16,
    pub job_stale_after: u64,
    pub transfer_stale_after: u64,
}

impl Default for Preferences {
    fn default() -> Self {
        Self {
            schema: 1,
            view: View::Overview,
            sorts: [SortOrder::Activity, SortOrder::Date, SortOrder::Date],
            layout: LayoutMode::Split,
            detail_percent: 40,
            job_stale_after: 300,
            transfer_stale_after: 60,
        }
    }
}

impl Preferences {
    fn valid(&self) -> bool {
        self.schema == 1
            && (25..=65).contains(&self.detail_percent)
            && (1..=86400).contains(&self.job_stale_after)
            && (1..=86400).contains(&self.transfer_stale_after)
    }
}

pub fn directory() -> Option<PathBuf> {
    std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
        .map(|home| PathBuf::from(home).join(".romeo-mcp").join("viewer"))
}

pub fn load(path: &Path) -> io::Result<Preferences> {
    if path.is_symlink() {
        return Err(io::Error::other("Préférences liées à un autre fichier."));
    }
    let mut bytes = Vec::new();
    fs::File::open(path)?.take(65537).read_to_end(&mut bytes)?;
    if bytes.len() > 65536 {
        return Err(io::Error::other("Préférences trop volumineuses."));
    }
    let preferences: Preferences = serde_json::from_slice(&bytes).map_err(io::Error::other)?;
    if !preferences.valid() {
        return Err(io::Error::other("Préférences incompatibles."));
    }
    Ok(preferences)
}

pub fn save(path: &Path, preferences: &Preferences) -> io::Result<()> {
    if !preferences.valid() || path.is_symlink() {
        return Err(io::Error::other("Préférences invalides."));
    }
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
    let temporary = path.with_extension(format!("{}.tmp", std::process::id()));
    let mut created = false;
    let result = (|| {
        let mut options = fs::OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options.open(&temporary)?;
        created = true;
        file.write_all(&serde_json::to_vec_pretty(preferences).map_err(io::Error::other)?)?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, path)
    })();
    if result.is_err() && created {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_known_preferences_are_accepted() {
        let preferences = Preferences::default();
        let encoded = serde_json::to_value(&preferences).unwrap();
        assert!(!encoded.to_string().contains("filters"));
        let mut invalid = encoded.clone();
        invalid["account"] = "unrelated-secret".into();
        assert!(serde_json::from_value::<Preferences>(invalid).is_err());
        let mut invalid: Preferences = serde_json::from_value(encoded).unwrap();
        invalid.detail_percent = 99;
        assert!(!invalid.valid());
    }
    #[test]
    fn preferences_round_trip_and_replace_atomically() {
        let path =
            std::env::temp_dir().join(format!("romeo-viewer-prefs-{}.json", std::process::id()));
        let mut expected = Preferences::default();
        save(&path, &expected).unwrap();
        expected.view = View::Transfers;
        expected.layout = LayoutMode::List;
        save(&path, &expected).unwrap();
        assert_eq!(load(&path).unwrap(), expected);
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn relative_preference_filename_can_be_saved_and_loaded() {
        let path = PathBuf::from(format!("romeo-viewer-relative-{}.json", std::process::id()));
        assert!(!path.exists());
        let expected = Preferences::default();
        save(&path, &expected).unwrap();
        let actual = load(&path);
        fs::remove_file(path).unwrap();
        assert_eq!(actual.unwrap(), expected);
    }
}
