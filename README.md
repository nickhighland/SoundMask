# SoundMask

SoundMask is a local-first sound-masking appliance for counseling offices. It runs a FastAPI web UI, watches either Google Calendar or a selected `.ics` feed/file, and loops a chosen local sound through `mpv` whenever an appointment window is active.

## Privacy

SoundMask does not use microphones, recording, transcription, analytics, remote backends, or cloud databases. All control data stays on the device. In Title Match Mode, SoundMask must read Google Calendar event summaries to decide whether a rule matches. Use a generic appointment title such as `Counseling appointment` and avoid client names or PHI in event titles.

By default, SoundMask stores only minimal trigger cache data:

- Hashed event ID
- Hashed summary
- Start and end timestamps
- Calendar ID
- Matched rule ID

It does not store descriptions, attendees, locations, conference links, notes, or attachments.

## What It Does

- Runs locally on macOS during development and Linux in production
- Plays a selected local sound while a trigger block is active
- Supports `freebusy`, `title_match`, and `fake` trigger modes
- Supports Google Calendar API and `.ics` calendar sources
- Supports manual play, manual stop, mute, buffers, active hours, and sound testing
- Uses SQLite for local settings and cache state

## Hardware Requirements

- macOS development machine or Debian/Ubuntu Linux device
- Dell Wyse 5070 supported for production target
- Powered speaker connected by 3.5mm audio or USB audio
- Reliable LAN access for the local web UI

## macOS Development Setup

```bash
brew install python mpv ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
soundmask serve --host 127.0.0.1 --port 8080 --reload
```

Open http://127.0.0.1:8080

## Linux Production Setup

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/nickhighland/SoundMask.git ~/src/SoundMask
cd ~/src/SoundMask
sudo bash scripts/install-linux.sh
```

The installer will:

- Sync the checked-out repo into `/opt/SoundMask`
- Create persistent app data under `/var/lib/soundmask`
- Generate `/etc/soundmask/soundmask.env` with a stable session secret
- Install and restart `soundmask.service`

Then open `http://soundmask.local` or `http://DEVICE-IP`

If you want a different appliance web port later, open `Settings` in the app and use the `Web access port` section. SoundMask will update its Linux config and restart on the new port automatically.

## Google Calendar Setup

1. Create a Google Cloud OAuth client for a desktop or web application.
2. Enable the Google Calendar API.
3. Place the client secret JSON in `/var/lib/soundmask/tokens/client_secret.json` on Linux or `~/.SoundMask/tokens/client_secret.json` on macOS, or set `SOUNDMASK_GOOGLE_CLIENT_SECRET`.
4. Open the Calendar Settings page and start OAuth.

## `.ics` Setup

1. Open the Calendar Settings page.
2. Set the Calendar Source to `.ics` feed or file.
3. Add a local path, `file://` path, `https://` URL, or `webcal://` feed.
4. Keep `freebusy` to treat matching events as busy blocks, or switch to `title_match` to apply title rules.

## FreeBusy Mode

FreeBusy Mode is the privacy-friendly default. It triggers sound whenever the selected calendar source is busy and does not need event titles.

Recommended defaults:

- Start buffer: 2 minutes
- End buffer: 3 minutes
- Max event duration: 240 minutes

## Title Match Mode

Title Match Mode uses Google event metadata or `.ics` event summaries and only needs limited title data to decide whether a rule matches.

When Google is the selected source, SoundMask requests only:

- `id`
- `summary`
- `start`
- `end`
- `status`
- `transparency`

Default rule: exact match for `Counseling appointment`

Supported match types:

- `exact`
- `contains`
- `starts_with`
- `ends_with`
- `regex`

## Recommended Calendar Title

Use `Counseling appointment` as the default event title. Keep titles generic to avoid PHI.

## Audio Setup

SoundMask uses `mpv` for playback:

```bash
mpv --no-video --loop-file=inf /path/to/sound.wav
```

Upload loops from the Sounds page, then mark one as active.

## Fake Mode Testing

Use Fake Mode when developing without Google Calendar:

