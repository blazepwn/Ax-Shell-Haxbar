import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image as FabricImage
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.stack import Stack
from fabric.widgets.window import Window
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image

from .data import (
    APP_NAME,
    APP_NAME_CAP,
)
from .settings_utils import (
    backup_and_replace,
    bind_vars,
    get_bind_var,
    get_default,
    start_config,
)


class HyprConfGUI(Window):
    def __init__(self, show_lock_checkbox: bool, show_idle_checkbox: bool, **kwargs):
        super().__init__(
            title="Ax-Shell Settings",
            name="axshell-settings-window",
            size=(900, 700),
            type_hint=Gdk.WindowTypeHint.DIALOG,
            **kwargs,
        )

        self.set_resizable(False)

        # Load CSS
        # Load CSS with manual variable replacement
        css_provider = Gtk.CssProvider()
        base_path = os.path.dirname(__file__)
        css_path = os.path.join(base_path, "../styles/settings.css")
        colors_path = os.path.join(base_path, "../styles/colors.css")
        
        try:
            css_content = ""
            # Parse colors
            colors = {}
            if os.path.exists(colors_path):
                with open(colors_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        # Handle @define-color syntax
                        if line.startswith("@define-color"):
                            parts = line.split()
                            if len(parts) >= 3:
                                key = parts[1]
                                val = parts[2].rstrip(";")
                                colors[f"var(--{key})"] = val
                        # Handle legacy syntax (just in case)
                        elif line.startswith("--") and ":" in line:
                            key, val = line.split(":", 1)
                            key = key.strip()
                            val = val.strip().rstrip(";")
                            colors[f"var({key})"] = val
            
            # Read settings CSS and replace vars
            if os.path.exists(css_path):
                with open(css_path, "r") as f:
                    css_content = f.read()
                
                # Use regex or simple replace for substituting vars
                for var, color in colors.items():
                    css_content = css_content.replace(var, color)
                
                # Remove the @import line if present to avoid errors
                css_content = css_content.replace('@import "colors.css";', '')

                css_provider.load_from_data(css_content.encode("utf-8"))
                Gtk.StyleContext.add_provider_for_screen(
                    Gdk.Screen.get_default(),
                    css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                )
        except Exception as e:
            print(f"Error loading CSS: {e}")
            # Fallback to direct load if possible (though likely to fail loop)
            if os.path.exists(css_path):
                try:
                    css_provider.load_from_path(css_path)
                    Gtk.StyleContext.add_provider_for_screen(
                        Gdk.Screen.get_default(),
                        css_provider,
                        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                    )
                except:
                    pass

        self.get_style_context().add_class("settings-window")

        self.selected_face_icon = None
        self.show_lock_checkbox = show_lock_checkbox
        self.show_idle_checkbox = show_idle_checkbox

        # Main horizontal container (Split view)
        main_hbox = Box(orientation="h", spacing=0)
        self.add(main_hbox)

        # --- Sidebar (Left) ---
        sidebar_box = Box(
            orientation="v", 
            spacing=10, 
            style_classes=["sidebar"],
            size=(200, -1) # Fixed width for sidebar
        )
        main_hbox.add(sidebar_box)

        # Sidebar Title/Header
        sidebar_header = Label(
            label="Settings", 
            style="font-weight: bold; font-size: 18px; padding: 20px;"
        )
        sidebar_box.add(sidebar_header)

        self.tab_stack = Stack(
            transition_type="slide-up-down",
            transition_duration=250,
            v_expand=True,
            h_expand=True,
        )

        self.key_bindings_tab_content = self.create_key_bindings_tab()
        self.appearance_tab_content = self.create_appearance_tab()
        self.system_tab_content = self.create_system_tab()
        self.about_tab_content = self.create_about_tab()

        self.tab_stack.add_titled(
            self.appearance_tab_content, "appearance", "Appearance"
        )
        self.tab_stack.add_titled(self.system_tab_content, "system", "System")
        self.tab_stack.add_titled(
            self.key_bindings_tab_content, "key_bindings", "Key Bindings"
        )
        self.tab_stack.add_titled(self.about_tab_content, "about", "About")

        # Sidebar Navigation (StackSwitcher)
        tab_switcher = Gtk.StackSwitcher()
        tab_switcher.set_stack(self.tab_stack)
        tab_switcher.set_orientation(Gtk.Orientation.VERTICAL)
        tab_switcher.set_halign(Gtk.Align.FILL)
        sidebar_box.add(tab_switcher)

        # Spacer to push buttons to bottom
        sidebar_box.add(Box(v_expand=True))

        # Action Buttons in Sidebar
        button_box = Box(orientation="v", spacing=10, style="padding: 15px;")
        reset_btn = Button(label="Reset Defaults", on_clicked=self.on_reset)
        close_btn = Button(label="Close", on_clicked=self.on_close)
        accept_btn = Button(label="Apply & Reload", on_clicked=self.on_accept)
        # Apply special styles to primary button
        accept_btn.get_style_context().add_class("suggested-action")
        
        button_box.add(accept_btn)
        button_box.add(reset_btn)
        button_box.add(close_btn)
        sidebar_box.add(button_box)

        # --- Content Area (Right) ---
        content_box = Box(
            orientation="v", 
            spacing=0, 
            h_expand=True, 
            v_expand=True,
            style_classes=["content-area"]
        )
        main_hbox.add(content_box)
        content_box.add(self.tab_stack)

    def create_card(self, title, widget_box):
        """Helper to create a styled card container"""
        card = Box(orientation="v", spacing=10, style_classes=["card"])
        
        if title:
            title_label = Label(
                label=title, 
                h_align="start", 
                style_classes=["card-title"]
            )
            card.add(title_label)
            
        card.add(widget_box)
        return card

    def create_key_bindings_tab(self):
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False,
        )

        main_vbox = Box(orientation="v", spacing=10, style="margin: 15px;")
        scrolled_window.add(main_vbox)

        keybind_grid = Gtk.Grid()
        keybind_grid.set_column_spacing(10)
        keybind_grid.set_row_spacing(8)
        keybind_grid.set_margin_start(5)
        keybind_grid.set_margin_end(5)
        keybind_grid.set_margin_top(5)
        keybind_grid.set_margin_bottom(5)

        action_label = Label(
            markup="<b>Action</b>", h_align="start", style="margin-bottom: 5px;"
        )
        modifier_label = Label(
            markup="<b>Modifier</b>", h_align="start", style="margin-bottom: 5px;"
        )
        separator_label = Label(
            label="+", h_align="center", style="margin-bottom: 5px;"
        )
        key_label = Label(
            markup="<b>Key</b>", h_align="start", style="margin-bottom: 5px;"
        )

        keybind_grid.attach(action_label, 0, 0, 1, 1)
        keybind_grid.attach(modifier_label, 1, 0, 1, 1)
        keybind_grid.attach(separator_label, 2, 0, 1, 1)
        keybind_grid.attach(key_label, 3, 0, 1, 1)

        self.entries = []
        bindings = [
            (f"Reload {APP_NAME_CAP}", "prefix_restart", "suffix_restart"),
            ("Message", "prefix_axmsg", "suffix_axmsg"),
            ("Dashboard", "prefix_dash", "suffix_dash"),
            ("Bluetooth", "prefix_bluetooth", "suffix_bluetooth"),
            ("Pins", "prefix_pins", "suffix_pins"),
            ("Kanban", "prefix_kanban", "suffix_kanban"),
            ("App Launcher", "prefix_launcher", "suffix_launcher"),
            ("Tmux", "prefix_tmux", "suffix_tmux"),
            ("Clipboard History", "prefix_cliphist", "suffix_cliphist"),
            ("Toolbox", "prefix_toolbox", "suffix_toolbox"),
            ("Overview", "prefix_overview", "suffix_overview"),
            ("Wallpapers", "prefix_wallpapers", "suffix_wallpapers"),
            ("Random Wallpaper", "prefix_randwall", "suffix_randwall"),
            ("Audio Mixer", "prefix_mixer", "suffix_mixer"),
            ("Emoji Picker", "prefix_emoji", "suffix_emoji"),
            ("Power Menu", "prefix_power", "suffix_power"),
            ("Toggle Caffeine", "prefix_caffeine", "suffix_caffeine"),
            ("Toggle Bar", "prefix_toggle", "suffix_toggle"),
            ("Reload CSS", "prefix_css", "suffix_css"),
            (
                "Restart with inspector",
                "prefix_restart_inspector",
                "suffix_restart_inspector",
            ),
        ]

        for i, (label_text, prefix_key, suffix_key) in enumerate(bindings):
            row = i + 1
            binding_label = Label(label=label_text, h_align="start")
            keybind_grid.attach(binding_label, 0, row, 1, 1)
            prefix_entry = Entry(text=get_bind_var(prefix_key))
            keybind_grid.attach(prefix_entry, 1, row, 1, 1)
            plus_label = Label(label="+", h_align="center")
            keybind_grid.attach(plus_label, 2, row, 1, 1)
            suffix_entry = Entry(text=get_bind_var(suffix_key))
            keybind_grid.attach(suffix_entry, 3, row, 1, 1)
            self.entries.append((prefix_key, suffix_key, prefix_entry, suffix_entry))

        main_vbox.add(keybind_grid)
        return scrolled_window

    def create_appearance_tab(self):
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False,
        )

        vbox = Box(orientation="v", spacing=20, style="margin: 20px; padding-bottom: 50px;")
        scrolled_window.add(vbox)

        # --- Wallpapers Card ---
        wall_box = Box(orientation="v", spacing=10)
        
        wall_row = Box(orientation="h", spacing=10)
        wall_label = Label(label="Directory", h_align="start", v_align="center", style_classes=["subtitle"])
        wall_row.add(wall_label)
        
        chooser_btn = Gtk.FileChooserButton(
            title="Select a folder", action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        chooser_btn.set_filename(get_bind_var("wallpapers_dir"))
        chooser_btn.set_hexpand(True)
        self.wall_dir_chooser = chooser_btn
        wall_row.add(chooser_btn)
        
        wall_box.add(wall_row)
        vbox.add(self.create_card("Wallpapers", wall_box))

        # --- Profile & Icon Card ---
        profile_box = Box(orientation="v", spacing=15)
        
        # Profile Icon Row
        face_row = Box(orientation="h", spacing=10)
        face_label = Label(label="Profile Image", h_align="start", v_align="center", style_classes=["subtitle"])
        face_row.add(face_label)
        face_row.add(Box(h_expand=True)) # Spacer

        self.face_image = FabricImage(size=48)
        current_face = os.path.expanduser("~/.face.icon")
        try:
            if os.path.exists(current_face):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(current_face, 48, 48)
                self.face_image.set_from_pixbuf(pixbuf)
            else:
                self.face_image.set_from_icon_name("user-info", Gtk.IconSize.DIALOG)
        except Exception:
            self.face_image.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
            
        face_frame = Box(style_classes=["image-frame"])
        face_frame.add(self.face_image)
        face_row.add(face_frame)
        
        face_btn = Button(label="Change", on_clicked=self.on_select_face_icon)
        face_row.add(face_btn)
        self.face_status_label = Label(label="") # Hidden status
        profile_box.add(face_row)
        
        profile_box.add(Box(style="min-height: 1px; background-color: alpha(currentColor, 0.1);"))

        # Launcher Icon Row
        launcher_row = Box(orientation="h", spacing=10)
        launcher_label = Label(label="Launcher Icon", h_align="start", v_align="center", style_classes=["subtitle"])
        launcher_row.add(launcher_label)
        launcher_row.add(Box(h_expand=True))

        self.launcher_image = FabricImage(size=32)
        current_launcher_icon = get_bind_var("launcher_icon_path")
        try:
            if current_launcher_icon and os.path.exists(current_launcher_icon):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(current_launcher_icon, 32, 32)
                self.launcher_image.set_from_pixbuf(pixbuf)
            else:
                self.launcher_image.set_from_icon_name("view-app-grid-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        except Exception:
            self.launcher_image.set_from_icon_name("image-missing", Gtk.IconSize.LARGE_TOOLBAR)
            
        launcher_container = Box(style_classes=["image-frame"])
        launcher_container.add(self.launcher_image)
        launcher_row.add(launcher_container)
        
        launcher_btn = Button(label="Change", on_clicked=self.on_select_launcher_icon)
        launcher_row.add(launcher_btn)
        launcher_reset = Button(label="Reset", on_clicked=self.on_reset_launcher_icon)
        launcher_row.add(launcher_reset)
        
        profile_box.add(launcher_row)
        vbox.add(self.create_card("Personalization", profile_box))

        # --- Layout Options Card ---
        layout_box = Box(orientation="v", spacing=12)
        
        def add_setting_row(label_text, widget):
            row = Box(orientation="h", spacing=10)
            lbl = Label(label=label_text, h_align="start", style_classes=["subtitle"])
            row.add(lbl)
            row.add(Box(h_expand=True))
            row.add(widget)
            layout_box.add(row)
            return row

        # Bar Position
        self.position_combo = Gtk.ComboBoxText()
        for pos in ["Top", "Bottom", "Left", "Right"]: self.position_combo.append_text(pos)
        try: self.position_combo.set_active(["Top", "Bottom", "Left", "Right"].index(get_bind_var("bar_position")))
        except: self.position_combo.set_active(0)
        self.position_combo.connect("changed", self.on_position_changed)
        add_setting_row("Bar Position", self.position_combo)
        
        # Centered Bar
        self.centered_switch = Gtk.Switch(active=get_bind_var("centered_bar"), sensitive=get_bind_var("bar_position") in ["Left", "Right"])
        add_setting_row("Centered Bar (Vertical)", self.centered_switch)
        
        # Bar Theme
        self.bar_theme_combo = Gtk.ComboBoxText()
        for theme in ["Pills", "Dense", "Edge"]: self.bar_theme_combo.append_text(theme)
        try: self.bar_theme_combo.set_active(["Pills", "Dense", "Edge"].index(get_bind_var("bar_theme")))
        except: self.bar_theme_combo.set_active(0)
        add_setting_row("Bar Theme", self.bar_theme_combo)

        layout_box.add(Box(style="min-height: 10px;")) # Spacer

        # Dock Settings
        self.dock_switch = Gtk.Switch(active=get_bind_var("dock_enabled"))
        self.dock_switch.connect("notify::active", self.on_dock_enabled_changed)
        add_setting_row("Enable Dock", self.dock_switch)
        
        self.dock_hover_switch = Gtk.Switch(active=get_bind_var("dock_always_show"), sensitive=self.dock_switch.get_active())
        add_setting_row("Always Show Dock", self.dock_hover_switch)
        
        self.dock_theme_combo = Gtk.ComboBoxText()
        for theme in ["Pills", "Dense", "Edge"]: self.dock_theme_combo.append_text(theme)
        try: self.dock_theme_combo.set_active(["Pills", "Dense", "Edge"].index(get_bind_var("dock_theme")))
        except: self.dock_theme_combo.set_active(0)
        add_setting_row("Dock Theme", self.dock_theme_combo)

        # Dock Size Scale
        dock_size_row = Box(orientation="v", spacing=5)
        dock_size_lbl = Label(label="Dock Icon Size", h_align="start", style_classes=["subtitle"])
        dock_size_row.add(dock_size_lbl)
        self.dock_size_scale = Scale(
            min_value=16, max_value=48, value=get_bind_var("dock_icon_size"),
            increments=(2, 4), draw_value=True, digits=0, h_expand=True
        )
        dock_size_row.add(self.dock_size_scale)
        layout_box.add(dock_size_row)
        
        vbox.add(self.create_card("Layout & Dock", layout_box))

        # --- Panel & Notifications Card ---
        panel_box = Box(orientation="v", spacing=12)
        
        def add_panel_row(label_text, widget):
            row = Box(orientation="h", spacing=10)
            lbl = Label(label=label_text, h_align="start", style_classes=["subtitle"])
            row.add(lbl)
            row.add(Box(h_expand=True))
            row.add(widget)
            panel_box.add(row)

        self.panel_theme_combo = Gtk.ComboBoxText()
        for theme in ["Notch", "Panel"]: self.panel_theme_combo.append_text(theme)
        try: self.panel_theme_combo.set_active(["Notch", "Panel"].index(get_bind_var("panel_theme")))
        except: self.panel_theme_combo.set_active(0)
        self.panel_theme_combo.connect("changed", self._on_panel_theme_changed_for_position_sensitivity)
        add_panel_row("Panel Style", self.panel_theme_combo)
        
        self.panel_position_combo = Gtk.ComboBoxText()
        for option in ["Start", "Center", "End"]: self.panel_position_combo.append_text(option)
        try: self.panel_position_combo.set_active(["Start", "Center", "End"].index(get_bind_var("panel_position")))
        except: self.panel_position_combo.set_active(0)
        self.panel_position_combo.set_sensitive(get_bind_var("panel_theme") == "Panel")
        add_panel_row("Panel Position", self.panel_position_combo)
        
        self.notification_pos_combo = Gtk.ComboBoxText()
        for pos in ["Top", "Bottom"]: self.notification_pos_combo.append_text(pos)
        try: self.notification_pos_combo.set_active(["Top", "Bottom"].index(get_bind_var("notif_pos")))
        except: self.notification_pos_combo.set_active(0)
        self.notification_pos_combo.connect("changed", self.on_notification_position_changed)
        add_panel_row("Notification Position", self.notification_pos_combo)

        vbox.add(self.create_card("Panels & Popups", panel_box))
        
        # --- Modules Grid Card ---
        modules_box = Box(orientation="v", spacing=10)
        
        # Grid for toggles
        mod_grid = Gtk.Grid()
        mod_grid.set_column_spacing(20)
        mod_grid.set_row_spacing(10)
        
        self.component_switches = {}
        component_display_names = {
            "button_apps": "App Launcher", "systray": "System Tray", "control": "Control Panel",
            "network": "Network", "local_ip": "Local IP", "htb_ip": "HTB VPN",
            "button_tools": "Toolbox", "button_overview": "Overview", "ws_container": "Workspaces",
            "weather": "Weather", "battery": "Battery", "metrics": "Metrics", "target": "Target",
            "language": "Language", "date_time": "Date & Time", "button_power": "Power",
            "sysprofiles": "Profiles"
        }
        
        # Add corners switch first
        corners_label = Label(label="Rounded Corners", h_align="start", style_classes=["subtitle"])
        mod_grid.attach(corners_label, 0, 0, 1, 1)
        self.corners_switch = Gtk.Switch(active=get_bind_var("corners_visible"))
        mod_grid.attach(self.corners_switch, 1, 0, 1, 1)
        
        row, col = 1, 0
        for name, display in component_display_names.items():
            if col > 2: # Max 2 columns (0,1 and 2,3)
                col = 0
                row += 1
            
            lbl = Label(label=display, h_align="start", style_classes=["subtitle"])
            mod_grid.attach(lbl, col, row, 1, 1)
            
            sw = Gtk.Switch(active=get_bind_var(f"bar_{name}_visible"))
            mod_grid.attach(sw, col+1, row, 1, 1)
            self.component_switches[name] = sw
            
            col += 2
            
        modules_box.add(mod_grid)
        vbox.add(self.create_card("Active Modules", modules_box))
        
        # --- Date & Time Format ---
        dt_box = Box(orientation="h", spacing=10)
        dt_label = Label(label="12-Hour Clock Format", h_align="start", style_classes=["subtitle"])
        dt_box.add(dt_label)
        dt_box.add(Box(h_expand=True))
        self.datetime_12h_switch = Gtk.Switch(active=get_bind_var("datetime_12h_format"))
        dt_box.add(self.datetime_12h_switch)
        vbox.add(self.create_card("Date & Time", dt_box))

        return scrolled_window

    def _on_panel_theme_changed_for_position_sensitivity(self, combo):
        self._update_panel_position_sensitivity()

    def _update_panel_position_sensitivity(self):
        if hasattr(self, "panel_theme_combo") and hasattr(self, "panel_position_combo"):
            selected_theme = self.panel_theme_combo.get_active_text()
            is_panel_theme_selected = selected_theme == "Panel"
            self.panel_position_combo.set_sensitive(is_panel_theme_selected)

    def on_notification_position_changed(self, combo: Gtk.ComboBoxText):
        selected_text = combo.get_active_text()
        if selected_text:
            bind_vars["notif_pos"] = selected_text
            print(
                f"Notification position updated in bind_vars: {bind_vars["notif_pos"]}"
            )

    def create_system_tab(self):
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False,
        )

        vbox = Box(orientation="v", spacing=15, style="margin: 15px;")
        scrolled_window.add(vbox)

        system_grid = Gtk.Grid()
        system_grid.set_column_spacing(20)
        system_grid.set_row_spacing(10)
        system_grid.set_margin_bottom(15)
        vbox.add(system_grid)

        # Auto-append checkbox - first option
        auto_append_label = Label(
            label="Auto-append to hyprland.conf", h_align="start", v_align="center"
        )
        system_grid.attach(auto_append_label, 0, 0, 1, 1)
        auto_append_switch_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        self.auto_append_switch = Gtk.Switch(
            active=get_bind_var("auto_append_hyprland"),
            tooltip_text="Automatically append Ax-Shell source string to hyprland.conf",
        )
        auto_append_switch_container.add(self.auto_append_switch)
        system_grid.attach(auto_append_switch_container, 1, 0, 1, 1)

        # OVPN Path - New Option
        ovpn_header = Label(markup="<b>VPN Configuration</b>", h_align="start")
        system_grid.attach(ovpn_header, 2, 0, 2, 1) # Right column

        ovpn_label = Label(
            label="OVPN Directory:", h_align="start", v_align="center"
        )
        system_grid.attach(ovpn_label, 2, 1, 1, 1)

        ovpn_chooser_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        ovpn_chooser_container.set_halign(Gtk.Align.START)
        ovpn_chooser_container.set_valign(Gtk.Align.CENTER)
        self.ovpn_dir_chooser = Gtk.FileChooserButton(
            title="Select VPN Config Folder", action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        self.ovpn_dir_chooser.set_tooltip_text(
            "Select the directory containing your .ovpn files"
        )
        self.ovpn_dir_chooser.set_filename(get_bind_var("ovpn_path"))
        self.ovpn_dir_chooser.set_size_request(180, -1)
        # Connect signal to update bind_var immediately or on apply
        self.ovpn_dir_chooser.connect("file-set", self.on_ovpn_dir_set)
        
        ovpn_chooser_container.add(self.ovpn_dir_chooser)
        system_grid.attach(ovpn_chooser_container, 3, 1, 1, 1)

        # Monitor Selection - second option
        monitor_header = Label(markup="<b>Monitor Selection</b>", h_align="start")
        system_grid.attach(monitor_header, 0, 1, 2, 1)

        monitor_label = Label(
            label="Show Ax-Shell on monitors:", h_align="start", v_align="center"
        )
        system_grid.attach(monitor_label, 0, 2, 1, 1)

        # Create monitor selection container
        self.monitor_selection_container = Box(
            orientation="v", spacing=5, h_align="start"
        )
        self.monitor_checkboxes = {}

        # Get available monitors
        try:
            from utils.monitor_manager import get_monitor_manager

            monitor_manager = get_monitor_manager()
            available_monitors = monitor_manager.get_monitors()
        except (ImportError, Exception) as e:
            print(f"Could not get monitor info for settings: {e}")
            available_monitors = [{"id": 0, "name": "default"}]

        # Get current selection from config
        current_selection = get_bind_var("selected_monitors")

        # Create checkboxes for each monitor
        for monitor in available_monitors:
            monitor_name = monitor.get("name", f'monitor-{monitor.get("id", 0)}')

            checkbox_container = Box(orientation="h", spacing=5, h_align="start")
            checkbox = Gtk.CheckButton(label=monitor_name)

            # Check if this monitor is selected (empty selection means all selected)
            is_selected = (
                len(current_selection) == 0 or monitor_name in current_selection
            )
            checkbox.set_active(is_selected)

            checkbox_container.add(checkbox)
            self.monitor_selection_container.add(checkbox_container)
            self.monitor_checkboxes[monitor_name] = checkbox

        # Add hint label
        hint_label = Label(
            markup="<small>Leave all unchecked to show on all monitors</small>",
            h_align="start",
        )
        self.monitor_selection_container.add(hint_label)

        system_grid.attach(self.monitor_selection_container, 1, 2, 1, 1)

        terminal_header = Label(markup="<b>Terminal Settings</b>", h_align="start")
        system_grid.attach(terminal_header, 0, 3, 2, 1)
        terminal_label = Label(label="Command:", h_align="start", v_align="center")
        system_grid.attach(terminal_label, 0, 4, 1, 1)
        self.terminal_entry = Entry(
            text=get_bind_var("terminal_command"),
            tooltip_text="Command used to launch terminal apps (e.g., 'kitty -e')",
            h_expand=True,
        )
        system_grid.attach(self.terminal_entry, 1, 4, 1, 1)
        hint_label = Label(
            markup="<small>Examples: 'kitty -e', 'alacritty -e', 'foot -e'</small>",
            h_align="start",
        )
        system_grid.attach(hint_label, 0, 5, 2, 1)

        hypr_header = Label(markup="<b>Hyprland Integration</b>", h_align="start")
        system_grid.attach(hypr_header, 2, 3, 2, 1)
        row = 4
        self.lock_switch = None
        if self.show_lock_checkbox:
            lock_label = Label(
                label="Replace Hyprlock config", h_align="start", v_align="center"
            )
            system_grid.attach(lock_label, 2, row, 1, 1)
            lock_switch_container = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
            )
            self.lock_switch = Gtk.Switch(
                tooltip_text="Replace Hyprlock configuration with Ax-Shell's custom config"
            )
            lock_switch_container.add(self.lock_switch)
            system_grid.attach(lock_switch_container, 3, row, 1, 1)
            row += 1
        self.idle_switch = None
        if self.show_idle_checkbox:
            idle_label = Label(
                label="Replace Hypridle config", h_align="start", v_align="center"
            )
            system_grid.attach(idle_label, 2, row, 1, 1)
            idle_switch_container = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
            )
            self.idle_switch = Gtk.Switch(
                tooltip_text="Replace Hypridle configuration with Ax-Shell's custom config"
            )
            idle_switch_container.add(self.idle_switch)
            system_grid.attach(idle_switch_container, 3, row, 1, 1)
            row += 1
        if self.show_lock_checkbox or self.show_idle_checkbox:
            note_label = Label(
                markup="<small>Existing configs will be backed up</small>",
                h_align="start",
            )
            system_grid.attach(note_label, 2, row, 2, 1)

        # Notifications app lists section
        notifications_header = Label(
            markup="<b>Notification Settings</b>", h_align="start"
        )
        vbox.add(notifications_header)

        notif_grid = Gtk.Grid()
        notif_grid.set_column_spacing(20)
        notif_grid.set_row_spacing(10)
        notif_grid.set_margin_start(10)
        notif_grid.set_margin_top(5)
        notif_grid.set_margin_bottom(15)
        vbox.add(notif_grid)

        # Limited Apps History
        limited_apps_label = Label(
            label="Limited Apps History:", h_align="start", v_align="center"
        )
        notif_grid.attach(limited_apps_label, 0, 0, 1, 1)

        limited_apps_list = get_bind_var("limited_apps_history")
        limited_apps_text = ", ".join(f'"{app}"' for app in limited_apps_list)
        self.limited_apps_entry = Entry(
            text=limited_apps_text,
            tooltip_text='Enter app names separated by commas, e.g: "Spotify", "Discord"',
            h_expand=True,
        )
        notif_grid.attach(self.limited_apps_entry, 1, 0, 1, 1)

        limited_apps_hint = Label(
            markup='<small>Apps with limited notification history (format: "App1", "App2")</small>',
            h_align="start",
        )
        notif_grid.attach(limited_apps_hint, 0, 1, 2, 1)

        # History Ignored Apps
        ignored_apps_label = Label(
            label="History Ignored Apps:", h_align="start", v_align="center"
        )
        notif_grid.attach(ignored_apps_label, 0, 2, 1, 1)

        ignored_apps_list = get_bind_var("history_ignored_apps")
        ignored_apps_text = ", ".join(f'"{app}"' for app in ignored_apps_list)
        self.ignored_apps_entry = Entry(
            text=ignored_apps_text,
            tooltip_text='Enter app names separated by commas, e.g: "Hyprshot", "Screenshot"',
            h_expand=True,
        )
        notif_grid.attach(self.ignored_apps_entry, 1, 2, 1, 1)

        ignored_apps_hint = Label(
            markup='<small>Apps whose notifications are ignored in history (format: "App1", "App2")</small>',
            h_align="start",
        )
        notif_grid.attach(ignored_apps_hint, 0, 3, 2, 1)

        metrics_header = Label(markup="<b>System Metrics Options</b>", h_align="start")
        vbox.add(metrics_header)
        metrics_grid = Gtk.Grid(
            column_spacing=15, row_spacing=8, margin_start=10, margin_top=5
        )
        vbox.add(metrics_grid)

        self.metrics_switches = {}
        self.metrics_small_switches = {}
        metric_names = {"cpu": "CPU", "ram": "RAM", "disk": "Disk", "gpu": "GPU"}

        metrics_grid.attach(Label(label="Show in Metrics", h_align="start"), 0, 0, 1, 1)
        for i, (key, label_text) in enumerate(metric_names.items()):
            switch = Gtk.Switch(active=get_bind_var("metrics_visible").get(key, True))
            self.metrics_switches[key] = switch
            metrics_grid.attach(
                Label(label=label_text, h_align="start"), 0, i + 1, 1, 1
            )
            metrics_grid.attach(switch, 1, i + 1, 1, 1)

        metrics_grid.attach(
            Label(label="Show in Small Metrics", h_align="start"), 2, 0, 1, 1
        )
        for i, (key, label_text) in enumerate(metric_names.items()):
            switch = Gtk.Switch(
                active=get_bind_var("metrics_small_visible").get(key, True)
            )
            self.metrics_small_switches[key] = switch
            metrics_grid.attach(
                Label(label=label_text, h_align="start"), 2, i + 1, 1, 1
            )
            metrics_grid.attach(switch, 3, i + 1, 1, 1)

        def enforce_minimum_metrics(switch_dict):
            enabled_switches = [s for s in switch_dict.values() if s.get_active()]
            can_disable = len(enabled_switches) > 3
            for s in switch_dict.values():
                s.set_sensitive(True if can_disable or not s.get_active() else False)

        def on_metric_toggle(switch, gparam, switch_dict):
            enforce_minimum_metrics(switch_dict)

        for k_s, s_s in self.metrics_switches.items():
            s_s.connect("notify::active", on_metric_toggle, self.metrics_switches)
        for k_s, s_s in self.metrics_small_switches.items():
            s_s.connect("notify::active", on_metric_toggle, self.metrics_small_switches)
        enforce_minimum_metrics(self.metrics_switches)
        enforce_minimum_metrics(self.metrics_small_switches)

        disks_label = Label(
            label="Disk directories for Metrics", h_align="start", v_align="center"
        )
        vbox.add(disks_label)
        self.disk_entries = Box(orientation="v", spacing=8, h_align="start")

        self._create_disk_edit_entry_func = lambda path: self._add_disk_entry_widget(
            path
        )

        for p in get_bind_var("bar_metrics_disks"):
            self._create_disk_edit_entry_func(p)
        vbox.add(self.disk_entries)

        add_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        add_btn = Button(
            label="Add new disk",
            on_clicked=lambda _: self._create_disk_edit_entry_func("/"),
        )
        add_container.add(add_btn)
        vbox.add(add_container)

        return scrolled_window

    def _add_disk_entry_widget(self, path):
        """Helper para añadir una fila de entrada de disco al Box disk_entries."""
        bar = Box(orientation="h", spacing=10, h_align="start")
        entry = Entry(text=path, h_expand=True)
        bar.add(entry)
        x_btn = Button(label="X")
        x_btn.connect(
            "clicked",
            lambda _, current_bar_to_remove=bar: self.disk_entries.remove(
                current_bar_to_remove
            ),
        )
        bar.add(x_btn)
        self.disk_entries.add(bar)
        self.disk_entries.show_all()

    def create_about_tab(self):
        vbox = Box(orientation="v", spacing=18, style="margin: 30px;")
        vbox.add(
            Label(
                markup=f"<b>{APP_NAME_CAP}</b>",
                h_align="start",
                style="font-size: 1.5em; margin-bottom: 8px;",
            )
        )
        vbox.add(
            Label(
                label="A hackable shell for Hyprland, powered by Fabric.",
                h_align="start",
                style="margin-bottom: 12px;",
            )
        )
        repo_box = Box(orientation="h", spacing=6, h_align="start")
        repo_label = Label(label="GitHub:", h_align="start")
        repo_link = Label(
            markup='<a href="https://github.com/Axenide/Ax-Shell">https://github.com/Axenide/Ax-Shell</a>'
        )
        repo_box.add(repo_label)
        repo_box.add(repo_link)
        vbox.add(repo_box)

        def on_kofi_clicked(_):
            import webbrowser

            webbrowser.open("https://ko-fi.com/Axenide")

        kofi_btn = Button(
            label="Support on Ko-Fi ❤️",
            on_clicked=on_kofi_clicked,
            tooltip_text="Support Axenide on Ko-Fi",
            style="margin-top: 18px; min-width: 160px;",
        )
        vbox.add(kofi_btn)
        vbox.add(Box(v_expand=True))
        return vbox

    def on_ws_num_changed(self, switch, gparam):
        is_active = switch.get_active()
        self.ws_chinese_switch.set_sensitive(is_active)
        if not is_active:
            self.ws_chinese_switch.set_active(False)

    def on_position_changed(self, combo):
        position = combo.get_active_text()
        is_vertical = position in ["Left", "Right"]
        self.centered_switch.set_sensitive(is_vertical)
        if not is_vertical:
            self.centered_switch.set_active(False)

    def on_dock_enabled_changed(self, switch, gparam):
        is_active = switch.get_active()
        self.dock_hover_switch.set_sensitive(is_active)
        if not is_active:
            self.dock_hover_switch.set_active(False)

    def on_select_launcher_icon(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Launcher Icon",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )

        filter_image = Gtk.FileFilter()
        filter_image.set_name("Images")
        filter_image.add_mime_type("image/png")
        filter_image.add_mime_type("image/jpeg")
        filter_image.add_mime_type("image/svg+xml")
        dialog.add_filter(filter_image)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            bind_vars["launcher_icon_path"] = filename
            
            # Update preview
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename, 32, 32)
                self.launcher_image.set_from_pixbuf(pixbuf)
                print(f"Selected launcher icon: {filename}")
            except Exception as e:
                print(f"Error loading preview: {e}")
                
        dialog.destroy()

    def on_reset_launcher_icon(self, button):
        bind_vars["launcher_icon_path"] = None
        self.launcher_image.set_from_icon_name("view-app-grid-symbolic", Gtk.IconSize.LARGE_TOOLBAR)

    def on_select_face_icon(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Select Face Icon",
            transient_for=self.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Image files")
        for mime in ["image/png", "image/jpeg"]:
            image_filter.add_mime_type(mime)
        for pattern in ["*.png", "*.jpg", "*.jpeg"]:
            image_filter.add_pattern(pattern)
        dialog.add_filter(image_filter)
        if dialog.run() == Gtk.ResponseType.OK:
            self.selected_face_icon = dialog.get_filename()
            self.face_status_label.label = (
                f"Selected: {os.path.basename(self.selected_face_icon)}"
            )
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    self.selected_face_icon, 64, 64
                )
                self.face_image.set_from_pixbuf(pixbuf)
            except Exception as e:
                print(f"Error loading selected face icon preview: {e}")
                self.face_image.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
        dialog.destroy()


    def on_accept(self, widget):
        print(f"{time.time():.4f}: DEBUG: on_accept called")
        try:
            current_bind_vars_snapshot = {}

            # Save key bindings
            for prefix_key, suffix_key, prefix_entry, suffix_entry in self.entries:
                current_bind_vars_snapshot[prefix_key] = prefix_entry.get_text()
                current_bind_vars_snapshot[suffix_key] = suffix_entry.get_text()

            # Save appearance settings
            current_bind_vars_snapshot["wallpapers_dir"] = (
                self.wall_dir_chooser.get_filename()
            )
            current_bind_vars_snapshot["launcher_icon_path"] = bind_vars.get("launcher_icon_path")

            current_bind_vars_snapshot["bar_position"] = self.position_combo.get_active_text()
            current_bind_vars_snapshot["centered_bar"] = self.centered_switch.get_active()
            current_bind_vars_snapshot["dock_enabled"] = self.dock_switch.get_active()
            current_bind_vars_snapshot["dock_always_show"] = (
                self.dock_hover_switch.get_active()
            )
            current_bind_vars_snapshot["dock_icon_size"] = int(
                self.dock_size_scale.get_value()
            )
            current_bind_vars_snapshot["terminal_command"] = (
                self.terminal_entry.get_text()
            ) if hasattr(self, "terminal_entry") else bind_vars.get("terminal_command", "kitty")

            current_bind_vars_snapshot["auto_append_hyprland"] = (
                self.auto_append_switch.get_active()
            )
            current_bind_vars_snapshot["bar_workspace_show_number"] = (
                self.ws_num_switch.get_active()
            ) if hasattr(self, "ws_num_switch") else bind_vars.get("bar_workspace_show_number", True)
            
            current_bind_vars_snapshot["bar_workspace_use_chinese_numerals"] = (
                self.ws_chinese_switch.get_active()
            ) if hasattr(self, "ws_chinese_switch") else bind_vars.get("bar_workspace_use_chinese_numerals", False)
            
            current_bind_vars_snapshot["bar_hide_special_workspace"] = (
                self.special_ws_switch.get_active()
            ) if hasattr(self, "special_ws_switch") else bind_vars.get("bar_hide_special_workspace", False)
            
            current_bind_vars_snapshot["ovpn_path"] = self.ovpn_dir_chooser.get_filename()

            current_bind_vars_snapshot["bar_theme"] = self.bar_theme_combo.get_active_text()
            current_bind_vars_snapshot["dock_theme"] = self.dock_theme_combo.get_active_text()
            current_bind_vars_snapshot["panel_theme"] = (
                self.panel_theme_combo.get_active_text()
            )
            current_bind_vars_snapshot["panel_position"] = (
                self.panel_position_combo.get_active_text()
            )
            current_bind_vars_snapshot["datetime_12h_format"] = (
                self.datetime_12h_switch.get_active()
            )

            selected_notif_pos_text = self.notification_pos_combo.get_active_text()
            if selected_notif_pos_text:
                current_bind_vars_snapshot["notif_pos"] = selected_notif_pos_text
            else:
                current_bind_vars_snapshot["notif_pos"] = "Top"

            for component_name, switch in self.component_switches.items():
                current_bind_vars_snapshot[f"bar_{component_name}_visible"] = (
                    switch.get_active()
                )

            if hasattr(self, "metrics_switches"):
                current_bind_vars_snapshot["metrics_visible"] = {
                    k: s.get_active() for k, s in self.metrics_switches.items()
                }
            else:
                current_bind_vars_snapshot["metrics_visible"] = bind_vars.get("metrics_visible", {})

            if hasattr(self, "metrics_small_switches"):
                current_bind_vars_snapshot["metrics_small_visible"] = {
                    k: s.get_active() for k, s in self.metrics_small_switches.items()
                }
            else:
                current_bind_vars_snapshot["metrics_small_visible"] = bind_vars.get("metrics_small_visible", {})

            if hasattr(self, "disk_entries"):
                current_bind_vars_snapshot["bar_metrics_disks"] = [
                    child.get_children()[0].get_text()
                    for child in self.disk_entries.get_children()
                    if isinstance(child, Gtk.Box)
                    and child.get_children()
                    and isinstance(child.get_children()[0], Entry)
                ]
            else:
                current_bind_vars_snapshot["bar_metrics_disks"] = bind_vars.get("bar_metrics_disks", [])

            current_bind_vars_snapshot["corners_visible"] = self.corners_switch.get_active()

            # Parse notification app lists
            def parse_app_list(text):
                """Parse comma-separated app names with quotes"""
                if not text.strip():
                    return []
                apps = []
                for app in text.split(","):
                    app = app.strip()
                    if app.startswith('"') and app.endswith('"'):
                        app = app[1:-1]
                    elif app.startswith("'") and app.endswith("'"):
                        app = app[1:-1]
                    if app:
                        apps.append(app)
                return apps

            current_bind_vars_snapshot["limited_apps_history"] = parse_app_list(
                self.limited_apps_entry.get_text()
            )
            current_bind_vars_snapshot["history_ignored_apps"] = parse_app_list(
                self.ignored_apps_entry.get_text()
            )

            # Save monitor selection
            selected_monitors = []
            any_checked = False
            for monitor_name, checkbox in self.monitor_checkboxes.items():
                if checkbox.get_active():
                    selected_monitors.append(monitor_name)
                    any_checked = True

            current_bind_vars_snapshot["selected_monitors"] = (
                selected_monitors if any_checked else []
            )

            selected_icon_path = self.selected_face_icon
            replace_lock = self.lock_switch and self.lock_switch.get_active() if hasattr(self, "lock_switch") else False
            replace_idle = self.idle_switch and self.idle_switch.get_active() if hasattr(self, "idle_switch") else False

            if self.selected_face_icon:
                self.selected_face_icon = None
                self.face_status_label.label = ""

            def _apply_and_reload_task_thread(user_data):
                nonlocal current_bind_vars_snapshot

                from . import settings_utils

                settings_utils.bind_vars.clear()
                settings_utils.bind_vars.update(current_bind_vars_snapshot)

                start_time = time.time()
                print(f"{start_time:.4f}: Background task started.")

                config_json = os.path.expanduser(
                    f"~/.config/{APP_NAME_CAP}/config/config.json"
                )
                os.makedirs(os.path.dirname(config_json), exist_ok=True)
                try:
                    with open(config_json, "w") as f:
                        json.dump(settings_utils.bind_vars, f, indent=4)
                    print(f"{time.time():.4f}: Saved config.json.")
                except Exception as e:
                    print(f"Error saving config.json: {e}")

                if selected_icon_path:
                    print(f"{time.time():.4f}: Processing face icon...")
                    try:
                        img = Image.open(selected_icon_path)
                        side = min(img.size)
                        left = (img.width - side) // 2
                        top = (img.height - side) // 2
                        cropped_img = img.crop((left, top, left + side, top + side))
                        face_icon_dest = os.path.expanduser("~/.face.icon")
                        cropped_img.save(face_icon_dest, format="PNG")
                        print(f"{time.time():.4f}: Face icon saved to {face_icon_dest}")
                        GLib.idle_add(self._update_face_image_widget, face_icon_dest)
                    except Exception as e:
                        print(f"Error processing face icon: {e}")

                if replace_lock:
                    print(f"{time.time():.4f}: Replacing hyprlock config...")
                    src = os.path.expanduser(
                        f"~/.config/{APP_NAME_CAP}/config/hypr/hyprlock.conf"
                    )
                    dest = os.path.expanduser("~/.config/hypr/hyprlock.conf")
                    if os.path.exists(src):
                        backup_and_replace(src, dest, "Hyprlock")
                    else:
                        print(f"Warning: Source hyprlock config not found at {src}")
                    print(f"{time.time():.4f}: Finished replacing hyprlock config.")

                if replace_idle:
                    print(f"{time.time():.4f}: Replacing hypridle config...")
                    src = os.path.expanduser(
                        f"~/.config/{APP_NAME_CAP}/config/hypr/hypridle.conf"
                    )
                    dest = os.path.expanduser("~/.config/hypr/hypridle.conf")
                    if os.path.exists(src):
                        backup_and_replace(src, dest, "Hypridle")
                    else:
                        print(f"Warning: Source hypridle config not found at {src}")
                    print(f"{time.time():.4f}: Finished replacing hypridle config.")

                print(
                    f"{time.time():.4f}: Checking/Appending hyprland.conf source string..."
                )
                hypr_path = os.path.expanduser("~/.config/hypr/hyprland.conf")
                try:
                    from .settings_constants import SOURCE_STRING

                    # Check if auto-append is enabled
                    auto_append_enabled = current_bind_vars_snapshot.get(
                        "auto_append_hyprland", True
                    )
                    if auto_append_enabled:
                        needs_append = True
                        if os.path.exists(hypr_path):
                            with open(hypr_path, "r") as f:
                                if SOURCE_STRING.strip() in f.read():
                                    needs_append = False
                        else:
                            os.makedirs(os.path.dirname(hypr_path), exist_ok=True)

                        if needs_append:
                            with open(hypr_path, "a") as f:
                                f.write("\n" + SOURCE_STRING)
                            print(f"Appended source string to {hypr_path}")
                        else:
                            print("Source string already present in hyprland.conf")
                    else:
                        print("Auto-append to hyprland.conf is disabled")
                except Exception as e:
                    print(f"Error updating {hypr_path}: {e}")
                print(
                    f"{time.time():.4f}: Finished checking/appending hyprland.conf source string."
                )

                print(f"{time.time():.4f}: Running start_config()...")
                start_config()
                print(f"{time.time():.4f}: Finished start_config().")

                print(f"{time.time():.4f}: Initiating Ax-Shell restart using Popen...")
                main_py = os.path.expanduser(f"~/.config/{APP_NAME_CAP}/main.py")
                kill_cmd = f"killall {APP_NAME}"
                start_cmd = ["uwsm", "app", "--", "python", main_py]
                try:
                    kill_proc = subprocess.Popen(
                        kill_cmd,
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    kill_proc.wait(timeout=2)
                    print(f"{time.time():.4f}: killall process finished (o timed out).")
                except subprocess.TimeoutExpired:
                    print("Warning: killall command timed out.")
                except Exception as e:
                    print(f"Error running killall: {e}")

                try:
                    subprocess.Popen(
                        start_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    print(f"{APP_NAME_CAP} restart initiated via Popen.")
                except FileNotFoundError as e:
                    print(f"Error restarting {APP_NAME_CAP}: Command not found ({e})")
                except Exception as e:
                    print(f"Error restarting {APP_NAME_CAP} via Popen: {e}")

                print(f"{time.time():.4f}: Ax-Shell restart commands issued via Popen.")
                end_time = time.time()
                print(
                    f"{end_time:.4f}: Background task finished (Total: {end_time - start_time:.4f}s)."
                )

            GLib.Thread.new("apply-reload-task", _apply_and_reload_task_thread, None)
            print("Configuration apply/reload task started in background.")

        except Exception as e:
            print(f"ERROR in on_accept: {e}")
            import traceback
            traceback.print_exc()
    def on_ovpn_dir_set(self, widget):
        folder = widget.get_filename()
        if folder:
            bind_vars["ovpn_path"] = folder
            print(f"OVPN path updated: {folder}")

    def on_reset(self, widget):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Reset all settings to defaults?",
        )
        dialog.format_secondary_text(
            "This will reset all keybindings and appearance settings to their default values."
        )
        if dialog.run() == Gtk.ResponseType.YES:
            from . import settings_utils
            from .settings_constants import DEFAULTS

            settings_utils.bind_vars.clear()
            settings_utils.bind_vars.update(DEFAULTS.copy())

            for prefix_key, suffix_key, prefix_entry, suffix_entry in self.entries:
                prefix_entry.set_text(settings_utils.bind_vars[prefix_key])
                suffix_entry.set_text(settings_utils.bind_vars[suffix_key])

            self.wall_dir_chooser.set_filename(
                settings_utils.bind_vars["wallpapers_dir"]
            )

            positions = ["Top", "Bottom", "Left", "Right"]
            default_position = get_default("bar_position")
            try:
                self.position_combo.set_active(positions.index(default_position))
            except ValueError:
                self.position_combo.set_active(0)

            self.centered_switch.set_active(get_bind_var("centered_bar"))
            self.centered_switch.set_sensitive(default_position in ["Left", "Right"])

            self.datetime_12h_switch.set_active(get_bind_var("datetime_12h_format"))

            self.dock_switch.set_active(get_bind_var("dock_enabled"))
            self.dock_hover_switch.set_active(get_bind_var("dock_always_show"))
            self.dock_hover_switch.set_sensitive(self.dock_switch.get_active())
            self.dock_size_scale.set_value(get_bind_var("dock_icon_size"))
            self.terminal_entry.set_text(settings_utils.bind_vars["terminal_command"])
            self.auto_append_switch.set_active(get_bind_var("auto_append_hyprland"))
            self.ws_num_switch.set_active(get_bind_var("bar_workspace_show_number"))
            self.ws_chinese_switch.set_active(
                get_bind_var("bar_workspace_use_chinese_numerals")
            )
            self.ws_chinese_switch.set_sensitive(self.ws_num_switch.get_active())
            self.special_ws_switch.set_active(
                get_bind_var("bar_hide_special_workspace")
            )

            default_theme_val = get_default("bar_theme")
            themes = ["Pills", "Dense", "Edge"]
            try:
                self.bar_theme_combo.set_active(themes.index(default_theme_val))
            except ValueError:
                self.bar_theme_combo.set_active(0)

            default_dock_theme_val = get_default("dock_theme")
            try:
                self.dock_theme_combo.set_active(themes.index(default_dock_theme_val))
            except ValueError:
                self.dock_theme_combo.set_active(0)

            default_panel_theme_val = get_default("panel_theme")
            panel_themes_options = ["Notch", "Panel"]
            try:
                self.panel_theme_combo.set_active(
                    panel_themes_options.index(default_panel_theme_val)
                )
            except ValueError:
                self.panel_theme_combo.set_active(0)

            default_panel_position_val = get_default("panel_position")
            try:
                self.panel_position_combo.set_active(
                    self.panel_position_options.index(default_panel_position_val)
                )
            except ValueError:
                try:
                    self.panel_position_combo.set_active(
                        self.panel_position_options.index("Center")
                    )
                except ValueError:
                    self.panel_position_combo.set_active(0)

            default_notif_pos_val = get_default("notif_pos")
            notification_positions_list = ["Top", "Bottom"]
            try:
                self.notification_pos_combo.set_active(
                    notification_positions_list.index(default_notif_pos_val)
                )
            except ValueError:
                self.notification_pos_combo.set_active(0)

            for name, switch in self.component_switches.items():
                switch.set_active(get_bind_var(f"bar_{name}_visible"))
            self.corners_switch.set_active(get_bind_var("corners_visible"))

            metrics_vis_defaults = get_default("metrics_visible")
            for k, s_widget in self.metrics_switches.items():
                s_widget.set_active(metrics_vis_defaults.get(k, True))

            metrics_small_vis_defaults = get_default("metrics_small_visible")
            for k, s_widget in self.metrics_small_switches.items():
                s_widget.set_active(metrics_small_vis_defaults.get(k, True))

            def enforce_minimum_metrics(switch_dict):
                enabled_switches = [
                    s_widget
                    for s_widget in switch_dict.values()
                    if s_widget.get_active()
                ]
                can_disable = len(enabled_switches) > 3
                for s_widget in switch_dict.values():
                    s_widget.set_sensitive(
                        True if can_disable or not s_widget.get_active() else False
                    )

            enforce_minimum_metrics(self.metrics_switches)
            enforce_minimum_metrics(self.metrics_small_switches)

            for child in list(self.disk_entries.get_children()):
                self.disk_entries.remove(child)

            for p in get_default("bar_metrics_disks"):
                self._add_disk_edit_entry_func(p)

            # Reset notification app lists
            limited_apps_list = get_default("limited_apps_history")
            limited_apps_text = ", ".join(f'"{app}"' for app in limited_apps_list)
            self.limited_apps_entry.set_text(limited_apps_text)

            ignored_apps_list = get_default("history_ignored_apps")
            ignored_apps_text = ", ".join(f'"{app}"' for app in ignored_apps_list)
            self.ignored_apps_entry.set_text(ignored_apps_text)

            # Reset monitor selection
            default_monitors = get_default("selected_monitors")
            for monitor_name, checkbox in self.monitor_checkboxes.items():
                # If defaults is empty, check all monitors (show on all)
                is_selected = (
                    len(default_monitors) == 0 or monitor_name in default_monitors
                )
                checkbox.set_active(is_selected)

            self._update_panel_position_sensitivity()

            self.selected_face_icon = None
            self.face_status_label.label = ""
            current_face = os.path.expanduser("~/.face.icon")
            try:
                pixbuf = (
                    GdkPixbuf.Pixbuf.new_from_file_at_size(current_face, 64, 64)
                    if os.path.exists(current_face)
                    else None
                )
                if pixbuf:
                    self.face_image.set_from_pixbuf(pixbuf)
                else:
                    self.face_image.set_from_icon_name("user-info", Gtk.IconSize.DIALOG)
            except Exception:
                self.face_image.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)

            if self.lock_switch:
                self.lock_switch.set_active(False)
            if self.idle_switch:
                self.idle_switch.set_active(False)
            print("Settings reset to defaults.")
        dialog.destroy()

    def on_close(self, widget):
        if self.application:
            self.application.quit()
        else:
            self.destroy()
