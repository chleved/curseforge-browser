import tkinter as tk
from tkinter import ttk

from constants import (
    APP_FONT_FAMILY,
    BASE_ENTRY_FONT_SIZE,
    BASE_HEADING_FONT_SIZE,
    BASE_ROW_HEIGHT,
    CURSEFORGE_USER_AGENT,
    IMAGE_SIZE,
    MAX_ROWS_PER_PAGE,
    MIN_ROWS_PER_PAGE,
    MODS_MODE,
    MOD_LOADER_LABELS,
    RESOURCEPACKS_MODE,
)
from image_loader import AsyncImageLoader


class UILayoutMixin:
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

        self.prev_btn = ttk.Button(nav_bottom_row, text="<- Previous", command=self.prev_page)
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

        self.next_btn = ttk.Button(nav_bottom_row, text="Next ->", command=self.next_page)
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
