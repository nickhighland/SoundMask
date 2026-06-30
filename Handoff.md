# SoundMask Handoff

## Project Summary

SoundMask is a local-first sound-masking appliance app for a counseling office. It is built as a Python 3.11+ FastAPI application with a local web UI, SQLite storage, background scheduling, and `mpv`-based audio playback.

The intended user flow is:

1. Start the app locally.
2. Complete first-run password setup.
3. Upload a masking sound.
4. Select a trigger mode.
5. Let the scheduler decide when sound should play.

The current implementation is focused on the original Google Calendar API path, plus a fake trigger mode for development and testing.

## What Has Been Built

### Core application

- FastAPI app entrypoint in `app/main.py`
- Jinja2 template rendering and static asset serving
- Session middleware with login and first-run password setup
- Local SQLite database bootstrap and default settings seeding
- Platform-aware data path handling in `app/config.py`

### Authentication

- First-run admin password creation
- Password hashing with `passlib[bcrypt]`
- Session-based login/logout
- HTTP-only session cookies

### Sound playback

- Single-process `mpv` playback manager in `app/audio.py`
- Manual play
- Manual stop
- Mute state support
- Volume updates
- Test playback
- Looping playback of the selected sound

### Scheduler and trigger logic

- APScheduler background scheduler in `app/scheduler.py`
- Main sync loop plus a 10-second playback evaluation loop
- Fake mode trigger blocks for development
- Merge/buffer/playback decision helpers in `app/trigger_rules.py`
- Current/next block status reporting for the dashboard

### Calendar support

- Google OAuth scaffolding in `app/calendar_client.py`
- Google FreeBusy support
- Google Title Match support with limited requested event fields
- `.ics` feed and local file support with recurrence expansion
- Calendar selection and title rule management UI on the Calendar page

### Sound management

- Upload sound files
- Accept `.wav`, `.mp3`, `.ogg`, `.flac`
- Select active sound
- Test a sound
- Delete a sound

### UI

- Login/setup page
- Dashboard page
- Settings page
- Calendar page
- Sounds page
- Local CSS/JS for the web UI

### Tests

- Title match tests
- Busy block merge/buffer tests
- Playback decision tests
- Fake scheduler tests

### Deployment assets

- Linux install script in `scripts/install-linux.sh`
- Development runner in `scripts/run-dev.sh`
- `systemd` unit in `systemd/SoundMask.service`
- Top-level README with setup and usage notes

## How the App Works

### Request/UI layer

- `app/main.py` wires the FastAPI app, session middleware, templates, database, audio manager, calendar client, and scheduler.
- Route modules under `app/routes/` render templates and handle form submissions.

### Data layer

- `app/db.py` owns SQLite access.
- Settings are stored as key/value JSON-encoded rows in the `settings` table.
- Runtime state such as fake blocks, mute, and manual play windows is stored in `app_state`.
- Sounds, calendars, title rules, and cached trigger blocks have dedicated tables.

### Calendar normalization

- `app/calendar_client.py` fetches Google calendar data.
- FreeBusy mode uses busy windows only.
- Title Match mode fetches only:
  - `id`
  - `summary`
  - `start`
  - `end`
  - `status`
  - `transparency`
- Matching events are normalized into `TriggerBlock` objects.

### Trigger logic

- `app/trigger_rules.py` contains the pure decision helpers:
  - `merge_blocks`
  - `apply_buffers`
  - `is_now_in_active_block`
  - `get_next_block`
  - `should_play`
  - `matches_title`

### Playback loop

- `app/scheduler.py` runs the sync loop.
- It loads the current trigger mode.
- It fetches calendar data or fake blocks.
- It filters, merges, and buffers blocks.
- It stores cache state.
- It calls the audio manager to start or stop playback.

## Current Project Structure

- `app/`
  - FastAPI application code
- `app/routes/`
  - Dashboard, settings, sounds, calendar routes
- `app/templates/`
  - Jinja templates
- `app/static/`
  - CSS and JS
- `sounds/`
  - Sound usage notes
- `tests/`
  - Unit tests for pure logic and fake scheduling
- `scripts/`
  - Dev and Linux install scripts
- `systemd/`
  - Production service unit

## Verified So Far

These checks were completed successfully during development:

- `python3 -m venv .venv`
- `source .venv/bin/activate && pip install -r requirements.txt`
- `source .venv/bin/activate && python -m pytest tests`
- `source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8080`
- `curl http://127.0.0.1:8080/health`

At the time of the successful validation:

