import sys
import os
import json
import re
import stat

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLineEdit,
    QLabel, QFileDialog, QProgressBar, QMessageBox, QHBoxLayout,
    QMenuBar, QAction
)
from PyQt5.QtCore import QProcess

CONFIG_FILE = "config.json"
LOG_FILE = "is.log"

# Only allow http/https URLs
URL_REGEX = re.compile(r"^https?://[^\s]+$")

# Strip ANSI escape codes (for log hygiene)
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# Allowed sites and their URL regex patterns
ALLOWED_SITES = {
    "Bluesky":   [re.compile(r"https?://(?:www\.)?bsky\.app/.*")],
    "Facebook":  [re.compile(r"https?://(?:www\.)?facebook\.com/.*")],
    "Instagram": [re.compile(r"https?://(?:www\.)?instagram\.com/.*")],
    "TikTok":    [re.compile(r"https?://(?:www\.)?tiktok\.com/.*")],
    "YouTube": [
        re.compile(r"https?://(?:www\.)?youtube\.com/.*"),
        re.compile(r"https?://youtu\.be/.*"),
        re.compile(r"https?://(?:www\.)?music\.youtube\.com/.*")
    ]
}


class YTDLP_GUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("iSnick Downloader")
        self.resize(560, 340)

        # Main layout
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Menu bar
        self.menu_bar = QMenuBar(self)
        self.layout.setMenuBar(self.menu_bar)

        # File menu
        file_menu = self.menu_bar.addMenu("File")
        reset_action = QAction("Reset", self)
        reset_action.triggered.connect(self.reset_ui)
        file_menu.addAction(reset_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Help menu
        help_menu = self.menu_bar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_action = QAction("Help", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(about_action)
        help_menu.addAction(help_action)

        # Site menu
        self.selected_site = "YouTube"  # default
        self.site_menu = self.menu_bar.addMenu("Site")
        for site in sorted(ALLOWED_SITES.keys()):
            act = QAction(site, self, checkable=True)
            if site == self.selected_site:
                act.setChecked(True)
            act.triggered.connect(lambda checked, s=site: self.set_site(s))
            self.site_menu.addAction(act)
        self.allow_unlisted_action = QAction("Allow Unlisted", self, checkable=True)
        self.allow_unlisted_action.triggered.connect(self.toggle_unlisted)
        self.site_menu.addAction(self.allow_unlisted_action)

        # Binary selector
        self.binary_label = QLabel("yt-dlp binary path:")
        self.binary_input = QLineEdit()
        self.binary_button = QPushButton("Browse…")
        self.binary_button.clicked.connect(self.choose_binary)

        self.layout.addWidget(self.binary_label)
        self.layout.addWidget(self.binary_input)
        self.layout.addWidget(self.binary_button)

        # URL input
        self.url_label = QLabel("Video URL:")
        self.layout.addWidget(self.url_label)
        self.url_input = QLineEdit()
        self.layout.addWidget(self.url_input)

        # Sandbox info
        self.sandbox_info = QLabel("Download location: (sandboxed)")
        self.layout.addWidget(self.sandbox_info)

        # Status + speed
        self.status_label = QLabel("Status: Idle")
        self.layout.addWidget(self.status_label)
        self.speed_label = QLabel("Speed: -")
        self.layout.addWidget(self.speed_label)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.layout.addWidget(self.progress)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Download")
        self.start_button.clicked.connect(self.start_download)
        button_layout.addWidget(self.start_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_download)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.cancel_button)

        self.layout.addLayout(button_layout)

        # Process
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_output)
        self.process.readyReadStandardError.connect(self.handle_output)
        self.process.finished.connect(self.download_finished)

        # Config
        self.binary_from_config = None
        self.sandbox_dir = None
        self.config = {}
        self.load_config()
        self.init_sandbox_dir()
        self.apply_site_config()

        # Hide binary picker if set in config
        if self.binary_from_config:
            self.binary_label.hide()
            self.binary_input.hide()
            self.binary_button.hide()

    # ---------------- Security Helpers ----------------
    def validate_binary(self, path: str) -> bool:
        if not os.path.isfile(path):
            return False
        st = os.stat(path)
        if not (st.st_mode & stat.S_IXUSR):
            return False
        base = os.path.basename(path)
        return base.startswith("yt-dlp")

    def real(self, p: str) -> str:
        return os.path.realpath(os.path.expanduser(p))

    def ensure_inside_sandbox(self, target_path: str) -> bool:
        sandbox = self.real(self.sandbox_dir)
        target = self.real(target_path)
        return os.path.commonpath([sandbox, target]) == sandbox

    def init_sandbox_dir(self):
        if not self.sandbox_dir:
            self.sandbox_dir = os.path.join(os.path.expanduser("~"), "Videos", "yt-dlp-gui")
        sb_real = self.real(self.sandbox_dir)
        if os.path.islink(self.sandbox_dir):
            QMessageBox.critical(self, "Sandbox Error", "Sandbox directory cannot be a symlink.")
            sys.exit(1)
        try:
            os.makedirs(sb_real, mode=0o700, exist_ok=True)
            os.chmod(sb_real, 0o700)
        except Exception as e:
            QMessageBox.critical(self, "Sandbox Error", f"Cannot create sandbox: {e}")
            sys.exit(1)
        if not os.access(sb_real, os.W_OK):
            QMessageBox.critical(self, "Sandbox Error", "Sandbox directory is not writable.")
            sys.exit(1)
        self.sandbox_dir = sb_real
        self.sandbox_info.setText(f"Download location: {self.sandbox_dir}")

    # ---------------- Site Menu ----------------
    def set_site(self, site):
        self.selected_site = site
        for act in self.site_menu.actions():
            if act.text() in ALLOWED_SITES:
                act.setChecked(act.text() == site)
        self.allow_unlisted_action.setChecked(False)
        self.log(f"Site set to: {site}")
        self.save_config()

    def toggle_unlisted(self, checked):
        if checked:
            self.selected_site = "Allow Unlisted"
            for act in self.site_menu.actions():
                if act.text() in ALLOWED_SITES:
                    act.setChecked(False)
            self.log("Allowing unlisted sites")
        else:
            self.set_site("YouTube")

    def apply_site_config(self):
        saved = self.config.get("selected_site")
        if saved == "Allow Unlisted":
            self.allow_unlisted_action.setChecked(True)
            self.selected_site = "Allow Unlisted"
        elif saved in ALLOWED_SITES:
            self.set_site(saved)

    # ---------------- UI Actions ----------------
    def choose_binary(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select yt-dlp binary")
        if file and self.validate_binary(file):
            self.binary_input.setText(file)
            self.save_config()
        elif file:
            QMessageBox.critical(self, "Error", "Invalid yt-dlp binary.")

    def start_download(self):
        binary = self.binary_from_config or self.binary_input.text().strip()
        url = self.url_input.text().strip()
        if not self.validate_binary(binary):
            QMessageBox.critical(self, "Error", "Invalid yt-dlp binary path.")
            return
        if self.selected_site == "Allow Unlisted":
            if not URL_REGEX.match(url):
                QMessageBox.critical(self, "Error", "Invalid or missing video URL.")
                return
        else:
            valid_patterns = ALLOWED_SITES.get(self.selected_site, [])
            if not any(re.match(p, url) for p in valid_patterns):
                QMessageBox.critical(self, "Error", f"URL does not match selected site ({self.selected_site}).")
                return
        if self.process.state() != QProcess.NotRunning:
            QMessageBox.warning(self, "Warning", "Another download is in progress.")
            return

        self.progress.setValue(0)
        self.status_label.setText("Status: Retrieving video information…")
        self.speed_label.setText("Speed: -")
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

        self.save_config()

        safe_template = "%(title).200B.%(ext)s"
        args = ["--restrict-filenames", "-o", safe_template, "-P", self.sandbox_dir, url]
        if not self.ensure_inside_sandbox(self.sandbox_dir):
            QMessageBox.critical(self, "Sandbox Error", "Resolved path escapes sandbox.")
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            return

        self.process.start(binary, args)
        self.log(f"Started download: {url} → {self.sandbox_dir}")

    def handle_output(self):
        output = str(self.process.readAllStandardOutput(), "utf-8", errors="ignore")
        error = str(self.process.readAllStandardError(), "utf-8", errors="ignore")
        text = ANSI_ESCAPE.sub("", output + error)
        if text.strip():
            self.log(text)
        for line in text.splitlines():
            if "[download]" in line:
                if "Destination" in line:
                    self.status_label.setText("Status: Beginning download…")
                elif "%" in line:
                    self.status_label.setText("Status: In progress…")
                    try:
                        percent = float(line.split("%")[0].split()[-1])
                        self.progress.setValue(int(percent))
                    except ValueError:
                        pass
                    if "at" in line:
                        sp = line.split("at", 1)[1].strip().split()
                        if sp:
                            self.speed_label.setText(f"Speed: {sp[0]}")
            elif "has already been downloaded" in line:
                self.progress.setValue(100)
                self.status_label.setText("Status: Complete (already downloaded)")
                self.speed_label.setText("Speed: -")

    def download_finished(self):
        self.progress.setValue(100)
        self.status_label.setText("Status: Complete")
        self.speed_label.setText("Speed: -")
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        QMessageBox.information(self, "Done", "Download completed.")
        self.log("Download finished.")

    def cancel_download(self):
        if self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.status_label.setText("Status: Cancelled")
            self.speed_label.setText("Speed: -")
            self.progress.setValue(0)
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.log("Download cancelled by user.")

    def reset_ui(self):
        self.url_input.clear()
        if not self.binary_from_config:
            self.binary_input.clear()
        self.progress.setValue(0)
        self.status_label.setText("Status: Idle")
        self.speed_label.setText("Speed: -")
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def show_about(self):
        QMessageBox.information(
            self,
            "About",
            "iSnick Downloader v0.0.1\n\n"
            "A program to download media for offline use.\n\n"
            "https://isnick.net\n\n"
        )

    def show_help(self):
        QMessageBox.information(
            self,
            "Help",
            "1) Paste a media URL (http/https).\n"
            "2) Select from menu (currently YouTube, TikTok, Facebook, Instagram, or Allow Unlisted).\n"
            "3) Download goes to sandbox directory.\n"
            "4) Click Download. Use Cancel to stop.\n\n"
            "Menu:\n- File → Reset: Clear inputs.\n- File → Exit: Quit.\n- Help → About / Help."

        )

    # ---------------- Config & Logging ----------------
    def log(self, text):
        clean = ANSI_ESCAPE.sub("", text)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(clean + "\n")

    def save_config(self):
        cfg = {}
        if self.binary_from_config or self.binary_input.text().strip():
            cfg["binary"] = self.binary_from_config or self.binary_input.text().strip()
        cfg["sandbox_dir"] = self.sandbox_dir
        cfg["selected_site"] = self.selected_site
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            self.log(f"Failed to save config: {e}")

    def load_config(self):
        self.binary_from_config = None
        self.sandbox_dir = None
        self.selected_site = "YouTube"
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.config = cfg
                self.binary_from_config = cfg.get("binary") or None
                self.sandbox_dir = cfg.get("sandbox_dir") or None
                self.selected_site = cfg.get("selected_site") or "YouTube"
            except Exception as e:
                self.log(f"Failed to load config: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YTDLP_GUI()
    window.show()
    sys.exit(app.exec_())
