import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from packaging.version import Version, InvalidVersion


JAVA_VERSION_MAP = {
    "legacy": (8, 17),
    "modern": (17, 21),
    "latest": (21, 22),
}

MC_JAVA_REQUIREMENTS = [
    (Version("1.21.5"), Version("21")),
    (Version("1.20.5"), Version("21")),
    (Version("1.17"), Version("17")),
    (Version("1.8"), Version("8")),
]


def get_java_for_mc_version(mc_version: str) -> int:
    try:
        mv = Version(mc_version)
        for mc_ver, java_ver in sorted(MC_JAVA_REQUIREMENTS, reverse=True):
            if mv >= mc_ver:
                return int(java_ver.base_version)
    except InvalidVersion:
        pass
    return 17


def scan_java_installations() -> list[dict]:
    found = []

    env_vars = ["JAVA_HOME", "JAVA8_HOME", "JAVA17_HOME", "JAVA21_HOME"]
    for var in env_vars:
        path = os.environ.get(var, "")
        if path:
            exe = _java_exe(path)
            if exe and os.path.exists(exe):
                info = _get_java_info(exe)
                if info:
                    info["source"] = f"${var}"
                    found.append(info)

    if platform.system() == "Windows":
        found.extend(_scan_windows_registry())
        found.extend(_scan_common_dirs_windows())
    else:
        found.extend(_scan_common_dirs_unix())

    for p in _scan_path():
        if p not in [f["path"] for f in found]:
            info = _get_java_info(p)
            if info:
                info["source"] = "$PATH"
                found.append(info)

    found.sort(key=lambda x: x.get("version", 0), reverse=True)
    return found


def _java_exe(base: str) -> str:
    return os.path.join(base, "bin", "java.exe") if platform.system() == "Windows" else os.path.join(base, "bin", "java")


def _get_java_info(java_path: str) -> dict | None:
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True, text=True, timeout=10,
            startupinfo=startupinfo,
        )
        output = result.stderr + result.stdout
        ver_match = re.search(r'version\s+"([^"]+)"', output)
        if not ver_match:
            return None
        version_str = ver_match.group(1)
        major = int(version_str.split(".")[0]) if "." in version_str else int(version_str)
        if major == 1:
            major = int(version_str.split(".")[1]) if version_str.count(".") >= 1 else 8

        vendor = "Unknown"
        if "openjdk" in output.lower():
            vendor = "OpenJDK"
        if "oracle" in output.lower():
            vendor = "Oracle"
        if "microsoft" in output.lower():
            vendor = "Microsoft"
        if "temurin" in output.lower() or "adoptium" in output.lower():
            vendor = "Eclipse Temurin"
        if "graalvm" in output.lower():
            vendor = "GraalVM"
        if "amazon" in output.lower():
            vendor = "Amazon Corretto"

        return {
            "path": java_path,
            "version": major,
            "version_str": version_str,
            "vendor": vendor,
            "arch": platform.machine(),
        }
    except Exception as e:
        print(f"Java detection error for {java_path}: {e}")
        return None


def _scan_windows_registry() -> list[dict]:
    found = []
    try:
        import winreg
        for hive_key, hive_name in [(winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")]:
            for sub_key in [
                r"SOFTWARE\JavaSoft\Java Development Kit",
                r"SOFTWARE\JavaSoft\Java Runtime Environment",
                r"SOFTWARE\JavaSoft\JDK",
                r"SOFTWARE\JavaSoft\JRE",
                r"SOFTWARE\Eclipse Adoptium\JDK",
                r"SOFTWARE\Eclipse Foundation\JDK",
                r"SOFTWARE\Microsoft\JDK",
            ]:
                try:
                    key = winreg.OpenKey(hive_key, sub_key)
                    try:
                        i = 0
                        while True:
                            ver_name = winreg.EnumKey(key, i)
                            try:
                                ver_key = winreg.OpenKey(key, ver_name)
                                java_home, _ = winreg.QueryValueEx(ver_key, "JavaHome")
                                exe = _java_exe(java_home)
                                if os.path.exists(exe):
                                    info = _get_java_info(exe)
                                    if info:
                                        info["source"] = f"Registry ({hive_name})"
                                        found.append(info)
                                winreg.CloseKey(ver_key)
                            except (OSError, FileNotFoundError):
                                pass
                            i += 1
                    except OSError:
                        pass
                    winreg.CloseKey(key)
                except (OSError, FileNotFoundError):
                    continue
    except Exception:
        pass
    return found


def _scan_common_dirs_windows() -> list[dict]:
    found = []
    common_dirs = [
        r"C:\Program Files\Java",
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Microsoft\JDK",
        r"C:\Program Files\Amazon Corretto",
        r"C:\Program Files\GraalVM",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Eclipse Adoptium"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft\JDK"),
    ]
    for base in common_dirs:
        base_path = Path(base)
        if base_path.exists():
            for d in base_path.iterdir():
                if d.is_dir():
                    exe = _java_exe(str(d))
                    if os.path.exists(exe):
                        info = _get_java_info(exe)
                        if info:
                            info["source"] = f"Common dir ({base})"
                            found.append(info)
    return found


def _scan_common_dirs_unix() -> list[dict]:
    found = []
    common = [
        "/usr/lib/jvm",
        "/usr/local/lib/jvm",
        "/opt/java",
        "/opt/jdk",
    ]
    for base in common:
        p = Path(base)
        if p.exists():
            for d in p.iterdir():
                if d.is_dir():
                    exe = _java_exe(str(d))
                    if os.path.exists(exe):
                        info = _get_java_info(exe)
                        if info:
                            found.append(info)
    return found


def _scan_path() -> list[str]:
    java_exe = shutil.which("java")
    if java_exe:
        return [java_exe]
    return []


def suggest_java_for_instance(java_list: list[dict], mc_version: str) -> str | None:
    required = get_java_for_mc_version(mc_version)
    candidates = [j for j in java_list if j["version"] == required]
    if candidates:
        return candidates[0]["path"]
    candidates = [j for j in java_list if j["version"] >= required]
    if candidates:
        return candidates[0]["path"]
    if java_list:
        return java_list[0]["path"]
    return None


def _get_platform_arch():
    """Return (os, arch) tuple for Adoptium API, e.g. ('windows', 'x64')"""
    syst = platform.system().lower()
    if syst == "windows":
        os_arch = "windows"
    elif syst == "linux":
        os_arch = "linux"
    elif syst == "darwin":
        os_arch = "mac"
    else:
        os_arch = "linux"
    arch = platform.machine().lower()
    if arch in ("amd64", "x86_64", "x64"):
        arch = "x64"
    elif arch in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        arch = "x64"
    return os_arch, arch


def get_java_download_url(version: int) -> str | None:
    os_arch, arch = _get_platform_arch()
    url = (
        f"https://api.adoptium.net/v3/binary/latest/{version}/ga/"
        f"{os_arch}/{arch}/jdk/hotspot/normal/eclipse"
    )
    return url


def get_java_download_name(version: int) -> str | None:
    names = {8: "Java 8 (Temurin)", 17: "Java 17 (Temurin)", 21: "Java 21 (Temurin)"}
    return names.get(version)
