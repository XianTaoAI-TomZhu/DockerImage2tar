import os
import json
import hashlib
import time
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from pathlib import Path


PROGRESS_FILE = "download_progress.json"
MAX_RETRIES = 10
INITIAL_RETRY_DELAY = 1


class DownloadManager:
    def __init__(self, output_dir: str, workers: int = 4, debug: bool = False):
        self.output_dir = output_dir
        self.workers = workers
        self.debug = debug
        self.progress_file = os.path.join(output_dir, PROGRESS_FILE)
        self.progress = self._load_progress()
        self.should_exit = False
        self.errors = []

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        self.should_exit = True
        self._save_progress()
        raise KeyboardInterrupt("Download interrupted")

    def _load_progress(self) -> Dict[str, Any]:
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_progress(self):
        with open(self.progress_file, "w") as f:
            json.dump(self.progress, f, indent=2)

    def _verify_sha256(self, file_path: str, expected_hash: str) -> bool:
        if not os.path.exists(file_path):
            return False
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        actual_hash = sha256_hash.hexdigest()
        if self.debug:
            print(f"[DEBUG] SHA256 verification: {actual_hash} == {expected_hash}")
        return actual_hash == expected_hash

    def _download_single_layer(
        self,
        layer: Dict[str, Any],
        registry_client: Any,
        retry_count: int = 0
    ) -> Optional[str]:
        if self.should_exit:
            return None

        digest = layer.get("digest", "")
        filename = layer.get("filename", digest.replace("sha256:", ""))
        expected_size = layer.get("size", 0)
        file_path = os.path.join(self.output_dir, filename)

        if digest in self.progress:
            saved_info = self.progress[digest]
            if saved_info.get("completed") and os.path.exists(file_path):
                file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                if file_size > 0 and self._verify_sha256(file_path, digest.replace("sha256:", "")):
                    if self.debug:
                        print(f"[DEBUG] Layer {filename} already downloaded and verified")
                    return file_path
                else:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    if digest in self.progress:
                        del self.progress[digest]

        if os.path.exists(file_path):
            current_size = os.path.getsize(file_path)
            if current_size > 0 and current_size >= expected_size:
                if self._verify_sha256(file_path, digest.replace("sha256:", "")):
                    self.progress[digest] = {"completed": True, "filename": filename}
                    self._save_progress()
                    return file_path
            elif current_size == 0:
                os.remove(file_path)

        if retry_count >= MAX_RETRIES:
            error_msg = f"Max retries reached for layer {filename}"
            if self.debug:
                print(f"[DEBUG] {error_msg}")
            self.errors.append(error_msg)
            return None

        try:
            if self.debug:
                print(f"[DEBUG] Downloading layer: {filename} (size: {expected_size})")

            success, error_msg = registry_client.download_layer(digest, file_path)

            if not success:
                error_msg = error_msg or "Unknown error"
                delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                print(f"  [!] Download failed for {filename}: {error_msg}, retrying in {delay}s (attempt {retry_count + 1}/{MAX_RETRIES})")
                time.sleep(delay)
                return self._download_single_layer(layer, registry_client, retry_count + 1)

            if not os.path.exists(file_path):
                delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                print(f"  [!] File not created for {filename}, retrying in {delay}s")
                time.sleep(delay)
                return self._download_single_layer(layer, registry_client, retry_count + 1)

            actual_size = os.path.getsize(file_path)
            if actual_size == 0:
                os.remove(file_path)
                delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                print(f"  [!] Empty file for {filename}, retrying in {delay}s")
                time.sleep(delay)
                return self._download_single_layer(layer, registry_client, retry_count + 1)

            if expected_size > 0 and actual_size != expected_size:
                if self.debug:
                    print(f"[DEBUG] Size mismatch: {actual_size} != {expected_size}")
                os.remove(file_path)
                delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                print(f"  [!] Size mismatch for {filename}: {actual_size} != {expected_size}, retrying")
                time.sleep(delay)
                return self._download_single_layer(layer, registry_client, retry_count + 1)

            if not self._verify_sha256(file_path, digest.replace("sha256:", "")):
                if self.debug:
                    print(f"[DEBUG] SHA256 verification failed for {filename}")
                os.remove(file_path)
                delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                print(f"  [!] SHA256 verification failed for {filename}, retrying")
                time.sleep(delay)
                return self._download_single_layer(layer, registry_client, retry_count + 1)

            self.progress[digest] = {"completed": True, "filename": filename}
            self._save_progress()
            return file_path

        except KeyboardInterrupt:
            raise
        except Exception as e:
            error_msg = str(e)
            if self.debug:
                print(f"[DEBUG] Error downloading layer: {error_msg}")
            delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
            print(f"  [!] Error downloading {filename}: {error_msg}, retrying in {delay}s")
            time.sleep(delay)
            return self._download_single_layer(layer, registry_client, retry_count + 1)

    def download_layers(
        self,
        layers: List[Dict[str, Any]],
        registry_client: Any
    ) -> List[str]:
        downloaded_files = []

        def download_task(layer):
            if self.should_exit:
                return None
            return self._download_single_layer(layer, registry_client)

        print(f"\nStarting download {len(layers)} layers...")

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(download_task, layer): layer for layer in layers}

            for future in as_completed(futures):
                if self.should_exit:
                    break
                try:
                    result = future.result()
                    layer = futures[future]
                    filename = layer.get("filename", "unknown")
                    if result and os.path.exists(result):
                        downloaded_files.append(result)
                        print(f"  [OK] {filename}")
                    else:
                        print(f"  [FAIL] {filename} - download failed")
                except Exception as e:
                    layer = futures[future]
                    filename = layer.get("filename", "unknown")
                    print(f"  [FAIL] {filename} - exception: {e}")
                    if self.debug:
                        import traceback
                        traceback.print_exc()

        self._save_progress()

        if self.errors:
            print(f"\n[!] Download completed with {len(self.errors)} errors:")
            for err in self.errors:
                print(f"  - {err}")

        if not downloaded_files:
            raise Exception("No layers were downloaded successfully!")

        print(f"\n[OK] Successfully downloaded {len(downloaded_files)}/{len(layers)} layers")
        return downloaded_files
