import argparse
import sys
from typing import Optional

from . import __version__


def parse_args(args: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="docker-pull-tar",
        description="Docker image puller - Pull image from registry and save as tar file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  docker-pull-tar -i nginx:latest
  docker-pull-tar -i alpine:latest -a arm64
  docker-pull-tar -i harbor.example.com/library/nginx:1.26.0 -u admin -p password
  docker-pull-tar -i nginx:latest -o ./downloads
  docker-pull-tar -i nginx:latest -q
        """
    )

    parser.add_argument(
        "-i", "--image",
        dest="image",
        help="Docker image name (e.g., nginx:latest or harbor.abc.com/abc/nginx:1.26.0)"
    )

    parser.add_argument(
        "-a", "--arch",
        dest="arch",
        default="amd64",
        help="Architecture, default: amd64, common: amd64, arm64, armv7, ppc64le, s390x"
    )

    parser.add_argument(
        "-r", "--custom-registry",
        dest="registry",
        help="Custom registry address (e.g., harbor.abc.com)"
    )

    parser.add_argument(
        "-u", "--username",
        dest="username",
        help="Registry username"
    )

    parser.add_argument(
        "-p", "--password",
        dest="password",
        help="Registry password"
    )

    parser.add_argument(
        "-o", "--output",
        dest="output",
        help="Output directory, default is current directory"
    )

    parser.add_argument(
        "-q", "--quiet",
        dest="quiet",
        action="store_true",
        help="Quiet mode"
    )

    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="Enable debug mode"
    )

    parser.add_argument(
        "--workers",
        dest="workers",
        type=int,
        default=4,
        help="Number of concurrent download threads, default 4"
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    return parser.parse_args(args)


def interactive_input(quiet: bool = False) -> dict:
    if quiet:
        raise ValueError("Interactive mode requires non-quiet mode")

    print("\n=== Docker Image Puller v0.0.1 ===")

    image = input("Enter Docker image name (e.g., nginx:latest): ").strip()
    if not image:
        print("Error: Image name cannot be empty")
        sys.exit(1)

    registry = input("Enter custom registry (default: https://docker-pull.ygxz.in/): ").strip()

    username = input("Enter registry username: ").strip()
    password = input("Enter registry password: ").strip()

    arch = input("Enter architecture (amd64/arm64/armv7/ppc64le/s390x, default: amd64): ").strip()
    if not arch:
        arch = "amd64"

    output = input("Enter output directory (optional): ").strip()

    return {
        "image": image,
        "registry": registry,
        "username": username,
        "password": password,
        "arch": arch,
        "output": output
    }
