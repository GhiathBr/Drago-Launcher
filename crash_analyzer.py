import os
import re
from pathlib import Path
from datetime import datetime

KNOWN_CRASH_PATTERNS = [
    {
        "pattern": re.compile(r'java\.lang\.OutOfMemoryError', re.IGNORECASE),
        "category": "memory",
        "severity": "error",
        "title": "Out of Memory",
        "suggestion": "Increase allocated RAM in Settings or Instance Settings. Try 4GB minimum, 6-8GB for modded packs.",
    },
    {
        "pattern": re.compile(r'java\.lang\.StackOverflowError', re.IGNORECASE),
        "category": "memory",
        "severity": "error",
        "title": "Stack Overflow",
        "suggestion": "This is often caused by conflicting mods or recursive code. Try removing recently added mods.",
    },
    {
        "pattern": re.compile(r'net\.minecraftforge\.fml\.loading\.LoadError|fml\.LoadingError', re.IGNORECASE),
        "category": "forge",
        "severity": "error",
        "title": "Forge Mod Loading Error",
        "suggestion": "A mod failed to load. Check the crash report for specific mod name. Try updating Forge or removing the problematic mod.",
    },
    {
        "pattern": re.compile(r'mixin.*?conflict|conflicting.*?mixin|mixin.*?error', re.IGNORECASE),
        "category": "mixin",
        "severity": "warning",
        "title": "Mixin Conflict",
        "suggestion": "Two or more mods are trying to modify the same game code. Try removing recently added mods or updating mods to their latest versions.",
    },
    {
        "pattern": re.compile(r'java\.lang\.NoClassDefFoundError|java\.lang\.ClassNotFoundException', re.IGNORECASE),
        "category": "missing_class",
        "severity": "error",
        "title": "Missing Class / Dependency",
        "suggestion": "A mod is missing a required library. Check if you need a dependency mod (like Fabric API, Forge, or a library mod).",
    },
    {
        "pattern": re.compile(r'java\.lang\.NullPointerException', re.IGNORECASE),
        "category": "null_pointer",
        "severity": "warning",
        "title": "Null Pointer Exception",
        "suggestion": "Generic error. Check mod compatibility or try removing recently added mods.",
    },
    {
        "pattern": re.compile(r'UnsupportedClassVersionError|major\.version', re.IGNORECASE),
        "category": "java_version",
        "severity": "error",
        "title": "Wrong Java Version",
        "suggestion": "The mod requires a different Java version. For MC 1.17+, use Java 17+. For MC 1.20.5+, use Java 21+.",
    },
    {
        "pattern": re.compile(r'Could not reserve enough space for object heap|Failed to allocate memory', re.IGNORECASE),
        "category": "memory",
        "severity": "error",
        "title": "Insufficient System Memory",
        "suggestion": "Your system doesn't have enough available memory. Close other programs and reduce allocated RAM.",
    },
    {
        "pattern": re.compile(r'org\.lwjgl\.|GLFW|GL error', re.IGNORECASE),
        "category": "graphics",
        "severity": "error",
        "title": "OpenGL / Graphics Error",
        "suggestion": "Update your graphics drivers. If using OptiFine, try without it. On integrated GPUs, allocate more video memory in BIOS.",
    },
    {
        "pattern": re.compile(r'EXCEPTION_ACCESS_VIOLATION|SIGSEGV', re.IGNORECASE),
        "category": "native",
        "severity": "critical",
        "title": "Native Crash (Access Violation)",
        "suggestion": "This is often caused by graphics issues or corrupted Java installation. Update GPU drivers and Java. Disable OptiFine if installed.",
    },
    {
        "pattern": re.compile(r'Could not create the Java Virtual Machine', re.IGNORECASE),
        "category": "jvm",
        "severity": "error",
        "title": "JVM Creation Failed",
        "suggestion": "Check your JVM arguments. Reduce allocated RAM or remove custom JVM flags.",
    },
    {
        "pattern": re.compile(r'Exit code:?\s*(-?\d+)'),
        "category": "exit_code",
        "severity": "info",
        "title": "Non-Zero Exit Code",
        "suggestion": "",
    },
    {
        "pattern": re.compile(r'Mod Resolution.*?failed|unresolved.*?mod|missing.*?mod', re.IGNORECASE),
        "category": "mod_resolution",
        "severity": "error",
        "title": "Mod Resolution Failure",
        "suggestion": "Missing mod dependencies. Try installing the latest version of Fabric API, Forge, or other required libraries.",
    },
    {
        "pattern": re.compile(r'optifine|optifabric', re.IGNORECASE),
        "category": "optifine",
        "severity": "warning",
        "title": "OptiFine-Related Crash",
        "suggestion": "OptiFine is known to cause crashes with many mods. Try removing OptiFine and using Sodium + Iris instead.",
    },
    {
        "pattern": re.compile(r'java\.lang\.IllegalAccessError', re.IGNORECASE),
        "category": "access",
        "severity": "error",
        "title": "Illegal Access Error",
        "suggestion": "A mod is trying to access internal game code it shouldn't. Update the mod or check for compatibility issues.",
    },
    {
        "pattern": re.compile(r'Connection refused|ConnectException|UnknownHostException|Connection timed out', re.IGNORECASE),
        "category": "network",
        "severity": "warning",
        "title": "Connection Error",
        "suggestion": "Check your internet connection or the server address. The server may be offline.",
    },
    {
        "pattern": re.compile(r'Failed to login|Invalid session|Authentication.*?failed', re.IGNORECASE),
        "category": "auth",
        "severity": "warning",
        "title": "Authentication Error",
        "suggestion": "Re-login with your Microsoft account. Your session may have expired.",
    },
    {
        "pattern": re.compile(r'Internal Exception|readTimeout|read time out', re.IGNORECASE),
        "category": "network",
        "severity": "warning",
        "title": "Network Read Timeout",
        "suggestion": "Server connection timed out. The server may be overloaded or your connection is unstable.",
    },
]


