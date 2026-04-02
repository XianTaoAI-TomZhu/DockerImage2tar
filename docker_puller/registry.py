import json
import base64
import requests
from typing import Optional, Dict, List, Any
from urllib.parse import urljoin, urlparse


class RegistryClient:
    BASE_API_VERSION = "v2"

    def __init__(
        self,
        registry: str,
        repo: str,
        tag: str,
        arch: str = "amd64",
        auth: Optional[str] = None,
        debug: bool = False
    ):
        self.registry = registry if registry.startswith("http") else f"https://{registry}"
        self.repo = repo
        self.tag = tag
        self.arch = arch
        self.auth = auth
        self.debug = debug

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, */*"
        })
        if self.auth:
            self.session.headers.update({"Authorization": f"Basic {self.auth}"})

        self._token = None

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = urljoin(self.registry, path)
        if self.debug:
            print(f"[DEBUG] {method} {url}")
        response = self.session.request(method, url, **kwargs)
        if self.debug:
            print(f"[DEBUG] Status: {response.status_code}")
        return response

    def _get_auth_token(self, realm: str, service: Optional[str] = None, scope: Optional[str] = None) -> Optional[str]:
        params = {}
        if service:
            params["service"] = service
        if scope:
            params["scope"] = scope

        headers = {}
        if self.auth:
            headers["Authorization"] = f"Basic {self.auth}"

        if self.debug:
            print(f"[DEBUG] Getting token from: {realm}")
            print(f"[DEBUG] Token params: {params}")

        response = self._request("GET", realm, params=params, headers=headers)
        if response.status_code == 200:
            token_data = response.json()
            return token_data.get("token")
        elif response.status_code == 401:
            pass
        return None

    def check_api_version(self) -> bool:
        response = self._request("GET", f"/{self.BASE_API_VERSION}/")
        return response.status_code == 200

    def _get_token_if_needed(self, response: requests.Response) -> bool:
        if response.status_code == 401:
            auth_info = self._parse_auth_header(response.headers.get("WWW-Authenticate", ""))
            if auth_info:
                realm = auth_info.get("realm")
                service = auth_info.get("service")
                scope = auth_info.get("scope", f"repository:{self.repo}:pull")

                if realm:
                    token = self._get_auth_token(realm, service, scope)
                    if token:
                        self._token = token
                        self.session.headers.update({"Authorization": f"Bearer {token}"})
                        return True
        return False

    def get_manifest(self, reference: Optional[str] = None) -> Dict[str, Any]:
        ref = reference or self.tag
        url = f"/{self.BASE_API_VERSION}/{self.repo}/manifests/{ref}"

        if self._token:
            self.session.headers.update({"Authorization": f"Bearer {self._token}"})

        response = self._request("GET", url)

        if self._get_token_if_needed(response):
            response = self._request("GET", url)

        if response.status_code == 200:
            manifest = response.json()
            media_type = response.headers.get("Content-Type", "")

            if "manifest.list" in media_type or manifest.get("schemaVersion") == 2 and "manifests" in manifest:
                if self.debug:
                    print(f"[DEBUG] Got manifest list, looking for arch: {self.arch}")
                return self._get_arch_manifest(manifest)

            return manifest
        else:
            raise Exception(f"Failed to get manifest: {response.status_code} - {response.text}")

    def _get_arch_manifest(self, manifest_list: Dict[str, Any]) -> Dict[str, Any]:
        manifests = manifest_list.get("manifests", [])

        target_digest = None
        for m in manifests:
            platform = m.get("platform", {})
            arch = platform.get("architecture", "")
            variant = platform.get("variant", "")

            if arch == self.arch or (self.arch == "arm64" and arch == "arm" and variant == "v8"):
                target_digest = m.get("digest")
                if self.debug:
                    print(f"[DEBUG] Found matching manifest for {self.arch}: {target_digest}")
                break

        if not target_digest:
            for m in manifests:
                platform = m.get("platform", {})
                arch = platform.get("architecture", "unknown")
                if arch != "unknown":
                    target_digest = m.get("digest")
                    if self.debug:
                        print(f"[DEBUG] Using first available arch: {arch}")
                    break

        if not target_digest:
            raise Exception(f"No manifest found for architecture: {self.arch}")

        return self.get_manifest(target_digest)

    def get_manifest_list(self) -> List[Dict[str, Any]]:
        url = f"/{self.BASE_API_VERSION}/{self.repo}/manifests/{self.tag}"
        self.session.headers.update({
            "Accept": "application/vnd.docker.distribution.manifest.list.v2+json, */*"
        })

        if self._token:
            self.session.headers.update({"Authorization": f"Bearer {self._token}"})

        response = self._request("GET", url)

        if self._get_token_if_needed(response):
            response = self._request("GET", url)

        if response.status_code == 200:
            return response.json().get("manifests", [])
        return []

    def get_available_archs(self) -> List[str]:
        manifest_list = self.get_manifest_list()
        if manifest_list:
            archs = []
            for m in manifest_list:
                arch = m.get("platform", {}).get("architecture")
                if arch and arch != "unknown":
                    archs.append(arch)
            return archs
        return [self.arch]

    def get_layers(self, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
        layers = []
        schema_version = manifest.get("schemaVersion", 0)

        if schema_version == 2:
            for layer in manifest.get("layers", []):
                layers.append({
                    "digest": layer.get("digest"),
                    "size": layer.get("size"),
                    "mediaType": layer.get("mediaType"),
                    "filename": layer.get("digest").replace("sha256:", "")
                })
        elif schema_version == 1:
            for fs_layer in manifest.get("fsLayers", []):
                blob_sum = fs_layer.get("blobSum")
                layers.append({
                    "digest": blob_sum,
                    "size": 0,
                    "filename": blob_sum.replace("sha256:", "")
                })

        config = manifest.get("config", {})
        if config:
            layers.insert(0, {
                "digest": config.get("digest"),
                "size": config.get("size"),
                "mediaType": config.get("mediaType"),
                "filename": config.get("digest", "").replace("sha256:", ""),
                "is_config": True
            })

        return layers

    def get_layer_url(self, digest: str) -> str:
        return f"/{self.BASE_API_VERSION}/{self.repo}/blobs/{digest}"

    def download_layer(self, digest: str, output_path: str) -> tuple:
        url = self.get_layer_url(digest)

        if self._token:
            self.session.headers.update({"Authorization": f"Bearer {self._token}"})

        response = self._request("GET", url, stream=True)

        if self._get_token_if_needed(response):
            response = self._request("GET", url, stream=True)

        if response.status_code == 200:
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return (True, None)
        error_msg = f"HTTP {response.status_code}"
        try:
            error_data = response.json()
            error_msg = error_data.get("errors", [{}])[0].get("message", error_msg)
        except:
            pass
        return (False, error_msg)

    def _parse_auth_header(self, auth_header: str) -> Optional[Dict[str, str]]:
        if not auth_header:
            return None
        parts = auth_header.split()
        if len(parts) < 2:
            return None
        auth_type = parts[0]
        if auth_type.lower() != "basic" and auth_type.lower() != "bearer":
            return None
        params = {}
        for param in parts[1].split(","):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key] = value.strip('"')
        return {"type": auth_type, **params}

    def get_config(self, manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if manifest.get("schemaVersion") == 2:
            config_digest = manifest.get("config", {}).get("digest")
            if config_digest:
                url = self.get_layer_url(config_digest)
                if self._token:
                    self.session.headers.update({"Authorization": f"Bearer {self._token}"})
                response = self._request("GET", url)
                if response.status_code == 200:
                    return response.json()
        return None