1. Set trigger mode to `fake` on the Settings page.
2. Open the Dashboard.
3. Add a fake block starting in 1 minute and lasting 3 minutes.
4. Confirm SoundMask starts and stops around the buffered window.

## systemd Service

The included service file is in `systemd/soundmask.service` and reads runtime configuration from `/etc/soundmask/soundmask.env`.

```bash
sudo systemctl status soundmask.service
sudo systemctl restart soundmask.service
```

Common production settings:

- `SOUNDMASK_HOST=0.0.0.0`
- `SOUNDMASK_PORT=80`
- `SOUNDMASK_DATA_DIR=/var/lib/soundmask`
- `SOUNDMASK_SESSION_SECRET=<generated-by-installer>`

You can change the Linux web port from the app at `Settings` -> `Web access port`, or manually with:

```bash
sudo sed -i 's/^SOUNDMASK_PORT=.*/SOUNDMASK_PORT=8081/' /etc/soundmask/soundmask.env
sudo systemctl restart soundmask.service
```

## Updates

- Linux installs check for updates once per day.
- Open the `Updates` page in the app to run an immediate check or install the next available update.
- Update installs restart SoundMask automatically after the new code is applied.
- Manual checks run in the web app process, and the installer now registers `/opt/SoundMask` as a trusted git checkout so Git will not block update checks with a `safe.directory` warning.
- Current Linux builds also grant the `soundmask` service user permission to start the root-owned update installer directly, so the `Install Update` button does not have to rely only on a filesystem watcher.

If you need to manually update an older appliance build that predates the `safe.directory` fix:

```bash
cd /opt/SoundMask
sudo git config --system --add safe.directory /opt/SoundMask
sudo git pull --ff-only origin main
sudo bash scripts/install-linux.sh
```

If `git pull` complains about permissions inside `.git`, repair that once and retry:

```bash
sudo chown -R soundmask:soundmask /opt/SoundMask/.git
```

If the `Install Update` button stays stuck on `Install queued`, manually update once with the commands above so the appliance picks up the direct-start update fix.

## Troubleshooting Audio

- Confirm `mpv` is installed and available on `PATH`
- Confirm the selected sound file exists in the platform-specific sounds directory
- On Linux, verify the device output with `aplay -l` and `alsamixer`
- If `speaker-test` works in your shell but not in SoundMask, test as the service user too: `sudo -u soundmask speaker-test -c 2 -t sine -l 1`
- Re-run `sudo bash scripts/install-linux.sh` after audio-related updates so the `soundmask` service user is added to the `audio` group
- Test the sound from the dashboard or sounds page

## Troubleshooting Google OAuth

- Confirm the Calendar API is enabled in Google Cloud
- Confirm the OAuth client secret JSON path is correct
- If you switch from FreeBusy Mode to Title Match Mode, reconnect so the token has the required scope
- If Google is unavailable, SoundMask falls back to cached same-day blocks when available

## Troubleshooting `.ics`

- Confirm the local file path or feed URL is reachable from the SoundMask host
- If using `webcal://`, SoundMask converts it to `https://`
- All-day events are ignored by default when `Ignore all-day events` is enabled in Settings
- If a remote feed is temporarily unavailable, SoundMask falls back to cached blocks when available

## Security Notes

- The web UI is password-protected and stores only a password hash
- Session cookies are HTTP-only
- Bind to `127.0.0.1` in development
- Do not expose SoundMask directly to the public internet
- Place it on a trusted LAN only

## Git and Packaging

- Put this project in a git repo before distributing it because the Linux install flow expects a cloned checkout as its source.
- Local package install now works with `pip install .` or `pip install -e .[dev]`.
- The app exposes a `soundmask` CLI entrypoint for development and production service startup.

## Project Layout

- `app/`: FastAPI application, scheduler, audio, calendar client, templates, static assets
- `sounds/`: Documentation for accepted sound assets
- `data/`: Workspace placeholder for local data
- `tests/`: Pure-logic and scheduler tests
- `scripts/`: Development and Linux installation scripts
- `systemd/`: Production service unit and example env file
