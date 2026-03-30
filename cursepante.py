import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox, simpledialog, ttk

from app_storage import AppStorage
from curseforge_client import CurseForgeClient
from image_loader import AsyncImageLoader
from refresh_mixin import RefreshMixin
from sorting_mixin import SortingMixin


APP_FONT_FAMILY = "Segoe UI"
DEFAULT_CLASS_ID = 6
MODS_MODE = "mods"
RESOURCEPACKS_MODE = "resourcepacks"
DEFAULT_GAME_VERSION = "1.7.10"
BASE_WINDOW_WIDTH = 1100
BASE_WINDOW_HEIGHT = 700
BASE_ENTRY_FONT_SIZE = 10
BASE_HEADING_FONT_SIZE = 11
BASE_ROW_HEIGHT = 44
BASE_ICON_SIZE = 34
MIN_ROWS_PER_PAGE = 5
MAX_ROWS_PER_PAGE = 100
IMAGE_SIZE = (BASE_ICON_SIZE, BASE_ICON_SIZE)
MOD_LOADER_LABELS = {
    0: "Any",
    1: "Forge",
    2: "Cauldron",
    3: "LiteLoader",
    4: "Fabric",
    5: "Quilt",
    6: "NeoForge",
}
CURSEFORGE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.124 Safari/537.36"
)


