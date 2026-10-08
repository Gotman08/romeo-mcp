//! Accent-tolerant display search and deterministic ordering of bounded records.
use serde::{Deserialize, Serialize};
use std::cmp::Ordering;
use unicode_normalization::{char::is_combining_mark, UnicodeNormalization};

pub fn normalize(value: &str) -> String {
    value
        .nfkd()
        .filter(|c| !is_combining_mark(*c))
        .flat_map(char::to_lowercase)
        .collect()
}

pub fn matches(query: &str, fields: &[&str]) -> bool {
    query.is_empty() || normalize(&fields.join(" ")).contains(query)
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SortOrder {
    Activity,
    #[default]
    Date,
    State,
    Priority,
}

impl SortOrder {
    pub fn next(self) -> Self {
        match self {
            Self::Activity => Self::Date,
            Self::Date => Self::State,
            Self::State => Self::Priority,
            Self::Priority => Self::Activity,
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Activity => "Actifs d'abord",
            Self::Date => "Date ↓",
            Self::State => "État A–Z",
            Self::Priority => "Priorité",
        }
    }
}

pub struct Key {
    pub active: bool,
    pub priority: u8,
    pub date: Option<f64>,
    pub state: String,
    pub id: String,
}

impl Key {
    pub fn new(priority: u8, date: Option<f64>, state: &str, id: &str) -> Self {
        Self {
            active: false,
            priority,
            date: date.filter(|time| time.is_finite() && *time > 0.0),
            state: normalize(state),
            id: id.into(),
        }
    }

    fn compare(&self, other: &Self, order: SortOrder) -> Ordering {
        let recent = || {
            other
                .date
                .unwrap_or(0.0)
                .total_cmp(&self.date.unwrap_or(0.0))
        };
        match order {
            SortOrder::Activity => other
                .active
                .cmp(&self.active)
                .then_with(|| (self.priority != 0).cmp(&(other.priority != 0)))
                .then_with(recent),
            SortOrder::Date => recent(),
            SortOrder::State => self.state.cmp(&other.state).then_with(recent),
            SortOrder::Priority => self.priority.cmp(&other.priority).then_with(recent),
        }
        .then_with(|| self.id.cmp(&other.id))
    }
}

pub fn order<T>(rows: Vec<&T>, sort: SortOrder, key: impl Fn(&T) -> Key) -> Vec<&T> {
    let mut keyed: Vec<_> = rows.into_iter().map(|row| (key(row), row)).collect();
    keyed.sort_by(|(a, _), (b, _)| a.compare(b, sort));
    keyed.into_iter().map(|(_, row)| row).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn search_matches_case_accents_and_decomposed_unicode() {
        assert!(matches(&normalize("TERMINE"), &["Terminé", "completed"]));
        assert!(matches(&normalize("échec"), &["ECHEC", "failed"]));
        assert_eq!(normalize("Prépare\u{301}"), normalize("PRÉPARÉ"));
    }

    #[test]
    fn dates_without_evidence_sort_last_and_priority_is_deterministic() {
        let keys = [
            Key::new(2, Some(100.0), "En cours", "a"),
            Key::new(0, None, "Échec", "b"),
            Key::new(2, Some(200.0), "En cours", "c"),
        ];
        assert_eq!(
            keys[0].compare(&keys[2], SortOrder::Date),
            Ordering::Greater
        );
        assert_eq!(
            keys[1].compare(&keys[0], SortOrder::Date),
            Ordering::Greater
        );
        assert_eq!(
            keys[1].compare(&keys[0], SortOrder::Priority),
            Ordering::Less
        );
        assert_eq!(keys[1].compare(&keys[0], SortOrder::State), Ordering::Less);
    }
}
