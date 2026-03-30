from calendar import monthrange
from datetime import datetime


class SortingMixin:
    def update_sort_headings(self):
        down_arrow = " ▼"
        up_arrow = " ▲"

        headings = {
            "name": "Name",
            "author": "Author",
            "downloads": "Downloads",
            "updated": "Last Updated",
        }

        for column, base_label in headings.items():
            arrow = ""
            if self.sort_column == column:
                arrow = down_arrow if self.sort_reverse else up_arrow
            self.tree.heading(column, text=f"{base_label}{arrow}")

    def on_sort_column_selected(self, column):
        if column == self.sort_column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = True
        self.update_sort_headings()
        self.current_page = 0
        self.schedule_display_results(delay_ms=0)

    def get_sort_key(self, mod):
        if self.sort_column == "name":
            return str(mod.get("name", "")).lower()
        if self.sort_column == "author":
            return str(mod.get("authors", "")).lower()
        if self.sort_column == "downloads":
            return int(mod.get("downloads", 0) or 0)
        if self.sort_column == "updated":
            return mod.get("update_date") or datetime.min
        return int(mod.get("downloads", 0) or 0)

    def format_age_counter(self, updated):
        if not updated:
            return "Unknown"

        today = datetime.now().date()
        updated_date = updated.date()
        if updated_date > today:
            updated_date = today

        years = today.year - updated_date.year
        months = today.month - updated_date.month
        days = today.day - updated_date.day

        if days < 0:
            months -= 1
            prev_month = today.month - 1
            prev_year = today.year
            if prev_month == 0:
                prev_month = 12
                prev_year -= 1
            days += monthrange(prev_year, prev_month)[1]

        if months < 0:
            years -= 1
            months += 12

        years = max(0, years)
        months = max(0, months)
        days = max(0, days)
        return f"{years}y {months}m {days}d ago"

    def format_updated_value(self, updated):
        if not updated:
            return "Unknown"
        updated_text = updated.strftime("%Y-%m-%d %H:%M")
        return f"{updated_text} | {self.format_age_counter(updated)}"

    def get_filtered_sorted_mods(self):
        raw_search = self.search_var.get().strip()
        normalized_search = raw_search.lower()
        author_prefix = "author:"

        if normalized_search.startswith(author_prefix):
            author_term = raw_search[len(author_prefix):].strip().lower()
            if author_term:
                filtered = [
                    mod
                    for mod in self.all_mods
                    if author_term in str(mod.get("authors", "")).lower()
                ]
            else:
                filtered = self.all_mods[:]
            active_search_term = author_term
        elif normalized_search:
            filtered = [
                mod
                for mod in self.all_mods
                if any(normalized_search in str(mod.get(field, "")).lower() for field in ["name", "summary", "authors"])
            ]
            active_search_term = normalized_search
        else:
            filtered = self.all_mods[:]
            active_search_term = ""

        return active_search_term, sorted(filtered, key=self.get_sort_key, reverse=self.sort_reverse)
