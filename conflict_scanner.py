import hashlib
import json
import os
import zipfile
import re
from pathlib import Path

KNOWN_INCOMPATIBILITIES = [
    ("optifabric", "optifine", "OptiFabric + OptiFine causes conflicts; use OptiFine directly or use Fabric API + Sodium/Iris instead"),
    ("sodium", "optifine", "Sodium and OptiFine are incompatible; use one or the other"),
    ("sodium", "vanillafix", "VanillaFix is unnecessary with Sodium 0.5+"),
    ("phosphor", "lithium", "Phosphor is deprecated; Lithium includes its own lighting fixes"),
    ("betterfps", "phosphor", "BetterFPS is deprecated; use Sodium or Lithium"),
    ("betterfps", "sodium", "BetterFPS is deprecated; use Sodium or Lithium"),
    ("foamfix", "sodium", "FoamFix is deprecated; use Sodium for better performance"),
    ("foamfix", "lithium", "FoamFix is deprecated; use Lithium for server-side optimizations"),
    ("vintagefix", "sodium", "VintageFix may conflict with Sodium rendering"),
    ("optifine", "iris", "OptiFine and Iris Shaders are incompatible; use one or the other"),
    ("optifine", "sodium", "OptiFine and Sodium are incompatible; use one or the other"),
    ("optifine", "canvas", "OptiFine and Canvas Renderer are incompatible"),
]

KNOWN_DUPLICATE_PATTERNS = [
    (r"(fabric-api|fabric_api|fabricapi).*", "fabric-api"),
    (r"(forge|forge-1\.\d+\.\d+).*", "forge"),
    (r"(quilt|qsl|qkl).*", "quilt-standard-libraries"),
    (r"(architectury|archtectury).*", "architectury-api"),
]

VERSION_EXTRACT_REGEX = re.compile(r'(\d+\.\d+(?:\.\d+)?)')


def _get_file_hash(filepath):
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _normalize_name(name):
    base = Path(name).stem.lower().replace("_", "").replace("-", "").replace(" ", "")
    return re.sub(r'[^a-z0-9]', '', base)


def _extract_mc_version_from_jar(jar_path):
    try:
        with zipfile.ZipFile(jar_path, "r") as z:
            if "fabric.mod.json" in z.namelist():
                data = json.loads(z.read("fabric.mod.json"))
                for dep in data.get("depends", {}):
                    if dep == "minecraft":
                        raw = data["depends"]["minecraft"]
                        if isinstance(raw, str):
                            match = VERSION_EXTRACT_REGEX.search(raw)
                            if match:
                                return match.group(1)
            if "META-INF/MANIFEST.MF" in z.namelist():
                manifest = z.read("META-INF/MANIFEST.MF").decode("utf-8", errors="ignore")
                for line in manifest.splitlines():
                    if line.startswith("Implementation-Version:"):
                        match = VERSION_EXTRACT_REGEX.search(line)
                        if match:
                            return match.group(1)
    except Exception:
        pass
    return None


def scan_mods_directory(mods_dir):
    mods_dir = Path(mods_dir)
    if not mods_dir.exists():
        return []

    results = []
    jar_files = [f for f in mods_dir.iterdir() if f.suffix == ".jar"]
    seen_hashes = {}
    seen_names = {}

    # Phase 1: check for duplicates by hash and by normalized name
    for jar in jar_files:
        jar_hash = _get_file_hash(jar)
        jar_name = _normalize_name(jar.stem)

        if jar_hash and jar_hash in seen_hashes:
            results.append({
                "type": "duplicate_hash",
                "severity": "error",
                "file": jar.name,
                "message": f"Duplicate of {seen_hashes[jar_hash]} (identical file)",
                "path": str(jar),
            })
        elif jar_hash:
            seen_hashes[jar_hash] = jar.name

        if jar_name in seen_names:
            results.append({
                "type": "duplicate_name",
                "severity": "warning",
                "file": jar.name,
                "message": f"Similar name to {seen_names[jar_name]} (may be same mod)",
                "path": str(jar),
            })
        else:
            seen_names[jar_name] = jar.name

    # Phase 2: check for known incompatibilities
    installed_lower = {}
    for jar in jar_files:
        installed_lower[_normalize_name(jar.stem)] = jar.name

    for a, b, reason in KNOWN_INCOMPATIBILITIES:
        a_norm = _normalize_name(a)
        b_norm = _normalize_name(b)
        if a_norm in installed_lower and b_norm in installed_lower:
            results.append({
                "type": "incompatibility",
                "severity": "error",
                "file": f"{installed_lower[a_norm]}, {installed_lower[b_norm]}",
                "message": f"Known incompatibility: {reason}",
                "path": "",
            })

    # Phase 3: check version tags
    mod_versions = {}
    for jar in jar_files:
        mc_ver = _extract_mc_version_from_jar(jar)
        if mc_ver:
            mod_versions[jar.name] = mc_ver

    if len(set(mod_versions.values())) > 1:
        by_version = {}
        for name, ver in mod_versions.items():
            by_version.setdefault(ver, []).append(name)
        if len(by_version) > 1:
            target_ver = max(by_version.keys(), key=lambda v: [int(x) for x in v.split(".")])
            others = {ver: names for ver, names in by_version.items() if ver != target_ver}
            for ver, names in others.items():
                results.append({
                    "type": "version_mismatch",
                    "severity": "warning",
                    "file": ", ".join(names),
                    "message": f"Targets MC {ver} (expected ~{target_ver})",
                    "path": "",
                })

    return results


def scan_resourcepacks_directory(rp_dir):
    rp_dir = Path(rp_dir)
    if not rp_dir.exists():
        return []

    results = []
    items = [f for f in rp_dir.iterdir() if f.suffix in (".zip", ".mcpack") or f.is_dir()]

    # Check for duplicate resource pack names
    seen = {}
    for item in items:
        name = _normalize_name(item.stem if item.suffix in (".zip", ".mcpack") else item.name)
        if name in seen:
            results.append({
                "type": "duplicate_name",
                "severity": "warning",
                "file": item.name,
                "message": f"Resource pack may duplicate content from {seen[name]}",
                "path": str(item),
            })
        else:
            seen[name] = item.name

    return results
