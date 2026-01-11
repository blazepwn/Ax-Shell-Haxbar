
import os
import subprocess
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.entry import Entry
from gi.repository import Gtk, Gdk, GLib
import modules.icons as icons
import config.data as data
from utils.async_subprocess import run_command_with_output_async

class VPNMenu(Box):
    def __init__(self, notch, **kwargs):
        super().__init__(
            name="network-menu", # Reusing generic menu styling
            visible=False,
            all_visible=False,
            **kwargs,
        )
        self.notch = notch
        self.selected_index = -1
        self._all_vpns = []
        self._current_process = None
        self._active_vpn_path = None

        # Viewport for VPN items
        self.vpns_box = Box(
            name="network-interfaces",
            orientation="v",
            spacing=4,
            v_expand=True,
            h_expand=True,
        )

        self.scrolled_window = ScrolledWindow(
            name="scrolled-window",
            spacing=10,
            h_expand=True,
            v_expand=True,
            child=self.vpns_box,
            propagate_width=False,
            propagate_height=False,
        )

        # Header with Search Entry and Close Button
        self.search_entry = Entry(
            name="search-entry",
            placeholder="Search VPN Configs...",
            h_expand=True,
            h_align="fill",
            notify_text=lambda entry, *_: self.arrange_viewport(entry.get_text()),
            on_key_press_event=self.on_search_entry_key_press,
        )
        self.search_entry.props.xalign = 0.5

        # Disconnect Button
        self.disconnect_btn = Button(
            name="stop-button",
            child=Label(name="stop-label", markup=icons.lock), # Changed from world_off
            tooltip_text="Disconnect VPN",
            on_clicked=lambda *_: self.disconnect_vpn()
        )
        self.disconnect_btn.set_sensitive(False) # Default disabled

        self.header_box = Box(
            name="header_box",
            spacing=15,
            orientation="h",
            style="margin: 5px 5px 10px 5px;",
            children=[
                self.disconnect_btn,
                self.search_entry,
                Button(
                    name="close-button",
                    child=Label(name="close-label", markup=icons.cancel),
                    tooltip_text="Close",
                    on_clicked=lambda *_: self.notch.close_notch()
                ),
            ]
        )

        # Main Content Wrapper
        self.content_box = Box(
            name="launcher-box",
            spacing=10,
            orientation="v",
            h_expand=True,
            style="margin: 10px;",
            children=[
                self.header_box,
                self.scrolled_window,
            ]
        )

        self.add(self.content_box)
        self.show_all()
        # Initial check for status
        GLib.timeout_add_seconds(5, self.check_connection_status)

    def open(self):
        self.refresh_vpns()
        self.search_entry.set_text("")
        self.search_entry.grab_focus()
        self.check_connection_status()

    def refresh_vpns(self):
        self._all_vpns = []
        self.selected_index = -1
        
        path = data.OVPN_PATH
        if not path or not os.path.isdir(path):
            self._all_vpns.append({
                "name": "Error: OVPN Path not set",
                "path": None,
                "desc": "Go to Settings -> System to configure",
                "icon": icons.alert
            })
            self.arrange_viewport()
            return

        # List .ovpn files
        try:
            for f in os.listdir(path):
                if f.endswith(".ovpn"):
                    full_path = os.path.join(path, f)
                    self._all_vpns.append({
                        "name": f.replace(".ovpn", ""),
                        "path": full_path,
                        "desc": full_path,
                        "icon": icons.lock
                    })
            
            # Sort alphabetically
            self._all_vpns.sort(key=lambda x: x["name"].lower())
            
        except Exception as e:
             self._all_vpns.append({
                "name": "Error reading directory",
                "path": None,
                "desc": str(e),
                "icon": icons.alert
            })

        self.arrange_viewport()

    def arrange_viewport(self, query: str = ""):
        # Clear current buttons
        for child in self.vpns_box.get_children():
            self.vpns_box.remove(child)
        
        self.selected_index = -1
        query = query.casefold()

        # Filter and add buttons
        filtered_items = [
            item for item in self._all_vpns
            if query in item["name"].casefold() 
        ]

        if not filtered_items and not self._all_vpns:
             # Empty state
             pass

        for item in filtered_items:
            self.add_vpn_button(item)
        
        GLib.idle_add(self._reset_scroll)
        
        if query and filtered_items:
             self.update_selection(0)

    def add_vpn_button(self, item):
        path = item["path"]
        
        # Inline Disconnect Button (Initially Hidden)
        inline_disconnect = Button(
            name="inline-stop-button",
            child=Label(name="stop-label-small", markup=icons.cancel), 
            tooltip_text="Disconnect this VPN",
            visible=False,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.END,
            on_clicked=lambda btn, *_: self.disconnect_vpn()
        )
        # Force layout behavior to prevent stretching
        inline_disconnect.set_size_request(24, 24)
        inline_disconnect.set_halign(Gtk.Align.END)
        inline_disconnect.set_valign(Gtk.Align.CENTER)
        inline_disconnect.set_hexpand(False)
        inline_disconnect.set_vexpand(False)
        
        # Margin to pull it away from the edge slightly
        inline_disconnect.set_margin_end(10)

        # Main Button Content
        box_children = [
            Label(
                name="clip-icon",
                markup=item["icon"],
                h_align="start",
                v_align="center",
            ),
            Box(
                orientation="v",
                v_align="center",
                h_expand=True, 
                children=[
                    Label(
                        name="app-label",
                        label=item["name"],
                        h_align="start",
                    ),
                    Label(
                        name="app-desc",
                        label=item["desc"],
                        h_align="start",
                        ellipsization="end"
                    ) 
                ]
            ),
        ]

        # Main Button
        btn = Button(
            name="slot-button",
            child=Box(
                name="slot-box",
                orientation="h",
                spacing=15,
                children=box_children
            ),
            h_expand=True,
            on_clicked=lambda *_: self.connect_vpn(path) if path != self._active_vpn_path else None
        )
        btn._vpn_path = path
        btn._inline_disconnect = inline_disconnect # Link for updates

        # Overlay Container
        overlay = Gtk.Overlay()
        overlay.add(btn) # Main widget
        overlay.add_overlay(inline_disconnect) # Overlay widget
        
        # We need to link the Overlay or Btn to the list for updates
        # The update check loops over children of self.vpns_box
        # So we should add attributes to the *Overlay* or find the btn inside.
        # Better: Add attributes to the Overlay widget which is direct child of vpns_box
        overlay._vpn_path = path
        overlay._main_btn = btn
        overlay._inline_disconnect = inline_disconnect

        self.vpns_box.add(overlay)
        self.vpns_box.show_all()
        inline_disconnect.set_visible(False) 

    def update_vpn_states(self):
        for child in self.vpns_box.get_children():
            # Child is now the Overlay
            if not hasattr(child, "_vpn_path"):
                continue
                
            path = child._vpn_path
            main_btn = child._main_btn
            disconnect_btn = child._inline_disconnect
            
            is_active = (path == self._active_vpn_path) and (self._active_vpn_path is not None)
            
            style = main_btn.get_style_context()
            if is_active:
                style.add_class("active-vpn")
                # Showing toggle button
                disconnect_btn.set_visible(True)
                disconnect_btn.set_sensitive(True) 
            else:
                style.remove_class("active-vpn")
                main_btn.set_sensitive(True)
                disconnect_btn.set_visible(False)

    def connect_vpn(self, config_path):
        if not config_path:
            return

        # Close notch immediately to let polkit grab focus
        self.notch.close_notch()

        # Use pkexec to run openvpn in a separate process
        # We use setsid or nohup equivalent logic by just spawning it detached?
        # A simple way is to use a terminal or a helper script.
        # Here we try to run it directly.
        
        cmd = ["pkexec", "openvpn", "--config", config_path, "--daemon"]
        
        def on_done(output):
            print(f"VPN Launch Output: {output}")
            # Wait a bit then check status manually once
            GLib.timeout_add(2000, lambda: self.check_connection_status(single_shot=True))

        run_command_with_output_async(cmd, on_success=on_done)
        
        # User notification
        # This part assumes pkexec will handle the UI prompt itself (it does).

    def disconnect_vpn(self):
        # Close notch immediately to let polkit get focus if needed,
        # and to provide immediate feedback that action was taken.
        self.notch.close_notch()
        
        # Kill all openvpn processes
        cmd = ["pkexec", "pkill", "openvpn"]
        run_command_with_output_async(cmd, on_success=lambda _: self.check_connection_status(single_shot=True))

    def check_connection_status(self, single_shot=False):
        # Check if openvpn is running and get arguments
        def on_pgrep(output):
            self._active_vpn_path = None
            is_running = False
            
            try:
                if isinstance(output, bytes):
                    output = output.decode("utf-8").strip()
                else:
                    output = str(output).strip()
            except Exception as e:
                print(f"Error decoding pgrep output: {e}")
                output = ""

            if output:
                lines = output.split('\n')
                for line in lines:
                    # Line format usually: PID COMMAND ARGS...
                    # We match both "openvpn" and "--config" just to be safe
                    if "openvpn" in line and "--config" in line:
                        parts = line.split()
                        try:
                            # Iterate to find --config and the NEXT argument
                            if "--config" in parts:
                                idx = parts.index("--config")
                                if idx + 1 < len(parts):
                                    # Normalize path for comparison
                                    raw_path = parts[idx + 1]
                                    self._active_vpn_path = os.path.abspath(raw_path)
                                    is_running = True
                                    break
                        except ValueError:
                            pass
            
            self._update_ui_state(is_running)
            return False

        def on_pgrep_error(e):
            # Process not found (exit code 1) or other error
            self._active_vpn_path = None
            self._update_ui_state(False)
            return False

        run_command_with_output_async(
            ["pgrep", "-a", "openvpn"], 
            on_success=on_pgrep, 
            on_error=on_pgrep_error # Handle exit code 1
        )
        
        if single_shot:
            return False
        return True # Keep running if called via timeout_add
    
    def _update_ui_state(self, is_running):
        self.disconnect_btn.set_sensitive(is_running)
        
        # Update style of disconnect button in header
        ctx = self.disconnect_btn.get_style_context()
        if is_running:
            ctx.add_class("active")
        else:
            ctx.remove_class("active")
        
        # Update individual VPN items
        self.update_vpn_states()

    def on_search_entry_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Down:
            self.move_selection(1)
            return True
        elif event.keyval == Gdk.KEY_Up:
            self.move_selection(-1)
            return True
        elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            children = self.vpns_box.get_children()
            if self.selected_index != -1 and 0 <= self.selected_index < len(children):
                children[self.selected_index].clicked()
            return True
        elif event.keyval == Gdk.KEY_Escape:
            self.notch.close_notch()
            return True
        return False

    def move_selection(self, delta: int):
        children = self.vpns_box.get_children()
        if not children:
            return
        if self.selected_index == -1 and delta == 1:
            new_index = 0
        else:
            new_index = self.selected_index + delta
        new_index = max(0, min(new_index, len(children) - 1))
        self.update_selection(new_index)

    def update_selection(self, new_index: int):
        children = self.vpns_box.get_children()
        
        if self.selected_index != -1 and self.selected_index < len(children):
            children[self.selected_index].get_style_context().remove_class("selected")

        if new_index != -1 and new_index < len(children):
            new_button = children[new_index]
            new_button.get_style_context().add_class("selected")
            self.selected_index = new_index
            self.scroll_to_selected(new_button)
        else:
            self.selected_index = -1

    def scroll_to_selected(self, button):
        def scroll():
            adj = self.scrolled_window.get_vadjustment()
            alloc = button.get_allocation()
            if alloc.height == 0: return False
            y = alloc.y
            height = alloc.height
            page_size = adj.get_page_size()
            current_value = adj.get_value()
            if y < current_value:
                adj.set_value(y)
            elif y + height > current_value + page_size:
                adj.set_value(y + height - page_size)
            return False
        GLib.idle_add(scroll)

    def _reset_scroll(self):
        if not self.scrolled_window:
            return False
            
        adj = self.scrolled_window.get_vadjustment()
        if adj and isinstance(adj, Gtk.Adjustment) and adj.get_upper() > 0:
            adj.set_value(0)
        return False
