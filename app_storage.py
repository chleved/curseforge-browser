import json
import os
import re
import sys
from datetime import datetime


class AppStorage:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or self._get_base_dir()
        self.settings_file = os.path.join(self.base_dir, "settings.json")

    def _get_base_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

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
        except Exception as error:
            print(f"Cache load error: {error}")
            return []

        total_items = len(loaded_data)
        if total_items == 0:
            return []

        mods = []
        for index, item in enumerate(loaded_data):
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
