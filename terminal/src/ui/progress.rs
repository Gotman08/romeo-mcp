//! A measured copy bar. Percentage never stands for integrity validation.
use super::{ACCENT, MUTED};
use crate::model::Progress;
use ratatui::{
    style::Style,
    text::{Line, Span},
};

pub(super) fn bar(progress: Option<&Progress>, width: usize) -> Line<'static> {
    let Some(percent) = progress.and_then(Progress::percent) else {
        return Line::from("—");
    };
    let label = format!("{percent:3} %");
    let length = width.saturating_sub(6).min(40);
    if length < 3 {
        return Line::from(label);
    }
    let filled = length * percent as usize / 100;
    Line::from(vec![
        Span::raw(format!("{label} ")),
        Span::styled("━".repeat(filled), Style::default().fg(ACCENT)),
        Span::styled("─".repeat(length - filled), Style::default().fg(MUTED)),
    ])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_valid_measurements_fill_the_bar() {
        let mut progress = Progress {
            bytes_transferred: 40,
            bytes_total: Some(100),
            ..Progress::default()
        };
        assert_eq!(bar(Some(&progress), 16).to_string(), " 40 % ━━━━──────");
        progress.bytes_total = None;
        assert_eq!(bar(Some(&progress), 16).to_string(), "—");
        progress.percent_reported = Some(100);
        assert_eq!(bar(Some(&progress), 16).to_string(), "100 % ━━━━━━━━━━");
        assert_eq!(bar(None, 16).to_string(), "—");
    }
}
