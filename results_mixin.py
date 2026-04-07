import os
import tkinter as tk
import webbrowser

from constants import RESOURCEPACKS_MODE


class ResultsMixin:
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
