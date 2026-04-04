"""Desktop control panel for CCFII Display Share."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover - depends on local Python build
    tk = None
    messagebox = None
    ttk = None

from .capture import CaptureTarget, build_capture_targets, list_monitors, list_windows
from .config import APP_COLORS, APP_NAME
from .manager import BroadcastManager

if TYPE_CHECKING:
    import tkinter as _tk


def format_target_option(target: CaptureTarget) -> str:
    if target.kind == "desktop":
        return f"{target.label}"
    return f"{target.label} (Window)"


def parse_int_setting(raw_value: str, default: int,
                      minimum: int, maximum: int) -> int:
    value = raw_value.strip()
    if not value:
        return default
    parsed = int(value)
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"Value must be between {minimum} and {maximum}.")
    return parsed


def build_status_text(status: dict[str, object]) -> str:
    if not status.get("is_running"):
        return "Ready to broadcast. Select a source and start sharing to the local network."

    viewer_count = int(status.get("viewer_count", 0))
    viewer_noun = "device" if viewer_count == 1 else "devices"
    target_label = str(status.get("target_label") or "Selected source")
    viewer_url = str(status.get("viewer_url") or "")
    return (
        f"Broadcasting live from {target_label}.\n"
        f"{viewer_count} {viewer_noun} connected.\n"
        f"Receivers can connect at {viewer_url}."
    )


class DisplayShareDesktopApp:
    """Tkinter-based operator console for display sharing."""

    def __init__(self, root: "_tk.Tk"):
        if tk is None or ttk is None or messagebox is None:
            raise RuntimeError("Tkinter is not available in this Python environment.")
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1180x760")
        self.root.minsize(1040, 680)
        self.root.configure(bg=APP_COLORS["background"])
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.targets: list[CaptureTarget] = []
        self.target_lookup: dict[str, CaptureTarget] = {}
        self.manager: BroadcastManager | None = None
        self.advanced_visible = False
        self.logo_image: tk.PhotoImage | None = None

        self.selected_target = tk.StringVar()
        self.status_badge = tk.StringVar(value="Ready")
        self.status_title = tk.StringVar(value="Ready for service")
        self.status_text = tk.StringVar(
            value="Select the display or window you want to send across the local network."
        )
        self.viewer_url = tk.StringVar(value="Not live yet")
        self.viewer_count = tk.StringVar(value="0")
        self.fps_value = tk.StringVar(value="30")
        self.quality_value = tk.StringVar(value="5")
        self.port_value = tk.StringVar(value="8080")

        self._configure_styles()
        self._build_ui()
        self.refresh_targets(initial=True)
        self._schedule_status_poll()

    def _configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "CCFII.TCombobox",
            fieldbackground=APP_COLORS["surface_alt"],
            background=APP_COLORS["surface_alt"],
            foreground=APP_COLORS["foreground"],
            bordercolor=APP_COLORS["border"],
            arrowcolor=APP_COLORS["accent"],
            lightcolor=APP_COLORS["surface_alt"],
            darkcolor=APP_COLORS["surface_alt"],
        )

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=APP_COLORS["background"], padx=24, pady=24)
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg=APP_COLORS["surface"], bd=1,
                          highlightbackground=APP_COLORS["border"],
                          highlightthickness=1)
        header.pack(fill="x", pady=(0, 18))

        self._build_header(header)

        body = tk.Frame(outer, bg=APP_COLORS["background"])
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=APP_COLORS["background"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))

        right = tk.Frame(body, bg=APP_COLORS["background"], width=340)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        self._build_primary_panel(left)
        self._build_status_panels(right)

    def _build_header(self, parent: tk.Frame):
        left = tk.Frame(parent, bg=APP_COLORS["surface"], padx=20, pady=18)
        left.pack(side="left", fill="x", expand=True)

        logo_path = Path(__file__).resolve().parents[1] / "assets" / "ccfii-logo.png"
        if logo_path.exists():
            try:
                self.logo_image = tk.PhotoImage(file=str(logo_path))
                logo_label = tk.Label(left, image=self.logo_image, bg=APP_COLORS["surface"])
                logo_label.pack(side="left", padx=(0, 18))
            except tk.TclError:
                self.logo_image = None

        text_wrap = tk.Frame(left, bg=APP_COLORS["surface"])
        text_wrap.pack(side="left", fill="x", expand=True)

        tk.Label(
            text_wrap,
            text="Christ Charismatic Fellowship Int'l, Inc.",
            bg=APP_COLORS["surface"],
            fg=APP_COLORS["accent"],
            font=("Palatino Linotype", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            text_wrap,
            text=APP_NAME,
            bg=APP_COLORS["surface"],
            fg=APP_COLORS["foreground"],
            font=("Palatino Linotype", 28, "bold"),
        ).pack(anchor="w", pady=(6, 0))
        tk.Label(
            text_wrap,
            text="Local network display broadcast for sanctuary and event operations",
            bg=APP_COLORS["surface"],
            fg=APP_COLORS["muted"],
            font=("Cambria", 12),
        ).pack(anchor="w", pady=(4, 0))

        tk.Label(
            parent,
            textvariable=self.status_badge,
            bg=APP_COLORS["primary"],
            fg=APP_COLORS["foreground"],
            font=("Cambria", 12, "bold"),
            padx=18,
            pady=10,
        ).pack(side="right", padx=20, pady=20)

    def _build_primary_panel(self, parent: tk.Frame):
        panel = self._card(parent)
        panel.pack(fill="both", expand=True)

        tk.Label(panel, text="Broadcast Control", bg=APP_COLORS["surface"],
                 fg=APP_COLORS["foreground"], font=("Palatino Linotype", 24, "bold")).pack(anchor="w")
        tk.Label(panel, text="Choose what to share, then start the local broadcast.",
                 bg=APP_COLORS["surface"], fg=APP_COLORS["muted"],
                 font=("Cambria", 12)).pack(anchor="w", pady=(6, 22))
        tk.Label(panel, text="Source", bg=APP_COLORS["surface"],
                 fg=APP_COLORS["accent"], font=("Cambria", 12, "bold")).pack(anchor="w")

        source_row = tk.Frame(panel, bg=APP_COLORS["surface"])
        source_row.pack(fill="x", pady=(8, 18))

        self.source_combo = ttk.Combobox(
            source_row,
            textvariable=self.selected_target,
            state="readonly",
            style="CCFII.TCombobox",
            font=("Cambria", 12),
        )
        self.source_combo.pack(side="left", fill="x", expand=True, ipady=8)

        self._button(
            source_row,
            text="Refresh Sources",
            command=self.refresh_targets,
            bg=APP_COLORS["surface_alt"],
            fg=APP_COLORS["foreground"],
            active_bg=APP_COLORS["primary_hover"],
        ).pack(side="left", padx=(12, 0))

        self.primary_button = self._button(
            panel,
            text="Start Broadcast",
            command=self.toggle_broadcast,
            bg=APP_COLORS["primary"],
            fg=APP_COLORS["foreground"],
            active_bg=APP_COLORS["primary_hover"],
            font=("Palatino Linotype", 18, "bold"),
            padx=20,
            pady=18,
        )
        self.primary_button.pack(fill="x")

        self.url_card = self._sub_card(panel)
        self.url_card.pack(fill="x", pady=(22, 18))
        tk.Label(self.url_card, text="Receiver Link", bg=APP_COLORS["surface_alt"],
                 fg=APP_COLORS["accent"], font=("Cambria", 12, "bold")).pack(anchor="w")

        link_row = tk.Frame(self.url_card, bg=APP_COLORS["surface_alt"])
        link_row.pack(fill="x", pady=(10, 0))

        self.link_entry = tk.Entry(
            link_row,
            textvariable=self.viewer_url,
            state="readonly",
            relief="flat",
            readonlybackground=APP_COLORS["background"],
            fg=APP_COLORS["foreground"],
            disabledforeground=APP_COLORS["foreground"],
            font=("Cambria", 12),
            bd=0,
        )
        self.link_entry.pack(side="left", fill="x", expand=True, ipady=10)

        self._button(
            link_row,
            text="Copy Link",
            command=self.copy_viewer_link,
            bg=APP_COLORS["accent"],
            fg="#2d1408",
            active_bg="#f0b85d",
        ).pack(side="left", padx=(12, 0))

        self._button(
            panel,
            text="AV Controls",
            command=self.toggle_advanced,
            bg=APP_COLORS["surface_alt"],
            fg=APP_COLORS["foreground"],
            active_bg=APP_COLORS["primary_hover"],
        ).pack(anchor="w")

        self.advanced_panel = self._sub_card(panel)
        self._build_advanced_panel(self.advanced_panel)

    def _build_advanced_panel(self, parent: tk.Frame):
        settings = [
            ("Port", self.port_value, "HTTP port used by the receivers."),
            ("Frames Per Second", self.fps_value, "Higher is smoother, but uses more bandwidth."),
            ("JPEG Quality", self.quality_value, "Lower number means better image quality."),
        ]
        for label, variable, description in settings:
            tk.Label(parent, text=label, bg=APP_COLORS["surface_alt"],
                     fg=APP_COLORS["foreground"], font=("Cambria", 12, "bold")).pack(anchor="w", pady=(0, 4))
            tk.Entry(
                parent,
                textvariable=variable,
                relief="flat",
                bg=APP_COLORS["background"],
                fg=APP_COLORS["foreground"],
                insertbackground=APP_COLORS["foreground"],
                font=("Cambria", 12),
            ).pack(fill="x", ipady=8)
            tk.Label(parent, text=description, bg=APP_COLORS["surface_alt"],
                     fg=APP_COLORS["muted"], font=("Cambria", 10)).pack(anchor="w", pady=(6, 16))

    def _build_status_panels(self, parent: tk.Frame):
        self.status_card = self._card(parent)
        self.status_card.pack(fill="x", pady=(0, 14))
        tk.Label(self.status_card, textvariable=self.status_title, bg=APP_COLORS["surface"],
                 fg=APP_COLORS["foreground"], font=("Palatino Linotype", 20, "bold"),
                 wraplength=280, justify="left").pack(anchor="w")
        tk.Label(self.status_card, textvariable=self.status_text, bg=APP_COLORS["surface"],
                 fg=APP_COLORS["muted"], font=("Cambria", 12), wraplength=280,
                 justify="left").pack(anchor="w", pady=(10, 0))

        details = self._card(parent)
        details.pack(fill="x", pady=(0, 14))
        self._metric(details, "Connected Devices", self.viewer_count)
        self._metric(details, "Current Link", self.viewer_url)

        help_card = self._card(parent)
        help_card.pack(fill="both", expand=True)
        tk.Label(help_card, text="Operator Notes", bg=APP_COLORS["surface"],
                 fg=APP_COLORS["accent"], font=("Cambria", 12, "bold")).pack(anchor="w")
        tips = (
            "Receivers must be on the same local network.\n\n"
            "Use the receiver link in any browser-capable device, then send that device to the monitor by HDMI or wireless display.\n\n"
            "If a device loses the feed, keep the app running. The stream will recycle idle connections so receivers can reconnect."
        )
        tk.Label(help_card, text=tips, bg=APP_COLORS["surface"], fg=APP_COLORS["muted"],
                 font=("Cambria", 11), wraplength=280, justify="left").pack(anchor="w", pady=(10, 0))

    def _metric(self, parent: tk.Frame, label: str, variable: tk.StringVar):
        tk.Label(parent, text=label, bg=APP_COLORS["surface"],
                 fg=APP_COLORS["accent"], font=("Cambria", 11, "bold")).pack(anchor="w", pady=(0, 6))
        tk.Label(parent, textvariable=variable, bg=APP_COLORS["surface"],
                 fg=APP_COLORS["foreground"], font=("Cambria", 13), wraplength=280,
                 justify="left").pack(anchor="w", pady=(0, 14))

    def _card(self, parent):
        return tk.Frame(parent, bg=APP_COLORS["surface"], padx=20, pady=20,
                        highlightbackground=APP_COLORS["border"], highlightthickness=1)

    def _sub_card(self, parent):
        return tk.Frame(parent, bg=APP_COLORS["surface_alt"], padx=16, pady=16,
                        highlightbackground=APP_COLORS["border"], highlightthickness=1)

    def _button(self, parent, text: str, command,
                bg: str, fg: str, active_bg: str,
                font=("Cambria", 11, "bold"), padx=16, pady=12):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=font,
            padx=padx,
            pady=pady,
        )

    def refresh_targets(self, initial: bool = False):
        try:
            monitors = list_monitors()
            windows = list_windows()
        except Exception as exc:
            if not initial:
                messagebox.showerror(APP_NAME, f"Unable to refresh sources.\n\n{exc}")
            return

        self.targets = build_capture_targets(monitors, windows)
        labels = [format_target_option(target) for target in self.targets]
        self.target_lookup = dict(zip(labels, self.targets))
        self.source_combo["values"] = labels
        if labels and (initial or self.selected_target.get() not in self.target_lookup):
            self.selected_target.set(labels[0])

    def toggle_broadcast(self):
        if self.manager and self.manager.get_status()["is_running"]:
            self.stop_broadcast()
        else:
            self.start_broadcast()

    def start_broadcast(self):
        target = self.target_lookup.get(self.selected_target.get())
        if target is None:
            messagebox.showwarning(APP_NAME, "Choose a display or window before starting the broadcast.")
            return
        try:
            port = parse_int_setting(self.port_value.get(), 8080, 1024, 65535)
            fps = parse_int_setting(self.fps_value.get(), 30, 1, 60)
            quality = parse_int_setting(self.quality_value.get(), 5, 1, 31)
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        try:
            self.manager = BroadcastManager(
                targets=self.targets,
                port=port,
                fps=fps,
                quality=quality,
            )
            self.manager.start(target)
        except Exception as exc:
            self.manager = None
            messagebox.showerror(APP_NAME, f"Unable to start the broadcast.\n\n{exc}")
            return

        self.primary_button.configure(text="Stop Broadcast", bg=APP_COLORS["accent"], fg="#2d1408")
        self.status_badge.set("Broadcasting")
        self.status_title.set("Broadcast live on local network")
        self._refresh_status_ui()

    def stop_broadcast(self):
        if self.manager is None:
            return
        self.manager.stop()
        self.manager = None
        self.primary_button.configure(text="Start Broadcast",
                                      bg=APP_COLORS["primary"],
                                      fg=APP_COLORS["foreground"])
        self.status_badge.set("Ready")
        self.status_title.set("Ready for service")
        self.status_text.set(build_status_text({"is_running": False}))
        self.viewer_url.set("Not live yet")
        self.viewer_count.set("0")

    def toggle_advanced(self):
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_panel.pack(fill="x", pady=(14, 0))
        else:
            self.advanced_panel.pack_forget()

    def copy_viewer_link(self):
        value = self.viewer_url.get()
        if not value.startswith("http"):
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.status_badge.set("Link Copied")
        self.root.after(1800, self._refresh_status_ui)

    def _schedule_status_poll(self):
        self._refresh_status_ui()
        self.root.after(1500, self._schedule_status_poll)

    def _refresh_status_ui(self):
        if self.manager is None:
            self.status_text.set(build_status_text({"is_running": False}))
            return

        status = self.manager.get_status()
        if status["is_running"]:
            self.status_badge.set("Broadcasting")
            self.status_title.set("Broadcast live on local network")
        else:
            self.status_badge.set("Ready")
            self.status_title.set("Ready for service")
        self.status_text.set(build_status_text(status))
        self.viewer_url.set(str(status["viewer_url"]))
        self.viewer_count.set(str(status["viewer_count"]))

    def on_close(self):
        if self.manager is not None:
            self.manager.stop()
        self.root.destroy()


def launch_app():
    if tk is None:
        raise RuntimeError("Tkinter is not available in this Python environment.")
    root = tk.Tk()
    DisplayShareDesktopApp(root)
    root.mainloop()