- All 14 tests passed.
- `/health` returned `{"status":"ok"}`.

## Current Gaps / Incomplete Areas

### ICS support

ICS support is now implemented as a first-class calendar source.

The app can store local `.ics` file paths and remote feed URLs, expand recurring events, and normalize them into the same `TriggerBlock` model used by the Google path.

### Linux appliance hardening

The app install path is implemented, but the full appliance experience is not finished. The following still need hardware-specific validation on the target Wyse box:

- Audio device selection
- Boot-time behavior on actual hardware
- LAN discovery and hostname behavior
- Real-world `systemd` restart behavior

### Production validation

The following still need real end-to-end validation on the production target:

- Google OAuth flow in the browser
- FreeBusy sync against a real calendar
- Title Match sync against a real calendar
- Playback through 3.5mm or USB audio on Linux

## Known State Notes

- The workspace currently contains a number of editor-reported style warnings, mostly line-length and newline-at-end-of-file issues.
- These were not the focus of implementation and were not fully cleaned up.
- The core logic and app startup were previously validated successfully despite that warning noise.
- Before making a release build, it would be worth doing one formatting/lint cleanup pass.

## Roadmap So Far

This mirrors the build plan that guided the current implementation.

### Phase 1: Project skeleton

- FastAPI app
- Jinja templates
- Static assets
- SQLite initialization
- Settings storage
- First-run admin password setup
- Login/logout

Status: largely complete

### Phase 2: Audio MVP

- Sound upload
- Active sound selection
- Manual play
- Manual stop
- Test sound
- Volume handling
- `mpv` integration

Status: complete at MVP level

### Phase 3: Fake trigger mode

- Fake trigger blocks
- Merge logic
- Buffer logic
- Playback decision loop
- Unit tests

Status: complete

### Phase 4: FreeBusy mode

- Google OAuth plumbing
- Calendar settings page
- FreeBusy sync
- Busy block normalization
- Trigger cache
- Sync status display

Status: mostly implemented, needs real-world validation

### Phase 5: Title Match mode

- Title rule management
- Default `Counseling appointment` rule
- Events API sync with limited fields
- Matching engine
- Hash-based cached event storage
- Tests

Status: mostly implemented, needs real-world validation

### Phase 6: Polish and production

- Active hours
- Mute/manual duration
- Dashboard status cards
- Error handling
- `systemd` service
- Linux install script
- README

Status: partially complete

## Suggestions for Further Development

### High-priority

1. Run a real Google OAuth and calendar sync validation pass.
2. Validate `.ics` feeds against a few real calendars, especially floating-time and timezone-heavy feeds.
3. Add partial-failure reporting when one `.ics` feed fails but others still sync.
4. Add tests for remote feed fetch failures and cache fallback behavior.
5. Confirm the Calendar UI copy is clear enough for non-technical admins.

### Production hardening

1. Add structured logging that avoids raw event summaries by default.
2. Validate `mpv` behavior on the Debian/Ubuntu target box.
3. Add startup checks for missing `mpv`, missing sound files, and missing Google credentials.
4. Add a clearer admin-facing error banner in the dashboard when sync fails.
5. Add backup/restore guidance for the SQLite DB and token files.

### UI improvements

1. Add inline validation messages on settings and calendar forms.
2. Show whether the current active block came from fake, freebusy, or title match mode.
3. Add a small diagnostics page for environment paths, sound status, sync status, and scheduler state.

### Code quality

1. Run a formatting pass across the project.
2. Clean up the current editor/lint warnings.
3. Add more isolated tests around scheduler fallback behavior and cache reuse on Google API failure.
4. Consider splitting the calendar provider logic behind a provider interface if `.ics` support is added.

## Recommended Next Steps for Codex

If handing this off to Codex, the most efficient order is:

1. Verify the current branch still boots and tests cleanly.
2. Clean up the existing warning noise so the next changes are easier to reason about.
3. Add end-to-end validation for the Google path, `.ics` path, and fake mode.
4. Validate Linux deployment on the actual target hardware.

## Files Most Important to Read First

- `app/main.py`
- `app/db.py`
- `app/scheduler.py`
- `app/calendar_client.py`
- `app/trigger_rules.py`
- `app/routes/calendar.py`
- `app/routes/dashboard.py`
- `README.md`

## Final Note

The project is in a good MVP state for the core local app, fake mode, sound management, and the initial Google calendar integration path. The biggest unfinished functional request after the original build is the dual Google/ICS calendar-source interface.
