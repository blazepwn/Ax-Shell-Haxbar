import subprocess
import re
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.entry import Entry
from gi.repository import Gtk, Gdk, GLib
import modules.icons as icons
from utils.async_subprocess import run_command_with_output_async

class NetworkMenu(Box):
    def __init__(self, notch, **kwargs):
        super().__init__(
            name="network-menu",
            visible=False,
            all_visible=False,
            **kwargs,
        )
        self.notch = notch
        self.selected_index = -1
        self._all_interfaces = []

        # Viewport for interfaces
        self.interfaces_box = Box(
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
            child=self.interfaces_box,
            propagate_width=False,
            propagate_height=False,
        )

        # Header with Search Entry and Close Button
        self.search_entry = Entry(
            name="search-entry",
            placeholder="Search Network Interfaces...",
            h_expand=True,
            h_align="fill",
            notify_text=lambda entry, *_: self.arrange_viewport(entry.get_text()),
            on_key_press_event=self.on_search_entry_key_press,
        )
        self.search_entry.props.xalign = 0.5

        self.header_box = Box(
            name="header_box",
            spacing=10,
            orientation="h",
            children=[
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
            children=[
                self.header_box,
                self.scrolled_window,
            ]
        )

        self.add(self.content_box)
        self.show_all()

    def refresh_interfaces(self):
        # Clear existing data
        self._all_interfaces = []
        self.search_entry.set_text("")
        self.selected_index = -1

        # Add "Auto / Default" option as first item
        self._all_interfaces.append({
            "name": "Default (Auto)",
            "iface": None,
            "icon": icons.wifi_3,
            "desc": "Sort options automatically",
            "priority": 0
        })

        # List interfaces async
        self.list_interfaces()

    def list_interfaces(self):
        def on_success(output: bytes):
            text = output.decode("utf-8", errors="ignore")
            lines = text.strip().split('\n')
            
            collected_interfaces = []
            
            for line in lines:
                parts = line.split(': ')
                if len(parts) >= 2:
                    iface_name = parts[1].strip()
                    if iface_name == "lo":
                        continue
                        
                    # Determine icon based on name
                    icon = icons.wifi_3
                    desc = "Wireless Interface"
                    priority = 3 # Default priority
                    
                    if iface_name.startswith("e"): # eth0, enp3s0
                         icon = icons.wifi_3 # Or a wired icon if available
                         desc = "Ethernet Interface"
                         priority = 1
                    elif iface_name.startswith("w"): # wlan0
                         icon = icons.wifi_3
                         desc = "Wireless Interface"
                         priority = 2
                    elif iface_name.startswith("tun"): # tun0
                         icon = icons.world
                         desc = "Tunnel/VPN Interface"
                         priority = 4
                    elif iface_name.startswith("vmnet"):
                        icon = icons.world
                        desc = "Virtual Machine Network"
                        priority = 5
                    
                    collected_interfaces.append({
                        "name": iface_name,
                        "iface": iface_name,
                        "icon": icon,
                        "desc": desc,
                        "priority": priority
                    })
            
            # Sort interfaces: Default (0) -> Eth (1) -> Wlan (2) -> Tun (4) -> Others (5)
            # Default is already in _all_interfaces, so we sort collected ones
            collected_interfaces.sort(key=lambda x: (x["priority"], x["name"]))
            
            self._all_interfaces.extend(collected_interfaces)
            
            # Populate initial view
            self.arrange_viewport()

        run_command_with_output_async(
            ["ip", "-o", "link", "show"],
            on_success=on_success
        )

    def arrange_viewport(self, query: str = ""):
        # Clear current buttons
        for child in self.interfaces_box.get_children():
            self.interfaces_box.remove(child)
        
        self.selected_index = -1
        query = query.casefold()

        # Filter and add buttons
        filtered_items = [
            item for item in self._all_interfaces
            if query in item["name"].casefold() or query in item["desc"].casefold()
        ]

        for item in filtered_items:
            self.add_interface_button(item)
        
        # Reset scroll
        GLib.idle_add(self._reset_scroll)
        
        # Auto-select first item if query isn't empty
        if query and filtered_items:
             self.update_selection(0)

    def add_interface_button(self, item):
        btn = Button(
            name="slot-button",
            child=Box(
                name="slot-box",
                orientation="h",
                spacing=10,
                children=[
                    Label(
                        name="clip-icon",
                        markup=item["icon"],
                        h_align="start",
                        v_align="center",
                    ),
                    Box(
                        orientation="v",
                        v_align="center",
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
                            ) if item["desc"] else None
                        ]
                    )
                ]
            ),
            on_clicked=lambda *_: self.on_interface_selected(item["iface"])
        )
        self.interfaces_box.add(btn)
        self.interfaces_box.show_all()

    def on_interface_selected(self, iface_name):
        if self.notch and self.notch.bar and self.notch.bar.local_ip:
            self.notch.bar.local_ip.set_interface(iface_name)
        
        self.notch.close_notch()

    def on_search_entry_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Down:
            self.move_selection(1)
            return True
        elif event.keyval == Gdk.KEY_Up:
            self.move_selection(-1)
            return True
        elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            children = self.interfaces_box.get_children()
            if self.selected_index != -1 and 0 <= self.selected_index < len(children):
                children[self.selected_index].clicked()
            return True
        elif event.keyval == Gdk.KEY_Escape:
            self.notch.close_notch()
            return True
        return False

    def move_selection(self, delta: int):
        children = self.interfaces_box.get_children()
        if not children:
            return

        if self.selected_index == -1 and delta == 1:
            new_index = 0
        else:
            new_index = self.selected_index + delta
        
        # Clamp index
        new_index = max(0, min(new_index, len(children) - 1))
        self.update_selection(new_index)

    def update_selection(self, new_index: int):
        children = self.interfaces_box.get_children()
        
        if self.selected_index != -1 and self.selected_index < len(children):
            current_button = children[self.selected_index]
            current_button.get_style_context().remove_class("selected")

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
            if alloc.height == 0:
                return False

            y = alloc.y
            height = alloc.height
            page_size = adj.get_page_size()
            current_value = adj.get_value()

            visible_top = current_value
            visible_bottom = current_value + page_size

            if y < visible_top:
                adj.set_value(y)
            elif y + height > visible_bottom:
                new_value = y + height - page_size
                adj.set_value(new_value)

            return False
        GLib.idle_add(scroll)

    def open(self):
        self.refresh_interfaces()
        # Focus the search entry when opening
        self.search_entry.grab_focus()

    def _reset_scroll(self):
        adj = self.scrolled_window.get_vadjustment()
        adj.set_value(0)
