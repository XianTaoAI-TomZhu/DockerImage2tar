import os
import tarfile
import json
import hashlib
from typing import List, Dict, Any
from pathlib import Path


class TarBuilder:
    def __init__(self, output_dir: str, repo: str = "image", tag: str = "latest"):
        self.output_dir = output_dir
        self.repo = repo
        self.tag = tag

    def _compute_digest(self, file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def build_tar(
        self,
        layers_info: List[Dict[str, Any]],
        downloaded_files: List[str],
        manifest: Dict[str, Any]
    ) -> str:
        output_dir = self.output_dir
        if output_dir == ".":
            output_dir = os.getcwd()

        repo_name = self.repo.replace("/", "_")
        tar_filename = f"{repo_name}_{self.tag}.tar"
        tar_path = os.path.join(output_dir, tar_filename)

        manifest_json = self._create_manifest_json(layers_info, manifest)

        with tarfile.open(tar_path, "w") as tar:
            for file_path in downloaded_files:
                if os.path.exists(file_path):
                    arcname = os.path.basename(file_path)
                    tar.add(file_path, arcname=arcname)

            manifest_bytes = json.dumps(manifest_json, indent=2).encode()
            import io
            manifest_info = tarfile.TarInfo(name="manifest.json")
            manifest_info.size = len(manifest_bytes)
            tar.addfile(manifest_info, io.BytesIO(manifest_bytes))

            config_data = self._create_config_json(manifest)
            config_bytes = json.dumps(config_data, indent=2).encode()
            config_info = tarfile.TarInfo(name="config.json")
            config_info.size = len(config_bytes)
            tar.addfile(config_info, io.BytesIO(config_bytes))

        return tar_path

    def _create_manifest_json(
        self,
        layers_info: List[Dict[str, Any]],
        manifest: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        repo_tag = f"{self.repo}:{self.tag}"

        config_digest = ""
        for layer in layers_info:
            if layer.get("is_config"):
                config_digest = layer.get("digest", "").replace("sha256:", "")
                break

        manifest_list = [{
            "Config": config_digest or "config.json",
            "RepoTags": [repo_tag],
            "Layers": [layer.get("digest", "").replace("sha256:", "") for layer in layers_info if not layer.get("is_config")]
        }]

        return manifest_list

    def _create_config_json(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        config = manifest.get("config", {})

        if manifest.get("schemaVersion") == 2:
            return {
                "architecture": config.get("architecture", "amd64"),
                "os": config.get("os", "linux"),
                "config": {},
                "created": config.get("created", ""),
                "docker_version": config.get("docker_version", ""),
                "history": manifest.get("history", []),
                "rootfs": {
                    "type": "layers",
                    "diff_ids": []
                }
            }

        return {
            "architecture": "amd64",
            "os": "linux",
            "config": {}
        }