class CurseForgeModBrowser(RefreshMixin, SortingMixin):
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
            "gameId": 432,
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

    def setup_ui(self):
        style = ttk.Style()
        style.configure("Treeview", rowheight=BASE_ROW_HEIGHT, font=(APP_FONT_FAMILY, BASE_ENTRY_FONT_SIZE))
        style.configure("Treeview.Heading", font=(APP_FONT_FAMILY, BASE_HEADING_FONT_SIZE, "bold"))

        nav_frame = ttk.Frame(self.root, padding="10")
        nav_frame.pack(fill=tk.X)

        nav_top_row = ttk.Frame(nav_frame)
        nav_top_row.pack(fill=tk.X, pady=(0, 6))

        nav_bottom_row = ttk.Frame(nav_frame)
        nav_bottom_row.pack(fill=tk.X)

        results_frame = ttk.Frame(self.root, padding="10")
        results_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(nav_top_row, text="Mode:", font=(APP_FONT_FAMILY, 10)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Radiobutton(nav_top_row, text="Mods", variable=self.mode_var, value=MODS_MODE, command=self.on_mode_change).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Radiobutton(nav_top_row, text="Resource Packs", variable=self.mode_var, value=RESOURCEPACKS_MODE, command=self.on_mode_change).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(nav_top_row, text="Version:", font=(APP_FONT_FAMILY, 10)).pack(side=tk.LEFT, padx=(0, 5))
        self.version_combo = ttk.Combobox(
            nav_top_row,
            textvariable=self.version_var,
            values=self.available_versions,
            state="readonly",
            width=12,
        )
        self.version_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.version_combo.bind("<<ComboboxSelected>>", self.on_version_change)

        ttk.Label(nav_top_row, text="Loader:", font=(APP_FONT_FAMILY, 10)).pack(side=tk.LEFT, padx=(0, 5))
        self.loader_combo = ttk.Combobox(
            nav_top_row,
            textvariable=self.loader_var,
            values=[MOD_LOADER_LABELS[loader_type] for loader_type in self.available_loader_types],
            state="readonly",
            width=10,
        )
        self.loader_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.loader_combo.bind("<<ComboboxSelected>>", self.on_loader_change)

        ttk.Label(nav_top_row, text="Search:", font=(APP_FONT_FAMILY, 10)).pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(nav_top_row, textvariable=self.search_var, width=24, font=(APP_FONT_FAMILY, 10))
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind("<KeyRelease>", self.on_search_key_release)

        ttk.Button(nav_top_row, text="Set API Key", command=self.set_api_key).pack(side=tk.LEFT, padx=(10, 0))

        self.prev_btn = ttk.Button(nav_bottom_row, text="← Previous", command=self.prev_page)
        self.prev_btn.pack(side=tk.LEFT, padx=(0, 5))

        page_nav_frame = ttk.Frame(nav_bottom_row)
        page_nav_frame.pack(side=tk.LEFT, padx=10)
        ttk.Label(page_nav_frame, text="Page", font=(APP_FONT_FAMILY, 10)).pack(side=tk.LEFT, padx=(0, 4))
        self.page_number_entry = ttk.Entry(
            page_nav_frame,
            textvariable=self.page_number_var,
            width=4,
            justify="center",
            font=(APP_FONT_FAMILY, 10),
        )
        self.page_number_entry.pack(side=tk.LEFT)
        self.page_number_entry.bind("<Return>", self.on_page_number_change)
        self.page_number_entry.bind("<FocusOut>", self.on_page_number_change)
        self.page_total_label = ttk.Label(page_nav_frame, text="of 1", font=(APP_FONT_FAMILY, 10))
        self.page_total_label.pack(side=tk.LEFT, padx=(4, 0))

        self.next_btn = ttk.Button(nav_bottom_row, text="Next →", command=self.next_page)
        self.next_btn.pack(side=tk.LEFT, padx=5)

        ttk.Label(nav_bottom_row, text="Per page:", font=(APP_FONT_FAMILY, 10)).pack(side=tk.LEFT, padx=(12, 5))
        self.page_size_spinbox = ttk.Spinbox(
            nav_bottom_row,
            from_=MIN_ROWS_PER_PAGE,
            to=MAX_ROWS_PER_PAGE,
            textvariable=self.page_size_var,
            width=4,
            command=self.on_page_size_change,
            justify="center",
        )
        self.page_size_spinbox.pack(side=tk.LEFT)
        self.page_size_spinbox.bind("<Return>", self.on_page_size_change)
        self.page_size_spinbox.bind("<FocusOut>", self.on_page_size_change)

        columns = ("name", "author", "downloads", "updated")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="tree headings")
        self.tree.heading("#0", text="Logo")
        self.tree.heading("name", text="Name", command=lambda: self.on_sort_column_selected("name"))
        self.tree.heading("author", text="Author", command=lambda: self.on_sort_column_selected("author"))
        self.tree.heading("downloads", text="Downloads", command=lambda: self.on_sort_column_selected("downloads"))
        self.tree.heading("updated", text="Last Updated", command=lambda: self.on_sort_column_selected("updated"))

        self.tree.column("#0", width=70, minwidth=52, stretch=tk.NO, anchor="center")
        self.tree.column("name", width=430, minwidth=180, stretch=tk.YES)
        self.tree.column("author", width=260, minwidth=220, stretch=tk.YES)
        self.tree.column("downloads", width=120, minwidth=100, stretch=tk.YES, anchor="center")
        self.tree.column("updated", width=260, minwidth=180, stretch=tk.YES, anchor="w")

        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self.open_mod_page)
        self.tree.bind("<Motion>", self.on_tree_motion)
        self.tree.bind("<Leave>", self.on_tree_leave)

        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.progress_container = tk.Frame(bottom_frame, height=24)
        self.progress_container.pack(fill=tk.X, side=tk.TOP)
        self.progress_container.pack_propagate(False)

        self.loading_progress = ttk.Progressbar(
            self.progress_container,
            mode="determinate",
            variable=self.loading_progress_var,
            maximum=100,
        )
        self.loading_progress.pack(fill=tk.BOTH, expand=True)

        self.loading_progress_label = tk.Label(
            self.progress_container,
            textvariable=self.loading_progress_text_var,
            bg="#f0f0f0",
            fg="#222222",
            font=(APP_FONT_FAMILY, 10, "bold"),
        )
        self.loading_progress_label.place(relx=0.5, rely=0.5, anchor="center")

        self.summary_label = ttk.Label(
            bottom_frame,
            text="",
            relief=tk.SUNKEN,
            anchor="center",
            font=(APP_FONT_FAMILY, 10, "bold"),
        )
        self.summary_label.pack(fill=tk.X, side=tk.TOP)
        self.summary_label.pack_forget()

        self.image_loader = AsyncImageLoader(
            root=self.root,
            tree=self.tree,
            user_agent=CURSEFORGE_USER_AGENT,
            image_size=IMAGE_SIZE,
        )
        self.update_sort_headings()
        self.root.bind("<Configure>", self.on_root_resize)
        self.root.after(0, lambda: self.apply_responsive_layout(self.root.winfo_width(), self.root.winfo_height()))
        self.root.after(0, self.apply_table_density)

    def show_loading_bar(self):
        if self.summary_label.winfo_ismapped():
            self.summary_label.pack_forget()
        if not self.progress_container.winfo_ismapped():
            self.progress_container.pack(fill=tk.X, side=tk.TOP)

    def show_summary_bar(self, text):
        self.summary_label.config(text=text)
        if self.progress_container.winfo_ismapped():
            self.progress_container.pack_forget()
        if not self.summary_label.winfo_ismapped():
            self.summary_label.pack(fill=tk.X, side=tk.TOP)

    def set_status(self, text):
        _ = text

    def set_loading_progress(self, mods_done, mods_total_hint, finished=False):
        def _update():
            self.show_loading_bar()
            mods_done_safe = max(0, int(mods_done))
            mods_total_safe = max(mods_done_safe, int(mods_total_hint) if mods_total_hint else 0)

            if finished:
                self.loading_progress_var.set(100.0)
                total_text = str(mods_total_safe if mods_total_safe > 0 else mods_done_safe)
                self.loading_progress_text_var.set(f"Loaded mods {mods_done_safe}/{total_text}")
                return

            mod_ratio = (mods_done_safe / mods_total_safe) if mods_total_safe > 0 else 0.0
            self.loading_progress_var.set(max(0.0, min(100.0, mod_ratio * 100.0)))

            total_text = str(mods_total_safe) if mods_total_safe > 0 else "?"
            self.loading_progress_text_var.set(f"Loading mods {mods_done_safe}/{total_text}")

        self.root.after(0, _update)

    def reset_loading_progress(self, text="Queued..."):
        def _update():
            self.show_loading_bar()
            self.loading_progress_var.set(0.0)
            self.loading_progress_text_var.set(text)

        self.root.after(0, _update)

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
        messagebox.showerror("Save Error", "Failed to save API key to settings.json")
        return False

    def ensure_api_key(self):
        if self.curseforge_api_key and self.curseforge_api_key != "YOUR_curseforge_api_key_HERE":
            return True

        entered_key = simpledialog.askstring(
            "CurseForge API Key",
            "Enter your CurseForge API key. It will be saved in settings.json for next launches.",
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

    def on_search_key_release(self, _event):
        if self.search_job:
            self.root.after_cancel(self.search_job)
        self.search_job = self.root.after(300, self.display_results)

    def on_page_size_change(self, _event=None):
        try:
            parsed_value = int(self.page_size_var.get())
        except (TypeError, ValueError, tk.TclError):
            self.page_size_var.set(self.page_size)
            return

        clamped = max(MIN_ROWS_PER_PAGE, min(MAX_ROWS_PER_PAGE, parsed_value))
        if clamped != self.page_size:
            self.page_size = clamped
            self.current_page = 0
            self._last_density_signature = None
            self.schedule_display_results(delay_ms=0)
        self.page_size_var.set(clamped)

    def on_page_number_change(self, _event=None):
        try:
            requested_page = int(str(self.page_number_var.get()).strip())
        except (TypeError, ValueError, tk.TclError):
            self.page_number_var.set(str(self.current_page + 1))
            return

        max_page = max(1, int(self.total_pages))
        clamped_page = max(1, min(max_page, requested_page))

        if (clamped_page - 1) != self.current_page:
            self.current_page = clamped_page - 1
            self.schedule_display_results(delay_ms=0)

        self.page_number_var.set(str(clamped_page))

    def on_root_resize(self, event):
        if event.widget is not self.root:
            return
        self.apply_responsive_layout(event.width, event.height)

    def apply_responsive_layout(self, width, height):
        if width <= 1 or height <= 1:
            return

        resize_signature = (width, height)
        if self._last_resize_signature == resize_signature:
            return
        self._last_resize_signature = resize_signature

        self.update_tree_columns()
        self.apply_table_density()

    def apply_table_density(self):
        tree_height = self.tree.winfo_height()
        if tree_height <= 1:
            return

        rows_target = max(1, int(self.page_size))
        header_height = 32
        usable_height = max(120, tree_height - header_height)
        fitted_row_height = max(22, min(BASE_ROW_HEIGHT, usable_height // rows_target))
        entry_font_size = min(BASE_ENTRY_FONT_SIZE, 11)
        while entry_font_size > 7:
            probe_font = tkfont.Font(family=APP_FONT_FAMILY, size=entry_font_size)
            min_row_for_two_lines = (probe_font.metrics("linespace") * 2) + 6
            if min_row_for_two_lines <= fitted_row_height:
                break
            entry_font_size -= 1

        entry_font_size = max(7, entry_font_size)
        heading_font_size = max(10, min(BASE_HEADING_FONT_SIZE, entry_font_size + 1))
        icon_size = max(18, min(BASE_ICON_SIZE, fitted_row_height - 8))

        density_signature = (fitted_row_height, entry_font_size, heading_font_size, icon_size)
        if self._last_density_signature == density_signature:
            return
        self._last_density_signature = density_signature

        style = ttk.Style()
        style.configure("Treeview", rowheight=fitted_row_height, font=(APP_FONT_FAMILY, entry_font_size))
        style.configure("Treeview.Heading", font=(APP_FONT_FAMILY, heading_font_size, "bold"))
        self.tree_font = tkfont.Font(family=APP_FONT_FAMILY, size=entry_font_size)

        if self.image_loader and self.image_loader.set_image_size((icon_size, icon_size)):
            self.schedule_display_results(delay_ms=0)

    def truncate_text_to_width(self, text, max_width):
        value = str(text or "")
        if not value:
            return ""

        if self.tree_font.measure(value) <= max_width:
            return value

        ellipsis = "..."
        if self.tree_font.measure(ellipsis) > max_width:
            return ""

        low = 0
        high = len(value)
        best = ""
        while low <= high:
            mid = (low + high) // 2
            candidate = value[:mid].rstrip()
            measure_text = f"{candidate}{ellipsis}" if candidate else ellipsis
            if self.tree_font.measure(measure_text) <= max_width:
                best = measure_text
                low = mid + 1
            else:
                high = mid - 1

        return best or ellipsis

    def format_authors_for_cell(self, authors_text):
        raw = str(authors_text or "").strip()
        if not raw:
            return ""

        names = [part.strip() for part in raw.split(",") if part.strip()]
        normalized = ", ".join(names) if names else raw

        max_width = max(80, int(self.tree.column("author", "width")) - 12)
        if self.tree_font.measure(normalized) <= max_width:
            return normalized

        if len(names) <= 1:
            return self.truncate_text_to_width(normalized, max_width)

        line_one_parts = []
        index = 0
        while index < len(names):
            candidate = ", ".join(line_one_parts + [names[index]])
            if self.tree_font.measure(candidate) <= max_width:
                line_one_parts.append(names[index])
                index += 1
                continue

            if not line_one_parts:
                line_one_parts.append(self.truncate_text_to_width(names[index], max_width))
                index += 1
            break

        line_one = ", ".join(line_one_parts).strip()
        line_two = ", ".join(names[index:]).strip()
        line_two = self.truncate_text_to_width(line_two, max_width)

        if not line_two:
            return line_one
        return f"{line_one}\n{line_two}"

    def update_tree_columns(self):
        tree_width = self.tree.winfo_width()
        if tree_width <= 1:
            return

        icon_width = max(52, int(tree_width * 0.08))
        remaining = max(350, tree_width - icon_width)

        name_width = max(170, int(remaining * 0.32))
        author_width = max(220, int(remaining * 0.30))
        downloads_width = max(110, int(remaining * 0.14))
        updated_width = max(180, remaining - name_width - author_width - downloads_width)

        self.tree.column("#0", width=icon_width, minwidth=52, stretch=tk.NO, anchor="center")
        self.tree.column("name", width=name_width, minwidth=180, stretch=tk.YES)
        self.tree.column("author", width=author_width, minwidth=220, stretch=tk.YES)
        self.tree.column("downloads", width=downloads_width, minwidth=100, stretch=tk.YES, anchor="center")
        self.tree.column("updated", width=updated_width, minwidth=220, stretch=tk.YES, anchor="w")

    def on_tree_motion(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id != self.current_tooltip_item:
            self.hide_tooltip()

        if self.tooltip_job:
            self.root.after_cancel(self.tooltip_job)
            self.tooltip_job = None

        if item_id:
            self.tooltip_job = self.root.after(500, self.show_tooltip, item_id, event.x_root, event.y_root)
        else:
            self.hide_tooltip()

    def on_tree_leave(self, _event):
        if self.tooltip_job:
            self.root.after_cancel(self.tooltip_job)
            self.tooltip_job = None
        self.hide_tooltip()

    def show_tooltip(self, item_id, x, y):
        self.hide_tooltip()
        mod_data = self.mods_data.get(item_id)
        if not mod_data:
            return

        tooltip_parts = []
        authors = str(mod_data.get("authors", "")).strip()
        summary = str(mod_data.get("summary", "")).strip()
        if authors:
            tooltip_parts.append(f"Author(s): {authors}")
        if summary:
            if tooltip_parts:
                tooltip_parts.append("")
            tooltip_parts.append(summary)
        if not tooltip_parts:
            return

        self.current_tooltip_item = item_id
        self.tooltip_window = tooltip = tk.Toplevel(self.root)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{x + 10}+{y + 20}")

        tk.Label(
            tooltip,
            text="\n".join(tooltip_parts),
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            wraplength=400,
            font=("Calibri", "10", "normal"),
        ).pack(ipadx=1)

    def hide_tooltip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None
        self.current_tooltip_item = None

    def get_photo_image_cached(self, url):
        if not self.image_loader:
            return None
        return self.image_loader.get_cached_image(url)

    def schedule_display_results(self, delay_ms=80):
        if self.page_change_job:
            self.root.after_cancel(self.page_change_job)
        self.page_change_job = self.root.after(delay_ms, self.display_results)

    def render_page_rows(self, page_mods, render_token):
        for mod in page_mods:
            updated = self.format_updated_value(mod.get("update_date"))
            authors_display = self.format_authors_for_cell(mod.get("authors", ""))
            values = (mod["name"], authors_display, f"{mod['downloads']:,}", updated)

            logo_url = mod.get("logo_url")
            photo = self.get_photo_image_cached(logo_url)
            if photo:
                item_id = self.tree.insert("", tk.END, text="", image=photo, values=values)
            else:
                item_id = self.tree.insert("", tk.END, text="", values=values)
                if logo_url:
                    self.image_loader.queue_image(logo_url, item_id, render_token)

            self.mods_data[item_id] = {
                "url": mod.get("url"),
                "summary": mod.get("summary", ""),
                "authors": mod.get("authors", ""),
            }

    def update_result_bars(self, page_count, total_filtered):
        mode_text = "Resource Packs" if self.mode_var.get() == RESOURCEPACKS_MODE else "Mods"

        if self.is_refresh_active:
            self.show_loading_bar()
            return

        self.show_summary_bar(
            f"Showing {page_count} of {total_filtered} {mode_text.lower()} for {self.current_version} version"
        )

    def display_results(self):
        self.page_change_job = None
        self.apply_table_density()
        self.tree.delete(*self.tree.get_children())
        self.mods_data.clear()
        render_token = self.image_loader.start_new_render_cycle() if self.image_loader else 0

        with self.lock:
            _, sorted_mods = self.get_filtered_sorted_mods()
            total_filtered = len(sorted_mods)

        if total_filtered == 0:
            self.total_pages = 1
            self.page_number_var.set("1")
            self.page_total_label.config(text="of 1")
            self.prev_btn.config(state="disabled")
            self.next_btn.config(state="disabled")
            if not self.is_refresh_active:
                self.show_summary_bar(f"Showing 0 of 0 mods for {self.current_version} version")
            return

        num_pages = (total_filtered + self.page_size - 1) // self.page_size
        self.current_page = max(0, min(self.current_page, num_pages - 1))
        self.total_pages = num_pages
        start_index = self.current_page * self.page_size
        page_mods = sorted_mods[start_index: start_index + self.page_size]

        self.render_page_rows(page_mods, render_token)

        self.page_number_var.set(str(self.current_page + 1))
        self.page_total_label.config(text=f"of {num_pages}")
        self.update_result_bars(len(page_mods), total_filtered)
        self.prev_btn.config(state="normal" if self.current_page > 0 else "disabled")
        self.next_btn.config(state="normal" if self.current_page < num_pages - 1 else "disabled")
        self.update_tree_columns()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.schedule_display_results()

    def next_page(self):
        self.current_page += 1
        self.schedule_display_results()

    def open_mod_page(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        mod_data = self.mods_data.get(selection[0])
        if mod_data and mod_data.get("url"):
            original_ld = os.environ.get("LD_LIBRARY_PATH")
            
            if "LD_LIBRARY_PATH_ORIG" in os.environ:
                os.environ["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH_ORIG"]
            elif "LD_LIBRARY_PATH" in os.environ:
                del os.environ["LD_LIBRARY_PATH"]

            try:
                webbrowser.open(mod_data["url"])
            finally:
                if original_ld is not None:
                    os.environ["LD_LIBRARY_PATH"] = original_ld
                elif "LD_LIBRARY_PATH" in os.environ:
                    del os.environ["LD_LIBRARY_PATH"]


def main():
    root = tk.Tk()
    CurseForgeModBrowser(root)
    root.mainloop()


if __name__ == "__main__":
    main()

