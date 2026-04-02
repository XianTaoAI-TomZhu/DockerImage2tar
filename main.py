import os
import sys
import signal
from typing import Optional

from docker_puller import cli
from docker_puller.registry import RegistryClient
from docker_puller.downloader import DownloadManager
from docker_puller.tar_builder import TarBuilder
from docker_puller import __version__


DEFAULT_REGISTRY = "https://docker-pull.ygxz.in/"

FALLBACK_REGISTRIES = [
    "https://docker.1panel.live/",
    "https://1ms.run/",
    "https://proxy.vvvv.ee",
    "https://docker.m.daocloud.io",
    "https://registry.cyou",
]


class DownloadProgress:
    def __init__(self):
        self.layers = []
        self.total_size = 0
        self.downloaded_size = 0

    def update(self, layer_info: dict):
        self.layers.append(layer_info)
        self.total_size += layer_info.get("size", 0)


def parse_image_name(image: str) -> tuple:
    registry = DEFAULT_REGISTRY
    repo = image
    tag = "latest"

    if "/" in image and "." not in image.split("/")[0]:
        pass
    elif "/" in image:
        parts = image.split("/", 1)
        if "." in parts[0]:
            registry = parts[0]
            if not registry.startswith("http"):
                registry = f"https://{registry}/"
            if "/" in parts[1]:
                repo_parts = parts[1].split(":")
                repo = repo_parts[0]
                tag = repo_parts[1] if len(repo_parts) > 1 else "latest"
            else:
                repo = parts[1]
        else:
            repo = image
    else:
        repo = f"library/{image}"

    if ":" in repo:
        repo, tag = repo.split(":", 1)

    return registry, repo, tag


def signal_handler(signum, frame):
    print("\n\n[!] Received interrupt signal, saving progress...")
    sys.exit(0)


def try_download(registry_url: str, repo: str, tag: str, arch: str, auth: Optional[str], output_dir: str, workers: int, debug: bool):
    client = RegistryClient(
        registry=registry_url,
        repo=repo,
        tag=tag,
        arch=arch,
        auth=auth,
        debug=debug
    )

    print(f"Fetching manifest from {registry_url}...")
    manifest = client.get_manifest()

    if debug:
        print(f"Manifest schema version: {manifest.get('schemaVersion')}")

    layers_info = client.get_layers(manifest)

    if not layers_info:
        raise Exception("No layers found in manifest!")

    download_manager = DownloadManager(
        output_dir=output_dir,
        workers=workers,
        debug=debug
    )

    downloaded_files = download_manager.download_layers(layers_info, client)

    return downloaded_files, manifest, layers_info, client


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    args = cli.parse_args()

    if not args.image and not args.quiet:
        interactive_data = cli.interactive_input(quiet=args.quiet)
        args.image = interactive_data.get("image")
        args.registry = interactive_data.get("registry") or args.registry
        args.username = interactive_data.get("username") or args.username
        args.password = interactive_data.get("password") or args.password
        args.arch = interactive_data.get("arch") or args.arch
        args.output = interactive_data.get("output") or args.output
    elif not args.image:
        print("Error: Image name is required (use -i parameter)")
        sys.exit(1)

    registry_url, repo, tag = parse_image_name(args.image)

    if args.registry:
        registry_url = args.registry
        if not registry_url.startswith("http"):
            registry_url = f"https://{registry_url}/"

    if not args.output:
        repo_safe = repo.replace("/", "_")
        args.output = repo_safe

    print(f"\nImage: {repo}")
    print(f"Tag: {tag}")
    print(f"Arch: {args.arch}")
    print(f"Output: {os.path.abspath(args.output)}")

    os.makedirs(args.output, exist_ok=True)

    auth = None
    if args.username and args.password:
        import base64
        auth = base64.b64encode(f"{args.username}:{args.password}".encode()).decode()

    registries_to_try = [registry_url] + FALLBACK_REGISTRIES if registry_url == DEFAULT_REGISTRY else [registry_url]

    downloaded_files = None
    manifest = None
    layers_info = None
    last_error = None

    for reg in registries_to_try:
        print(f"\n[Try] Registry: {reg}")
        try:
            downloaded_files, manifest, layers_info, _ = try_download(
                reg, repo, tag, args.arch, auth, args.output, args.workers, args.debug
            )
            print(f"[OK] Success with registry: {reg}")
            registry_url = reg
            break
        except Exception as e:
            last_error = e
            print(f"[FAIL] {reg}: {e}")
            continue

    if not downloaded_files:
        print("\n[Error] All registries failed!")
        print(f"Last error: {last_error}")
        sys.exit(1)

    print("\nBuilding tar file...")

    tar_builder = TarBuilder(output_dir=args.output, repo=repo, tag=tag)
    tar_path = tar_builder.build_tar(layers_info, downloaded_files, manifest)

    print(f"\nDone! Image saved as: {tar_path}")
    print(f"Import command: docker load -i {os.path.basename(tar_path)}")


if __name__ == "__main__":
    main()
