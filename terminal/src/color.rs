//! Explicit color policy; only the native viewer's output is configured.
use clap::ValueEnum;

#[derive(Clone, Copy, Debug, Default, ValueEnum)]
pub enum ColorMode {
    #[default]
    Auto,
    Always,
    Never,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Palette {
    #[default]
    Color,
    NoColorEnvironment,
    Monochrome,
}

impl ColorMode {
    pub fn palette(self, no_color: Option<&str>) -> Palette {
        match self {
            Self::Never => Palette::Monochrome,
            Self::Auto if no_color.is_some_and(|value| !value.is_empty()) => {
                Palette::NoColorEnvironment
            }
            _ => Palette::Color,
        }
    }
}

impl Palette {
    pub fn description(self) -> &'static str {
        match self {
            Self::Color => "Couleurs actives",
            Self::NoColorEnvironment => "Monochrome (NO_COLOR)",
            Self::Monochrome => "Monochrome (--color never)",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn explicit_modes_override_environment_and_auto_respects_nonempty_no_color() {
        assert_eq!(
            ColorMode::Auto.palette(Some("1")),
            Palette::NoColorEnvironment
        );
        assert_eq!(ColorMode::Auto.palette(Some("")), Palette::Color);
        assert_eq!(ColorMode::Auto.palette(None), Palette::Color);
        assert_eq!(ColorMode::Always.palette(Some("1")), Palette::Color);
        assert_eq!(ColorMode::Never.palette(None), Palette::Monochrome);
    }
}
