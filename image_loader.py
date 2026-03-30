import io
import threading
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image, ImageTk


class AsyncImageLoader:
    def __init__(self, root, tree, user_agent, image_size=(40, 40), max_workers=4):
        self.root = root
        self.tree = tree
        self.image_size = image_size
        self.headers = {"User-Agent": user_agent}

        self._cache = {}
        self._raw_cache = {}
        self._references = []
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._render_token = 0
        self._inflight = set()

    def set_image_size(self, image_size):
        width = max(16, int(image_size[0]))
        height = max(16, int(image_size[1]))
        new_size = (width, height)
        with self._lock:
            if new_size == self.image_size:
                return False
            self.image_size = new_size
            self._cache = {}
            self._references = []
        return True

    def start_new_render_cycle(self):
        with self._lock:
            self._render_token += 1
            return self._render_token

    def get_cached_image(self, url):
        if not url:
            return None
        return self._cache.get(url)

    def queue_image(self, url, item_id, render_token):
        if not url:
            return

        raw_bytes = None
        with self._lock:
            if url in self._cache:
                return

            raw_bytes = self._raw_cache.get(url)

            key = (url, render_token)
            if raw_bytes is None:
                if key in self._inflight:
                    return
                self._inflight.add(key)

        if raw_bytes is not None:
            self.root.after(0, self._apply_image, raw_bytes, url, item_id, render_token)
            return

        self._executor.submit(self._load_image, url, item_id, render_token)

    def _is_stale(self, render_token):
        with self._lock:
            return render_token != self._render_token

    def _clear_inflight(self, url, render_token):
        with self._lock:
            self._inflight.discard((url, render_token))

    def _load_image(self, url, item_id, render_token):
        try:
            if self._is_stale(render_token):
                return

            response = requests.get(url, timeout=10, headers=self.headers)
            response.raise_for_status()

            if self._is_stale(render_token):
                return

            self.root.after(0, self._apply_image, response.content, url, item_id, render_token)
        except Exception as error:
            print(f"Error loading image {url}: {error}")
        finally:
            self._clear_inflight(url, render_token)

    def _apply_image(self, img_data, url, item_id, render_token):
        if self._is_stale(render_token):
            return
        try:
            with self._lock:
                current_size = self.image_size

            image = Image.open(io.BytesIO(img_data)).resize(current_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            with self._lock:
                self._raw_cache[url] = img_data
                self._cache[url] = photo
                self._references.append(photo)

            if self.tree.exists(item_id):
                self.tree.item(item_id, image=photo)
        except Exception as error:
            print(f"Error setting image: {error}")
