import os
import sys
import json
import subprocess
import tempfile
import shutil
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docker_puller.registry import RegistryClient
from docker_puller.downloader import DownloadManager
from docker_puller.tar_builder import TarBuilder


TEST_REGISTRY = "https://docker-pull.ygxz.in/"


class TestReport:
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.start_time = datetime.now()

    def add_result(self, name: str, passed: bool, message: str = "", details: Any = None):
        self.results.append({
            "name": name,
            "passed": passed,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def generate_report(self) -> str:
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        passed = sum(1 for r in self.results if r["passed"])
        failed = sum(1 for r in self.results if not r["passed"])
        total = len(self.results)

        report = []
        report.append("=" * 60)
        report.append("Docker Image Puller - Test Report")
        report.append("=" * 60)
        report.append(f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Duration: {duration:.2f} seconds")
        report.append("")
        report.append(f"Total Tests: {total}")
        report.append(f"Passed: {passed}")
        report.append(f"Failed: {failed}")
        report.append(f"Success Rate: {passed/total*100:.1f}%" if total > 0 else "N/A")
        report.append("")
        report.append("=" * 60)
        report.append("Test Results")
        report.append("=" * 60)

        for i, result in enumerate(self.results, 1):
            status = "[PASS]" if result["passed"] else "[FAIL]"
            report.append(f"\n{i}. {result['name']} {status}")
            if result["message"]:
                report.append(f"   Message: {result['message']}")
            if result["details"] and isinstance(result["details"], dict):
                for key, value in result["details"].items():
                    report.append(f"   {key}: {value}")

        report.append("")
        report.append("=" * 60)

        return "\n".join(report)

    def save_report(self, filename: str = "test_report.txt"):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        txt_path = os.path.join(script_dir, filename.replace(".txt", ""))
        if not txt_path.endswith(".txt"):
            txt_path = txt_path + ".txt"

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(self.generate_report())

        json_path = txt_path.replace(".txt", ".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "start_time": self.start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "results": self.results,
                "summary": {
                    "total": len(self.results),
                    "passed": sum(1 for r in self.results if r["passed"]),
                    "failed": sum(1 for r in self.results if not r["passed"])
                }
            }, f, indent=2, ensure_ascii=False)

        return txt_path, json_path


def test_registry_client_init():
    report = TestReport()

    try:
        client = RegistryClient(
            registry=TEST_REGISTRY,
            repo="library/ubuntu",
            tag="latest",
            arch="amd64",
            debug=False
        )
        report.add_result(
            "RegistryClient initialization",
            True,
            "Client created successfully",
            {"registry": TEST_REGISTRY, "repo": "library/ubuntu", "tag": "latest"}
        )
    except Exception as e:
        report.add_result("RegistryClient initialization", False, str(e))

    return report


def test_parse_image_name():
    from main import parse_image_name
    report = TestReport()

    test_cases = [
        ("nginx:latest", "https://docker-pull.ygxz.in/", "library/nginx", "latest"),
        ("alpine:latest", "https://docker-pull.ygxz.in/", "library/alpine", "latest"),
        ("nginx", "https://docker-pull.ygxz.in/", "library/nginx", "latest"),
        ("myregistry.com/nginx:v1.0", "https://myregistry.com/", "nginx", "v1.0"),
    ]

    for image, expected_registry, expected_repo, expected_tag in test_cases:
        registry, repo, tag = parse_image_name(image)
        passed = (registry == expected_registry and repo == expected_repo and tag == expected_tag)
        report.add_result(
            f"parse_image_name: {image}",
            passed,
            f"registry={registry}, repo={repo}, tag={tag}" if not passed else "OK",
            {"expected": (expected_registry, expected_repo, expected_tag), "actual": (registry, repo, tag)}
        )

    return report


def test_get_manifest():
    report = TestReport()

    try:
        client = RegistryClient(
            registry=TEST_REGISTRY,
            repo="library/alpine",
            tag="latest",
            arch="amd64"
        )
        manifest = client.get_manifest()
        schema_version = manifest.get("schemaVersion")

        if schema_version == 2:
            report.add_result(
                "Get manifest (alpine:latest)",
                True,
                "Manifest fetched successfully",
                {"schemaVersion": schema_version}
            )
        else:
            report.add_result(
                "Get manifest (alpine:latest)",
                False,
                f"Unexpected schema version: {schema_version}",
                {"schemaVersion": schema_version}
            )
    except Exception as e:
        report.add_result("Get manifest (alpine:latest)", False, str(e))

    return report


def test_get_layers():
    report = TestReport()

    try:
        client = RegistryClient(
            registry=TEST_REGISTRY,
            repo="library/alpine",
            tag="latest",
            arch="amd64"
        )
        manifest = client.get_manifest()
        layers = client.get_layers(manifest)

        if len(layers) > 0:
            report.add_result(
                "Get layers (alpine:latest)",
                True,
                f"Found {len(layers)} layers",
                {"layer_count": len(layers)}
            )
        else:
            report.add_result(
                "Get layers (alpine:latest)",
                False,
                "No layers found",
                {"layers": layers}
            )
    except Exception as e:
        report.add_result("Get layers (alpine:latest)", False, str(e))

    return report


def test_download_and_build_tar():
    report = TestReport()
    temp_dir = None

    try:
        temp_dir = tempfile.mkdtemp()
        image_name = "alpine"
        repo = f"library/{image_name}"
        tag = "latest"

        client = RegistryClient(
            registry=TEST_REGISTRY,
            repo=repo,
            tag=tag,
            arch="amd64"
        )

        manifest = client.get_manifest()
        layers = client.get_layers(manifest)

        if not layers:
            report.add_result("Download and build tar", False, "No layers found")
            return report

        download_manager = DownloadManager(output_dir=temp_dir, workers=2)
        downloaded_files = download_manager.download_layers(layers, client)

        if not downloaded_files:
            report.add_result("Download and build tar", False, "No files downloaded")
            return report

        tar_builder = TarBuilder(output_dir=temp_dir, repo=repo, tag=tag)
        tar_path = tar_builder.build_tar(layers, downloaded_files, manifest)

        tar_exists = os.path.exists(tar_path)
        tar_size = os.path.getsize(tar_path) if tar_exists else 0

        if tar_exists and tar_size > 0:
            report.add_result(
                "Download and build tar",
                True,
                f"Tar file created: {tar_size} bytes",
                {"tar_path": tar_path, "tar_size": tar_size, "layers_downloaded": len(downloaded_files)}
            )
        else:
            report.add_result(
                "Download and build tar",
                False,
                f"Tar file not created or empty",
                {"tar_exists": tar_exists, "tar_size": tar_size}
            )

    except Exception as e:
        report.add_result("Download and build tar", False, str(e))

    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    return report


def test_fallback_registries():
    from main import FALLBACK_REGISTRIES
    report = TestReport()

    report.add_result(
        "Fallback registries defined",
        True,
        f"Found {len(FALLBACK_REGISTRIES)} fallback registries",
        {"registries": FALLBACK_REGISTRIES}
    )

    return report


def test_multi_arch_detection():
    report = TestReport()

    try:
        client = RegistryClient(
            registry=TEST_REGISTRY,
            repo="library/ubuntu",
            tag="latest",
            arch="amd64"
        )
        client.session.headers.update({
            "Accept": "application/vnd.docker.distribution.manifest.list.v2+json, */*"
        })
        manifest_list = client.get_manifest_list()

        if len(manifest_list) > 0:
            report.add_result(
                "Multi-arch manifest detection",
                True,
                f"Found {len(manifest_list)} architecture variants",
                {"manifest_count": len(manifest_list)}
            )
        else:
            report.add_result(
                "Multi-arch manifest detection",
                False,
                "No manifest list found"
            )
    except Exception as e:
        report.add_result("Multi-arch manifest detection", False, str(e))

    return report


def test_command_line_help():
    report = TestReport()
    test_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        result = subprocess.run(
            [sys.executable, "main.py", "-h"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=test_dir
        )

        if result.returncode == 0 and "docker-pull-tar" in result.stdout:
            report.add_result(
                "Command line help",
                True,
                "Help message displayed successfully"
            )
        else:
            report.add_result(
                "Command line help",
                False,
                f"Exit code: {result.returncode}",
                {"stdout": result.stdout[:200], "stderr": result.stderr[:200]}
            )
    except Exception as e:
        report.add_result("Command line help", False, str(e))

    return report


def test_version():
    report = TestReport()
    test_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        result = subprocess.run(
            [sys.executable, "main.py", "-v"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=test_dir
        )

        if result.returncode == 0:
            report.add_result(
                "Version command",
                True,
                f"Version: {result.stdout.strip()}"
            )
        else:
            report.add_result("Version command", False, result.stderr)
    except Exception as e:
        report.add_result("Version command", False, str(e))

    return report


def run_all_tests():
    print("Running tests...")
    print("")

    all_reports = []

    all_reports.append(test_registry_client_init())
    all_reports.append(test_parse_image_name())
    all_reports.append(test_get_manifest())
    all_reports.append(test_get_layers())
    all_reports.append(test_multi_arch_detection())
    all_reports.append(test_fallback_registries())
    all_reports.append(test_command_line_help())
    all_reports.append(test_version())

    combined_report = TestReport()
    for report in all_reports:
        combined_report.results.extend(report.results)

    return combined_report


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    report = run_all_tests()

    print(report.generate_report())

    txt_file, json_file = report.save_report("test_report.txt")
    print(f"\nReports saved to:")
    print(f"  - {txt_file}")
    print(f"  - {json_file}")
