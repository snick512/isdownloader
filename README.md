# iSnick Downloader

iSnick Downloader is a simple PyQt5-based GUI for downloading media from supported sites using [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features

- Download videos from YouTube, TikTok, Facebook, Instagram, Bluesky, or any HTTP/HTTPS URL (with "Allow Unlisted").
- Sandboxed download directory (default: `~/Videos/yt-dlp-gui`).
- Progress bar, speed display, and status updates.
- Configurable yt-dlp binary path.
- Simple site selection menu.
- Logging to `is.log`.
- Reset and Cancel options.
- Minimal configuration saved in `config.json`.

## Requirements

- Python 3.6+
- [PyQt5](https://pypi.org/project/PyQt5/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) binary (download separately)

## Usage

1. **Install dependencies:**
   ```sh
   pip install PyQt5
   ```
2. **Download the `yt-dlp` binary** and place it in the project directory or elsewhere on your system.

3. **Run the GUI:**
   ```sh
   python gui.py
   ```

4. **Configure:**
   - Set the path to your `yt-dlp` binary (unless preconfigured in `config.json`).
   - Paste a supported video URL.
   - Select the site from the menu (or "Allow Unlisted" for generic URLs).
   - Click **Download**.

5. **Downloads** will be saved to the sandbox directory (default: `~/Videos/yt-dlp-gui`).

## Configuration

Settings are saved in `config.json`:
- `binary`: Path to the yt-dlp binary.
- `sandbox_dir`: Download directory.
- `selected_site`: Last selected site.

## Security

- Only allows execution of binaries starting with `yt-dlp` and marked as executable.
- Download directory cannot be a symlink and must be writable.
- All downloads are sandboxed to the configured directory.

## Logging

All output and errors are logged to `is.log` in the project directory.

## Supported Sites

- YouTube
- TikTok
- Facebook
- Instagram
- Bluesky
- Any HTTP/HTTPS URL (with "Allow Unlisted")

## License

See [yt-dlp](https://github.com/yt-dlp/yt-dlp) for downloader licensing. This GUI is provided as-is.

---

**Website:** https://isnick.net
