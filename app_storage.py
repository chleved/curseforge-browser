import json
import os
import re
import sys
from datetime import datetime


class AppStorage:
    def __init__(self, base_dir=None):
        self.legacy_base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = base_dir or self._get_base_dir()
        os.makedirs(self.base_dir, exist_ok=True)
        self.settings_file = os.path.join(self.base_dir, "settings.json")
        self._migrate_legacy_settings()

    def _get_base_dir(self):
        app_name_windows = "Cursepante"
        app_name_unix = "cursepante"

        if os.name == "nt":
            app_data_root = os.getenv("APPDATA") or os.path.expanduser("~")
            return os.path.join(app_data_root, app_name_windows)

        xdg_config_home = os.getenv("XDG_CONFIG_HOME")
        if xdg_config_home:
            return os.path.join(xdg_config_home, app_name_unix)
        return os.path.join(os.path.expanduser("~"), ".config", app_name_unix)

    def _migrate_legacy_settings(self):
        legacy_settings_file = os.path.join(self.legacy_base_dir, "settings.json")
        if self.base_dir == self.legacy_base_dir:
            return
        if os.path.exists(self.settings_file) or not os.path.exists(legacy_settings_file):
            return

        try:
            with open(legacy_settings_file, "r", encoding="utf-8") as file:
                legacy_data = json.load(file)
        except Exception as error:
            print(f"Legacy settings migration load error: {error}")
            return

        if not isinstance(legacy_data, dict):
            return

        if not self._save_settings(legacy_data):
            print("Legacy settings migration save error: failed to write migrated settings")

    def load_api_key(self):
        config = self._load_settings()
        return str(config.get("curseforge_api_key", "")).strip()

    def save_api_key(self, api_key):
        config = self._load_settings()
        config["curseforge_api_key"] = api_key.strip()
        return self._save_settings(config)

    def load_selected_version(self, default_version):
        config = self._load_settings()
        selected = str(config.get("minecraft_game_version", "")).strip()
        return selected or default_version

    def save_selected_version(self, version):
        config = self._load_settings()
        config["minecraft_game_version"] = str(version).strip()
        return self._save_settings(config)

    def load_selected_loader_type(self, default_loader_type=0):
        config = self._load_settings()
        try:
            selected = int(config.get("minecraft_mod_loader_type", default_loader_type))
        except (TypeError, ValueError):
            return int(default_loader_type)
        return selected if 0 <= selected <= 6 else int(default_loader_type)

    def save_selected_loader_type(self, loader_type):
        config = self._load_settings()
        config["minecraft_mod_loader_type"] = int(loader_type)
        return self._save_settings(config)

    def get_cache_file(self, mode, game_version, loader_type=0):
        version_token = re.sub(r"[^A-Za-z0-9]+", "_", str(game_version).strip()).strip("_")
        if not version_token:
            version_token = "default"
        loader_token = f"loader_{int(loader_type)}"
        filename = f"{mode}_{version_token}_{loader_token}.json"
        return os.path.join(self.base_dir, filename)

    def _load_settings(self):
        if not os.path.exists(self.settings_file):
            return {}
        try:
            with open(self.settings_file, "r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict):
                return data
            print(f"Settings load error: expected JSON object, got {type(data).__name__}")
            self._backup_malformed_json(self.settings_file)
            return {}
        except json.JSONDecodeError as error:
            print(f"Settings load error: {error}")
            self._backup_malformed_json(self.settings_file)
            return {}
        except Exception as error:
            print(f"Settings load error: {error}")
            return {}

    def _save_settings(self, data):
        try:
            with open(self.settings_file, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
            return True
        except Exception as error:
            print(f"Settings save error: {error}")
            return False

    def load_cache(self, cache_file, progress_callback=None):
        if not os.path.exists(cache_file):
            return []

        try:
            with open(cache_file, "r", encoding="utf-8") as file:
                loaded_data = json.load(file)
        except json.JSONDecodeError as error:
            print(f"Cache load error: {error}")
            self._backup_malformed_json(cache_file)
            return []
        except Exception as error:
            print(f"Cache load error: {error}")
            return []

        if not isinstance(loaded_data, list):
            print(f"Cache load error: expected JSON array, got {type(loaded_data).__name__}")
            self._backup_malformed_json(cache_file)
            return []

        total_items = len(loaded_data)
        if total_items == 0:
            return []

        mods = []
        for index, item in enumerate(loaded_data):
            if not isinstance(item, dict):
                print(f"Cache load warning: skipping non-object item at index {index}")
                continue
            mod = item.copy()
            if mod.get("update_date"):
                mod["update_date"] = self._parse_datetime(mod["update_date"])
            mods.append(mod)

            if progress_callback and index % 50 == 0:
                progress = (index / total_items) * 100
                progress_callback(progress)

        return mods

    def save_cache(self, cache_file, mods):
        try:
            data_to_save = []
            for mod in mods:
                item = mod.copy()
                update_date = item.get("update_date")
                if isinstance(update_date, datetime):
                    item["update_date"] = update_date.isoformat()
                elif update_date is None:
                    item["update_date"] = None
                data_to_save.append(item)

            with open(cache_file, "w", encoding="utf-8") as file:
                json.dump(data_to_save, file, indent=2)
            return True
        except Exception as error:
            print(f"Cache save error: {error}")
            return False

    def _parse_datetime(self, value):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _backup_malformed_json(self, file_path):
        if not os.path.exists(file_path):
            return

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = f"{file_path}.corrupt-{timestamp}"
        suffix = 1
        while os.path.exists(backup_path):
            suffix += 1
            backup_path = f"{file_path}.corrupt-{timestamp}-{suffix}"

        try:
            os.replace(file_path, backup_path)
            print(f"Malformed JSON moved to backup: {backup_path}")
        except Exception as error:
            print(f"Failed to back up malformed JSON file '{file_path}': {error}")
