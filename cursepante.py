import os
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

from app_storage import AppStorage
from constants import (
    APP_FONT_FAMILY,
    BASE_ENTRY_FONT_SIZE,
    BASE_WINDOW_HEIGHT,
    BASE_WINDOW_WIDTH,
    DEFAULT_CLASS_ID,
    DEFAULT_GAME_VERSION,
    GAME_ID,
    MODS_MODE,
    MOD_LOADER_LABELS,
)
from curseforge_client import CurseForgeClient
from refresh_mixin import RefreshMixin
from results_mixin import ResultsMixin
from settings_mixin import SettingsMixin
from sorting_mixin import SortingMixin
from ui_layout_mixin import UILayoutMixin
from ui_setup_mixin import UISetupMixin


class CurseForgeModBrowser(RefreshMixin, SortingMixin, SettingsMixin, UILayoutMixin, UISetupMixin, ResultsMixin):
    def __init__(self, root):
        self.root = root
        self.root.title("CurseForge Browser for Minecraft Forge")
        self.root.geometry(f"{BASE_WINDOW_WIDTH}x{BASE_WINDOW_HEIGHT}")
        self.root.minsize(900, 560)

        self.storage = AppStorage()
        self.curseforge_api_key = (os.getenv("curseforge_api_key") or self.storage.load_api_key()).strip()
        self.current_version = self.storage.load_selected_version(DEFAULT_GAME_VERSION)
        self.current_loader_type = self.storage.load_selected_loader_type(0)
        if self.current_loader_type not in MOD_LOADER_LABELS:
            self.current_loader_type = 0
        self.client = CurseForgeClient(self.curseforge_api_key)

        self.params = {
            "gameId": GAME_ID,
            "searchFilter": "",
            "pageSize": 50,
            "classId": DEFAULT_CLASS_ID,
            "sortField": 3,
            "sortOrder": "desc",
            "gameVersion": self.current_version,
        }
        if self.current_loader_type > 0:
            self.params["modLoaderType"] = self.current_loader_type

        self.current_page = 0
        self.total_pages = 1
        self.page_size = 15
        self.page_size_var = tk.IntVar(value=self.page_size)
        self.page_number_var = tk.StringVar(value="1")
        self.all_mods = []
        self.mods_data = {}
        self.sort_column = "downloads"
        self.sort_reverse = True
        self.search_var = tk.StringVar()
        self.version_var = tk.StringVar(value=self.current_version)
        self.loader_var = tk.StringVar(value=MOD_LOADER_LABELS[self.current_loader_type])
        self.mode_var = tk.StringVar(value=MODS_MODE)
        self.loading_progress_var = tk.DoubleVar(value=0.0)
        self.loading_progress_text_var = tk.StringVar(value="Idle")
        self.lock = threading.Lock()
        self.available_versions = [self.current_version]
        self.available_loader_types = [0]
        self.cache_file = self.storage.get_cache_file(self.mode_var.get(), self.current_version, self.current_loader_type)

        self.image_loader = None

        self.tooltip_window = None
        self.tooltip_job = None
        self.search_job = None
        self.page_change_job = None
        self.current_tooltip_item = None
        self.refresh_queue = queue.Queue()
        self.refresh_request_counter = 0
        self.active_refresh_id = 0
        self.refresh_lock = threading.Lock()
        self.is_refresh_active = False
        self._last_resize_signature = None
        self._last_density_signature = None
        self.tree_font = tkfont.Font(family=APP_FONT_FAMILY, size=BASE_ENTRY_FONT_SIZE)

        self.setup_ui()

        if not self.ensure_api_key():
            self.root.quit()
            return

        threading.Thread(target=self.run_refresh_queue_worker, daemon=True).start()
        threading.Thread(target=self.load_versions_thread, daemon=True).start()
        self.queue_refresh("initial")


def main():
    root = tk.Tk()
    CurseForgeModBrowser(root)
    root.mainloop()


if __name__ == "__main__":
    main()
