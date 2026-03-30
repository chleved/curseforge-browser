import queue
from tkinter import messagebox

from curseforge_client import RequestCancelledError


DEFAULT_CLASS_ID = 6
MODS_MODE = "mods"
RESOURCEPACKS_MODE = "resourcepacks"
PROGRESSIVE_DATE_CHUNK_SIZE = 200


class RefreshMixin:
    def queue_refresh(self, reason):
        self.is_refresh_active = True
        self.reset_loading_progress(f"Queued: {reason}")
        mode = self.mode_var.get()
        version = self.current_version
        loader_type = self.current_loader_type
        with self.refresh_lock:
            self.refresh_request_counter += 1
            refresh_id = self.refresh_request_counter
            self.active_refresh_id = refresh_id

        while True:
            try:
                self.refresh_queue.get_nowait()
            except queue.Empty:
                break

        self.refresh_queue.put(
            {"id": refresh_id, "mode": mode, "version": version, "loader_type": loader_type, "reason": reason}
        )

    def is_refresh_cancelled(self, refresh_id):
        with self.refresh_lock:
            return refresh_id != self.active_refresh_id

    def _cancel_checker(self, refresh_id):
        return lambda: self.is_refresh_cancelled(refresh_id)

    def run_refresh_queue_worker(self):
        while True:
            request = self.refresh_queue.get()
            while True:
                try:
                    request = self.refresh_queue.get_nowait()
                except queue.Empty:
                    break
            self.process_refresh_request(request)

    def _show_refresh_error(self, refresh_id, title, message):
        if self.is_refresh_cancelled(refresh_id):
            return
        self.is_refresh_active = False
        self.reset_loading_progress("Failed")
        self.root.after(0, lambda: self.show_summary_bar("Refresh failed. Check the error dialog."))
        self.root.after(0, lambda m=message, t=title: messagebox.showerror(t, m))

    def _load_cache_for_request(self, mode, version, loader_type, refresh_id):
        if self.is_refresh_cancelled(refresh_id):
            return None
        cache_file = self.storage.get_cache_file(mode, version, loader_type)
        self.cache_file = cache_file
        self.current_page = 0
        self.set_status("Switching filters... loading cache...")
        self.load_cache_with_progress(cache_file, refresh_id)
        if self.is_refresh_cancelled(refresh_id):
            return None
        return cache_file

    def _build_params_for_request(self, mode, version, loader_type, refresh_id):
        params = self.params.copy()
        params["gameVersion"] = version

        if mode == MODS_MODE:
            if int(loader_type) > 0:
                params["modLoaderType"] = int(loader_type)
            else:
                params.pop("modLoaderType", None)
            params["classId"] = DEFAULT_CLASS_ID
            return params

        params.pop("modLoaderType", None)

        self.set_status("Finding resource-pack category class...")
        class_id, class_name = self.client.find_resource_pack_class(
            params["gameId"],
            status_callback=self.set_status,
            should_cancel=self._cancel_checker(refresh_id),
        )
        if class_id:
            params["classId"] = class_id
            self.set_status(f"Found class '{class_name}' (id={class_id}). Fetching resource packs...")
        else:
            params.pop("classId", None)
            self.set_status("Could not find a resource-pack class; searching without class filter.")

        return params

    def _fetch_mods_for_request(self, mode, params, refresh_id):
        mode_text = "resource packs" if mode == RESOURCEPACKS_MODE else "mods"
        cancel_checker = self._cancel_checker(refresh_id)
        pending_chunk = []
        fetched_with_dates = []
        progress_state = {
            "mods_done": 0,
            "mods_total_hint": 0,
        }

        for page_results, total in self.client.iter_mod_pages(
            params,
            mode_text=mode_text,
            status_callback=self.set_status,
            should_cancel=cancel_checker,
        ):
            if page_results:
                pending_chunk.extend(page_results)

            progress_state["mods_done"] += len(page_results)
            if total:
                progress_state["mods_total_hint"] = max(progress_state["mods_total_hint"], int(total))
            self.set_loading_progress(
                progress_state["mods_done"],
                progress_state["mods_total_hint"],
            )

            if len(pending_chunk) >= PROGRESSIVE_DATE_CHUNK_SIZE:
                self._flush_progressive_chunk(
                    pending_chunk,
                    fetched_with_dates,
                    refresh_id,
                    cancel_checker,
                )
                pending_chunk = []

        if pending_chunk:
            self._flush_progressive_chunk(
                pending_chunk,
                fetched_with_dates,
                refresh_id,
                cancel_checker,
            )

        return fetched_with_dates

    def _flush_progressive_chunk(self, chunk_mods, fetched_with_dates, refresh_id, cancel_checker):
        self.client.fetch_file_dates(
            chunk_mods,
            status_callback=self.set_status,
            should_cancel=cancel_checker,
        )
        fetched_with_dates.extend(chunk_mods)
        self._publish_partial_results(refresh_id, fetched_with_dates)

    def _publish_partial_results(self, refresh_id, partial_mods):
        if self.is_refresh_cancelled(refresh_id):
            return

        with self.lock:
            self.all_mods = list(partial_mods)

        if self.is_refresh_cancelled(refresh_id):
            return

        self.set_status(f"Displaying partial results: {len(partial_mods)} fetched so far...")
        self.root.after(0, lambda: self.schedule_display_results(delay_ms=0))

    def _apply_refresh_result(self, cache_file, new_mods_list, refresh_id):
        if self.is_refresh_cancelled(refresh_id):
            return

        with self.lock:
            self.all_mods = new_mods_list
            cache_data = list(self.all_mods)

        self.storage.save_cache(cache_file, cache_data)
        if self.is_refresh_cancelled(refresh_id):
            return

        self.set_loading_progress(len(new_mods_list), len(new_mods_list), finished=True)
        self.is_refresh_active = False
        self.set_status("Update complete! Displaying fresh data.")
        self.root.after(0, self.display_results)

    def process_refresh_request(self, request):
        refresh_id = request["id"]
        mode = request["mode"]
        version = request["version"]
        loader_type = request.get("loader_type", 0)

        cache_file = self._load_cache_for_request(mode, version, loader_type, refresh_id)
        if not cache_file:
            return

        try:
            params = self._build_params_for_request(mode, version, loader_type, refresh_id)
            new_mods_list = self._fetch_mods_for_request(mode, params, refresh_id)
        except RequestCancelledError:
            return
        except RuntimeError as error:
            self._show_refresh_error(refresh_id, "API Error", str(error))
            return
        except Exception as error:
            self._show_refresh_error(refresh_id, "Connection Error", f"Failed to connect: {error}")
            return

        self._apply_refresh_result(cache_file, new_mods_list, refresh_id)

    def load_cache_with_progress(self, cache_file, refresh_id=None):
        cache_data = self.storage.load_cache(
            cache_file,
            progress_callback=lambda p: self.set_status(f"Loading from cache... {p:.0f}%"),
        )
        if refresh_id is not None and self.is_refresh_cancelled(refresh_id):
            return
        with self.lock:
            self.all_mods = cache_data
        self.root.after(0, self.display_results)

    def on_mode_change(self):
        self.queue_refresh("mode change")
