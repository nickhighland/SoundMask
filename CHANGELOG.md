# Changelog

All notable changes to SoundMask should be documented in this file.

The format is inspired by Keep a Changelog, with an `Unreleased` section at the top so ongoing work has a clear place to live before the next version bump.

## [Unreleased]

- Update this section as work lands, then roll the notes into the next versioned release.

## [0.1.12] - 2026-07-01

### Added

- Added configurable timezone support so schedule logic and UI timestamps can follow the selected local timezone.
- Added a dashboard master volume slider for live playback control.
- Added a layered sound mix library with embedded sample sounds, per-layer volume, and uploadable custom sounds.
- Added persistent sound categories, including support for categorizing uploads into existing or new groups.
- Added a `Mute Current Session` dashboard action that silences only the appointment window currently driving playback.

### Changed

- Polished the dashboard, sounds, logs, and updates screens for a cleaner and more consistent interface.
- Improved calendar settings cards so long Google calendar IDs and `.ics` feed URLs wrap cleanly inside their panels.
- Normalized legacy `Travel & Transit` sounds into the `Transportation` category.

### Fixed

- Fixed sidebar transitions between desktop and accordion layouts across breakpoint changes and window resizes.
- Fixed the dashboard `Today's Schedule` timeline so completed sessions stay visible for the rest of the day.
- Fixed sound categorization edge cases so names like `Train Passing` no longer match `rain` accidentally.

## [0.1.11] - 2026-06-30

### Fixed

- Fixed responsive sidebar resize behavior when moving from the compact accordion layout back to the full desktop navigation.

## [0.1.10] - 2026-06-30

### Fixed

- Fixed sidebar accordion visibility so the navigation does not disappear unexpectedly.

## [0.1.9] - 2026-06-30

### Fixed

- Fixed the mobile menu breakpoint logic so the compact navigation activates at the correct viewport width.

## [0.1.8] - 2026-06-30

### Added

- Added a mobile-friendly sidebar accordion for smaller screens.

## [0.1.7] - 2026-06-30

### Fixed

- Fixed calendar block mutation issues that could distort or collapse appointment rendering.

## [0.1.6] - 2026-06-30

### Changed

- Stopped tracking the placeholder data directory file in git.

## [0.1.5] - 2026-06-30

### Fixed

- Fixed Google Calendar view sync fidelity so the visual calendar mirrors appointment timing more accurately.

## [0.1.4] - 2026-06-30

### Fixed

- Fixed Linux update installs so untracked files in the checkout no longer block appliance updates.

## [0.1.3] - 2026-06-30

### Fixed

- Fixed stalled queued update installs on Linux appliances.

## [0.1.2] - 2026-06-30

### Fixed

- Fixed calendar slot rendering issues.
- Refreshed branding and presentation details in the UI.

## [0.1.1] - 2026-06-30

### Added

- Added the visual calendar page.
- Added the in-app log viewer.
- Added Linux appliance update and startup improvements.

### Changed

- Improved Linux appliance controls and deployment flow.
- Increased playback volume headroom for appliance installs.
- Updated the repository URL in the README and install docs.

### Fixed

- Fixed manual playback IPC race conditions.
- Fixed manual update checks.

## [0.1.0] - 2026-06-29

### Added

- Initial Linux installation packaging and project versioning scaffold.
