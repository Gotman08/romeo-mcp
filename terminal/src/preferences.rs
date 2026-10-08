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
    pub sorts: [SortOrder; 4],
    pub layout: LayoutMode,
    pub detail_percent: u16,
    pub job_stale_after: u64,
    pub transfer_stale_after: u64,
    #[serde(default)]
    pub favorites: std::collections::BTreeSet<String>,
    #[serde(default)]
    pub notes: std::collections::BTreeMap<String, String>,
    #[serde(default)]
    pub notifications: bool,
    #[serde(default)]
    pub mouse: bool,
    #[serde(default)]
    pub anonymized: bool,
    #[serde(default = "default_id_width")]
    pub id_width: u16,
}
fn default_id_width() -> u16 {
    8
}

impl Default for Preferences {
    fn default() -> Self {
        Self {
            schema: 2,
            view: View::Overview,
            sorts: [
                SortOrder::Activity,
                SortOrder::Date,
                SortOrder::Date,
                SortOrder::Date,
            ],
            layout: LayoutMode::Split,
            detail_percent: 40,
            job_stale_after: 300,
            transfer_stale_after: 60,
            favorites: Default::default(),
            notes: Default::default(),
            notifications: false,
            mouse: false,
            anonymized: false,
            id_width: 8,
        }
    }
}

impl Preferences {
    fn valid(&self) -> bool {
        self.schema == 2
            && (25..=65).contains(&self.detail_percent)
            && (1..=86400).contains(&self.job_stale_after)
            && (1..=86400).contains(&self.transfer_stale_after)
            && (7..=32).contains(&self.id_width)
            && self.favorites.len() <= 1000
            && self.notes.len() <= 1000
            && self
                .favorites
                .iter()
                .chain(self.notes.keys())
                .all(|id| !id.is_empty() && id.len() <= 180 && !id.chars().any(char::is_control))
            && self
                .notes
                .values()
                .all(|note| note.chars().count() <= 500 && !note.chars().any(char::is_control))
            && self.notes.values().map(String::len).sum::<usize>() <= 256000
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
    fs::File::open(path)?
        .take(1048577)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 1048576 {
        return Err(io::Error::other("Préférences trop volumineuses."));
    }
    let mut value: serde_json::Value = serde_json::from_slice(&bytes).map_err(io::Error::other)?;
    if value["schema"] == 1 {
        if let Some(sorts) = value["sorts"].as_array_mut() {
            if sorts.len() == 3 {
                sorts.push("date".into());
            }
        }
        value["schema"] = 2.into();
    }
    let preferences: Preferences = serde_json::from_value(value).map_err(io::Error::other)?;
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

    #[test]
    fn legacy_preferences_migrate_and_local_annotations_round_trip() {
        let path = std::env::temp_dir().join(format!(
            "romeo-viewer-migration-{}.json",
            std::process::id()
        ));
        let mut legacy = serde_json::to_value(Preferences::default()).unwrap();
        legacy["schema"] = 1.into();
        legacy["sorts"].as_array_mut().unwrap().pop();
        for key in [
            "favorites",
            "notes",
            "notifications",
            "mouse",
            "anonymized",
            "id_width",
        ] {
            legacy.as_object_mut().unwrap().remove(key);
        }
        fs::write(&path, serde_json::to_vec(&legacy).unwrap()).unwrap();
        let mut expected = load(&path).unwrap();
        assert_eq!(expected.schema, 2);
        expected.favorites.insert("42".into());
        expected
            .notes
            .insert("42".into(), "Annotation synthétique".into());
        expected.anonymized = true;
        save(&path, &expected).unwrap();
        assert_eq!(load(&path).unwrap(), expected);
        fs::remove_file(path).unwrap();
        expected.notes.insert("43".into(), "x".repeat(501));
        assert!(!expected.valid());
    }
}
