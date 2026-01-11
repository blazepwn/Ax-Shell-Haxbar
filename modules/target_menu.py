
import os
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.entry import Entry
from gi.repository import Gtk, Gdk, GLib
import modules.icons as icons

class TargetMenu(Box):
    def __init__(self, notch, **kwargs):
        super().__init__(
            name="target-menu",
            visible=False,
            all_visible=False,
            orientation="v",
            spacing=10,
            style="margin: 15px;",
            **kwargs,
        )
        self.notch = notch
        self.target_file = os.path.expanduser("~/.config/Ax-Shell/scripts/target")

        # Header
        self.header_box = Box(
            name="header_box",
            spacing=10,
            orientation="h",
            children=[
                Label(
                    markup=icons.radar, 
                    style="font-size: 16px; margin-right: 5px;"
                ),
                Label(
                    label="Target Configuration", 
                    style="font-weight: bold; font-size: 16px;"
                ),
                Box(h_expand=True),
                Button(
                    name="close-button",
                    child=Label(name="close-label", markup=icons.cancel),
                    tooltip_text="Close",
                    on_clicked=lambda *_: self.notch.close_notch()
                ),
            ]
        )
        self.add(self.header_box)

        # Content
        content_box = Box(orientation="v", spacing=15, style="margin-top: 10px;")
        
        # IP Input
        ip_label = Label(label="Target IP", h_align="start", style="font-weight: bold;")
        self.ip_entry = Entry(
            placeholder="e.g. 10.10.11.24",
            h_expand=True,
            name="search-entry", # Reuse entry style
            on_activate=lambda *_: self.name_entry.grab_focus()
        )
        content_box.add(ip_label)
        content_box.add(self.ip_entry)

        # Name Input
        name_label = Label(label="Target Name", h_align="start", style="font-weight: bold;")
        self.name_entry = Entry(
            placeholder="e.g. OmniBox",
            h_expand=True,
            name="search-entry",
            on_activate=lambda *_: self.set_target()
        )
        content_box.add(name_label)
        content_box.add(self.name_entry)

        # Actions
        actions_box = Box(orientation="h", spacing=10, style="margin-top: 10px;")
        
        self.set_btn = Button(
            label="Set Target",
            h_expand=True,
            style_classes=["primary-button"], # Assuming this class exists or generic button
            on_clicked=lambda *_: self.set_target()
        )
        # Apply style manually if needed to match theme
        self.set_btn.set_style("padding: 8px; background-color: #89b4fa; color: #1e1e2e; border-radius: 8px; font-weight: bold;")
        
        self.clear_btn = Button(
            label="Clear",
            # tooltip_text="Clear target",
            h_expand=False,
            style="padding: 8px; background-color: #45475a; color: #cdd6f4; border-radius: 8px;",
            on_clicked=lambda *_: self.clear_target()
        )

        actions_box.add(self.set_btn)
        actions_box.add(self.clear_btn)
        content_box.add(actions_box)

        self.add(content_box)
        self.show_all()

    def open(self):
        # Load current target
        self._load_current()
        self.ip_entry.grab_focus()

    def _load_current(self):
        try:
            if os.path.exists(self.target_file):
                with open(self.target_file, "r") as f:
                    content = f.read().strip()
                if content:
                    parts = content.split(maxsplit=1)
                    if len(parts) >= 1:
                        self.ip_entry.set_text(parts[0])
                    if len(parts) >= 2:
                        self.name_entry.set_text(parts[1])
                    else:
                        self.name_entry.set_text("")
                else:
                    self._clear_fields()
            else:
                self._clear_fields()
        except:
            self._clear_fields()

    def _clear_fields(self):
        self.ip_entry.set_text("")
        self.name_entry.set_text("")

    def set_target(self):
        ip = self.ip_entry.get_text().strip()
        name = self.name_entry.get_text().strip()
        
        if not ip:
            return 
            
        os.makedirs(os.path.dirname(self.target_file), exist_ok=True)
        with open(self.target_file, "w") as f:
            if name:
                f.write(f"{ip} {name}")
            else:
                f.write(f"{ip}")
        
        self.notch.close_notch()

    def clear_target(self):
        os.makedirs(os.path.dirname(self.target_file), exist_ok=True)
        with open(self.target_file, "w") as f:
            f.write("") # Clear content
        
        self._clear_fields()
        self.notch.close_notch()