def find_crash_reports(instance_dir):
    crash_dir = Path(instance_dir) / "crash-reports"
    if not crash_dir.exists():
        crash_dir = Path(instance_dir) / "crash-reports"
        if not crash_dir.exists():
            return []
    reports = sorted(crash_dir.glob("*.txt"), key=os.path.getmtime, reverse=True)
    return reports


def analyze_crash_report(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return None

    lines = content.splitlines()
    report = {
        "file": str(filepath),
        "filename": os.path.basename(filepath),
        "lines": len(lines),
        "size": os.path.getsize(filepath),
        "mod_time": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat(),
        "time": _extract_time(lines),
        "minecraft_version": _extract_value(lines, r"Minecraft\s*(?:Version|v)?[:\s]+(.+)"),
        "java_version": _extract_value(lines, r"Java\s*(?:Version|v)?[:\s]+(.+)"),
        "mods_loaded": _extract_value(lines, r"Mods\s*loaded[:\s]+(\d+)"),
        "suspect_mod": _extract_value(lines, r"(?:Suspect|Suspected|Likely culprit)[:\s]+(.+)"),
        "stack_trace_head": _extract_stack_trace_head(lines),
        "matches": [],
    }

    for pattern_info in KNOWN_CRASH_PATTERNS:
        match = pattern_info["pattern"].search(content)
        if match:
            suggestion = pattern_info["suggestion"]
            exit_code = match.group(1) if pattern_info["category"] == "exit_code" else None
            if exit_code:
                report["exit_code"] = exit_code
                if exit_code == "0":
                    continue
                suggestion = EXIT_CODE_SUGGESTIONS.get(exit_code, "")

            report["matches"].append({
                "category": pattern_info["category"],
                "severity": pattern_info["severity"],
                "title": pattern_info["title"],
                "suggestion": suggestion,
                "matched_text": content[max(0, match.start()-50):match.end()+100],
            })

    if not report["matches"]:
        report["matches"].append({
            "category": "unknown",
            "severity": "info",
            "title": "Unknown Crash",
            "suggestion": "Could not identify the crash cause. Check the crash report manually or share it on modding forums.",
            "matched_text": _extract_stack_trace_head(lines)[:500] if report["stack_trace_head"] else "",
        })

    return report


EXIT_CODE_SUGGESTIONS = {
    "1": "Generic JVM error. Check Java installation and allocated RAM.",
    "-1": "Generic error. Check crash report for details.",
    "-805306369": "Out of memory or graphics driver crash. Reduce allocated RAM or update GPU drivers.",
    "-1073740791": "Access violation. Usually caused by graphics issues or corrupted Java installation.",
    "-1073741819": "Access violation error. Update GPU drivers and Java.",
    "-1073740940": "Not enough memory. Increase allocated RAM.",
    "-1073741676": "Broken pipe / network error. Check your internet connection.",
    "-1073741515": "Application was killed. Your system may have run out of memory.",
    "-1073741502": "Application hang detected by Windows.",
    "0": "Normal exit (not a crash).",
}


def _extract_value(lines, pattern):
    for line in lines:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_time(lines):
    for line in lines[:5]:
        if "Time" in line:
            match = re.search(r"Time[:\s]+(.+)", line)
            if match:
                return match.group(1).strip()
    return None


def _extract_stack_trace_head(lines):
    for i, line in enumerate(lines):
        if "at net.minecraft" in line or "at net.minecraftforge" in line or "at org.spongepowered" in line:
            start = max(0, i - 3)
            return "\n".join(lines[start:i+5])
    for i, line in enumerate(lines):
        if "at " in line:
            start = max(0, i - 3)
            return "\n".join(lines[start:i+5])
    return None


def analyze_instance(instance_dir):
    reports = find_crash_reports(instance_dir)
    if not reports:
        return []

    results = []
    for report_path in reports:
        analysis = analyze_crash_report(report_path)
        if analysis:
            results.append(analysis)

    return results[:10]
