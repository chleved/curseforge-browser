import threading
from tkinter import messagebox, simpledialog

from constants import MOD_LOADER_LABELS


class SettingsMixin:
    def set_selected_version(self, version):
        selected_version = str(version).strip()
        if not selected_version:
            return
        self.current_version = selected_version
        self.params["gameVersion"] = selected_version
        self.cache_file = self.storage.get_cache_file(self.mode_var.get(), selected_version, self.current_loader_type)
        self.version_var.set(selected_version)
        self.update_sort_headings()
        self.storage.save_selected_version(selected_version)

    def set_selected_loader_type(self, loader_type):
        try:
            selected_loader_type = int(loader_type)
        except (TypeError, ValueError):
            selected_loader_type = 0
        if selected_loader_type not in MOD_LOADER_LABELS:
            selected_loader_type = 0

        self.current_loader_type = selected_loader_type
        self.loader_var.set(MOD_LOADER_LABELS[selected_loader_type])
        if selected_loader_type > 0:
            self.params["modLoaderType"] = selected_loader_type
        else:
            self.params.pop("modLoaderType", None)

        self.cache_file = self.storage.get_cache_file(self.mode_var.get(), self.current_version, selected_loader_type)
        self.storage.save_selected_loader_type(selected_loader_type)

    def load_versions_thread(self):
        self.set_status("Loading Minecraft versions...")
        try:
            versions = self.client.get_minecraft_versions(status_callback=self.set_status)
            self.root.after(0, lambda items=versions: self.apply_versions_list(items))
        except Exception as error:
            self.set_status(f"Failed to load versions list: {error}")

    def load_loaders_thread(self, version):
        target_version = str(version).strip()
        if not target_version:
            return
        self.set_status(f"Loading mod loaders for {target_version}...")
        try:
            loaders = self.client.get_minecraft_modloaders(
                version=target_version,
                include_all=True,
                status_callback=self.set_status,
            )
            self.root.after(0, lambda items=loaders, v=target_version: self.apply_loaders_list(v, items))
        except Exception as error:
            self.set_status(f"Failed to load mod loaders: {error}")

    def apply_versions_list(self, versions):
        cleaned_versions = [v for v in versions if v]
        if not cleaned_versions:
            cleaned_versions = [self.current_version]

        self.available_versions = cleaned_versions
        self.version_combo["values"] = self.available_versions

        if self.current_version in self.available_versions:
            self.version_var.set(self.current_version)
        else:
            self.set_selected_version(self.available_versions[0])
            self.queue_refresh("version list loaded")

        threading.Thread(target=self.load_loaders_thread, args=(self.current_version,), daemon=True).start()

    def apply_loaders_list(self, version, loaders):
        if str(version).strip() != self.current_version:
            return

        discovered_types = {0}
        for item in loaders:
            try:
                loader_type = int(item.get("type", 0))
            except (TypeError, ValueError):
                continue
            if loader_type in MOD_LOADER_LABELS:
                discovered_types.add(loader_type)

        self.available_loader_types = sorted(discovered_types)
        self.loader_combo["values"] = [MOD_LOADER_LABELS[loader_type] for loader_type in self.available_loader_types]

        if self.current_loader_type not in self.available_loader_types:
            self.set_selected_loader_type(0)
            self.queue_refresh("loader list loaded")
            return

        self.loader_var.set(MOD_LOADER_LABELS[self.current_loader_type])

    def save_api_key(self, api_key):
        if self.storage.save_api_key(api_key):
            return True
        messagebox.showerror("Save Error", "Failed to save API key to local app settings")
        return False

    def ensure_api_key(self):
        if self.curseforge_api_key and self.curseforge_api_key != "YOUR_curseforge_api_key_HERE":
            return True

        entered_key = simpledialog.askstring(
            "CurseForge API Key",
            "Enter your CurseForge API key. It will be saved in local app settings for next launches.",
            parent=self.root,
            show="*",
        )
        if not entered_key or not entered_key.strip():
            messagebox.showerror("API Key Required", "A valid CurseForge API key is required to use the app.")
            return False

        self.curseforge_api_key = entered_key.strip()
        self.client.set_api_key(self.curseforge_api_key)
        self.save_api_key(self.curseforge_api_key)
        return True

    def set_api_key(self):
        new_key = simpledialog.askstring(
            "Set CurseForge API Key",
            "Enter your CurseForge API key:",
            parent=self.root,
            initialvalue=self.curseforge_api_key or "",
            show="*",
        )
        if new_key is None:
            return

        new_key = new_key.strip()
        if not new_key:
            messagebox.showerror("Invalid Key", "API key cannot be empty.")
            return

        self.curseforge_api_key = new_key
        self.client.set_api_key(new_key)
        if self.save_api_key(new_key):
            self.set_status("API key saved. New requests will use the updated key.")
            threading.Thread(target=self.load_versions_thread, daemon=True).start()

    def on_version_change(self, _event):
        selected_version = self.version_var.get().strip()
        if not selected_version or selected_version == self.current_version:
            return
        self.set_selected_version(selected_version)
        threading.Thread(target=self.load_loaders_thread, args=(selected_version,), daemon=True).start()
        self.queue_refresh("version change")

    def on_loader_change(self, _event):
        selected_label = self.loader_var.get().strip()
        selected_loader = next(
            (loader_type for loader_type, label in MOD_LOADER_LABELS.items() if label == selected_label),
            0,
        )
        if selected_loader == self.current_loader_type:
            return
        self.set_selected_loader_type(selected_loader)
        self.queue_refresh("loader change")
