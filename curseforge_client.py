import time

import requests

from curseforge_parsing import build_mod_dict, find_resource_pack_class, parse_file_date


JSON_MIME_TYPE = "application/json"
RATE_LIMIT_WAIT_SECONDS = 60
FETCH_DELAY_SECONDS = 0.1
SEARCH_INDEX_LIMIT = 9950


class RequestCancelledError(RuntimeError):
    pass


class CurseForgeClient:
    def __init__(self, api_key, base_url="https://api.curseforge.com/v1"):
        self.api_key = api_key
        self.base_url = base_url

    def set_api_key(self, api_key):
        self.api_key = api_key

    def build_headers(self, include_content_type=False):
        headers = {"Accept": JSON_MIME_TYPE, "x-api-key": self.api_key}
        if include_content_type:
            headers["Content-Type"] = JSON_MIME_TYPE
        return headers

    def find_resource_pack_class(self, game_id, status_callback=None, should_cancel=None):
        self._raise_if_cancelled(should_cancel)
        response = requests.get(
            f"{self.base_url}/categories",
            headers=self.build_headers(),
            params={"gameId": game_id, "classesOnly": True},
            timeout=15,
        )
        self._raise_if_cancelled(should_cancel)

        if response.status_code == 429:
            self._set_status(status_callback, "Rate limit hit while fetching categories. Waiting...")
            self._sleep_with_cancel(RATE_LIMIT_WAIT_SECONDS, should_cancel)
            self._raise_if_cancelled(should_cancel)
            return None, None

        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch categories: {response.status_code}\n{response.text}")

        classes = response.json().get("data", []) or []
        found_class = find_resource_pack_class(classes)
        if not found_class:
            return None, None

        return found_class.get("id"), found_class.get("name")

    def get_minecraft_versions(self, sort_descending=True, status_callback=None):
        response = requests.get(
            f"{self.base_url}/minecraft/version",
            headers=self.build_headers(),
            params={"sortDescending": sort_descending},
            timeout=20,
        )

        if response.status_code == 429:
            self._set_status(status_callback, "Rate limit hit while fetching versions. Waiting...")
            self._sleep_with_cancel(RATE_LIMIT_WAIT_SECONDS)
            response = requests.get(
                f"{self.base_url}/minecraft/version",
                headers=self.build_headers(),
                params={"sortDescending": sort_descending},
                timeout=20,
            )

        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch Minecraft versions: {response.status_code}\n{response.text}")

        versions = []
        seen = set()
        for item in response.json().get("data", []):
            version = str(item.get("versionString", "")).strip()
            if version and version not in seen:
                seen.add(version)
                versions.append(version)
        return versions

    def get_minecraft_modloaders(self, version=None, include_all=False, status_callback=None):
        params = {"includeAll": bool(include_all)}
        if version:
            params["version"] = str(version).strip()

        response = requests.get(
            f"{self.base_url}/minecraft/modloader",
            headers=self.build_headers(),
            params=params,
            timeout=20,
        )

        if response.status_code == 429:
            self._set_status(status_callback, "Rate limit hit while fetching modloaders. Waiting...")
            self._sleep_with_cancel(RATE_LIMIT_WAIT_SECONDS)
            response = requests.get(
                f"{self.base_url}/minecraft/modloader",
                headers=self.build_headers(),
                params=params,
                timeout=20,
            )

        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch Minecraft modloaders: {response.status_code}\n{response.text}")

        return response.json().get("data", []) or []

    def iter_mod_pages(self, params, mode_text, status_callback=None, should_cancel=None):
        page_size = params.get("pageSize", 50)
        target_version = str(params.get("gameVersion", "")).strip()
        target_mod_loader = params.get("modLoaderType")
        index = 0
        fetched_count = 0

        while True:
            self._raise_if_cancelled(should_cancel)
            query_params = params.copy()
            query_params["index"] = index

            response = requests.get(
                f"{self.base_url}/mods/search",
                headers=self.build_headers(),
                params=query_params,
                timeout=20,
            )
            self._raise_if_cancelled(should_cancel)

            if response.status_code == 429:
                self._set_status(status_callback, "Rate limit hit. Waiting 60s...")
                self._sleep_with_cancel(RATE_LIMIT_WAIT_SECONDS, should_cancel)
                self._raise_if_cancelled(should_cancel)
                continue

            if response.status_code != 200:
                raise RuntimeError(f"Search failed: {response.status_code}\n{response.text}")

            payload = response.json()
            pagination = payload.get("pagination") or {}
            total = pagination.get("totalCount", 0)
            page_results = []

            for mod in payload.get("data", []):
                mod_dict = build_mod_dict(mod, target_version, target_mod_loader)
                if mod_dict["fileId"]:
                    page_results.append(mod_dict)

            fetched_count += len(page_results)

            self._set_status(status_callback, f"Loading {mode_text}: {fetched_count} / {total}")
            yield page_results, total

            if not total or index + page_size >= total or index >= SEARCH_INDEX_LIMIT:
                break

            index += page_size
            self._sleep_with_cancel(FETCH_DELAY_SECONDS, should_cancel)
            self._raise_if_cancelled(should_cancel)

    def fetch_mods(self, params, mode_text, status_callback=None, should_cancel=None):
        results = []
        for page_results, _ in self.iter_mod_pages(
            params,
            mode_text=mode_text,
            status_callback=status_callback,
            should_cancel=should_cancel,
        ):
            results.extend(page_results)
        return results

    def fetch_file_dates(self, mods_list, status_callback=None, should_cancel=None, progress_callback=None):
        file_id_map = {mod["fileId"]: mod for mod in mods_list if mod.get("fileId")}
        if not file_id_map:
            if progress_callback:
                progress_callback(0, 0)
            return

        file_ids = list(file_id_map.keys())
        batch_size = 50
        total_batches = (len(file_ids) + batch_size - 1) // batch_size

        for offset in range(0, len(file_ids), batch_size):
            self._raise_if_cancelled(should_cancel)
            batch = file_ids[offset: offset + batch_size]
            response = requests.post(
                f"{self.base_url}/mods/files",
                headers=self.build_headers(include_content_type=True),
                json={"fileIds": batch},
                timeout=20,
            )
            self._raise_if_cancelled(should_cancel)

            if response.status_code == 429:
                self._set_status(status_callback, "Rate limit hit while fetching file dates. Waiting...")
                self._sleep_with_cancel(RATE_LIMIT_WAIT_SECONDS, should_cancel)
                self._raise_if_cancelled(should_cancel)
                continue

            if response.status_code != 200:
                raise RuntimeError(f"Failed to fetch file dates: {response.status_code}\n{response.text}")

            for file_data in response.json().get("data", []):
                file_id = file_data.get("id")
                if file_id in file_id_map:
                    file_id_map[file_id]["update_date"] = parse_file_date(file_data.get("fileDate", ""))

            current_batch = (offset // batch_size) + 1
            self._set_status(status_callback, f"Loading file metadata: batch {current_batch}/{total_batches}")
            if progress_callback:
                processed = min(offset + batch_size, len(file_ids))
                progress_callback(processed, len(file_ids))
            self._sleep_with_cancel(FETCH_DELAY_SECONDS, should_cancel)
            self._raise_if_cancelled(should_cancel)

    def _set_status(self, status_callback, message):
        if status_callback:
            status_callback(message)

    def _raise_if_cancelled(self, should_cancel):
        if should_cancel and should_cancel():
            raise RequestCancelledError("Request cancelled")

    def _sleep_with_cancel(self, seconds, should_cancel=None):
        if seconds <= 0:
            return
        step = 0.2
        slept = 0.0
        while slept < seconds:
            self._raise_if_cancelled(should_cancel)
            chunk = min(step, seconds - slept)
            time.sleep(chunk)
            slept += chunk
