import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from constants import (
    APP_FONT_FAMILY,
    BASE_ENTRY_FONT_SIZE,
    BASE_HEADING_FONT_SIZE,
    BASE_ICON_SIZE,
    BASE_ROW_HEIGHT,
    MAX_ROWS_PER_PAGE,
    MIN_ROWS_PER_PAGE,
)


class UISetupMixin:
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
