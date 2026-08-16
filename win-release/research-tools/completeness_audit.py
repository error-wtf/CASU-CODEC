#!/usr/bin/env python3
"""Read-only completeness audit for the Windows-port reference tree.

Enumerates every source file under /home/error/Codec-Casu (excluding
dist/ and win-release/) and classifies it. Then checks that the analysis
documents in win-release/research/ + roadmap/ mention it (by basename or a
grouping token). Outputs anything NOT covered, so no file is forgotten.

This tool only READS the reference tree; it never modifies it.
"""
import os
import re
import sys

ROOT = "/home/error/Codec-Casu"
RESEARCH = os.path.join(ROOT, "win-release", "research")
ROADMAP = os.path.join(ROOT, "win-release", "roadmap")
EXCLUDE_TOP = {"dist", "win-release", ".git", "pure-web-release"}

EXTENSIONS = {
    ".py": "python", ".js": "javascript", ".html": "html", ".css": "css",
    ".sh": "shell", ".json": "json", ".md": "markdown", ".toml": "toml",
    ".cfg": "config", ".ini": "config", ".txt": "text", ".tsv": "text",
    ".csv": "text", ".xml": "xml", ".m3u": "playlist", ".pls": "playlist",
}

# Grouping tokens that, when found in the analysis corpus, count as covering a
# whole directory of files (so we don't need to name every test individually).
GROUP_TOKENS = {
    "tests/": ["test-", "test_map", "test-semantics", "pytest", "smoke",
               "acceptance", "fuzz", "test-suite"],
    "casu/": ["casu-format", "casu-", "repository-inventory", "feature-matrix",
              "format-map", "api-contracts"],
    "tools/": ["tool", "smoke", "screenshot", "release-gate", "inventory"],
    "docs/": ["format-map", "deep-dive", "reference", "documentation"],
}


def collect():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        top = rel.split(os.sep)[0]
        if top in EXCLUDE_TOP or rel == "." or rel.startswith("."):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_TOP]
            continue
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in EXTENSIONS and not name.startswith("."):
                files.append((os.path.join(rel, name), EXTENSIONS[ext]))
    return files


def corpus():
    text = []
    for base in (RESEARCH, ROADMAP):
        for dirpath, _dn, filenames in os.walk(base):
            for name in filenames:
                if name.endswith(".md"):
                    text.append(open(os.path.join(dirpath, name), encoding="utf-8", errors="replace").read())
    return "\n".join(text)


def covered(basename, path, corpus_text):
    if basename in corpus_text:
        return True
    if basename.replace(".", "\\.") and re.search(rf"\b{re.escape(basename)}\b", corpus_text):
        return True
    for prefix, tokens in GROUP_TOKENS.items():
        if path.startswith(prefix):
            return any(tok in corpus_text for tok in tokens)
    return False


def main():
    files = collect()
    text = corpus()
    missing = []
    by_lang = {}
    for rel, lang in sorted(files):
        by_lang[lang] = by_lang.get(lang, 0) + 1
        base = os.path.basename(rel)
        if not covered(base, rel, text):
            missing.append(rel)
    print("=== Sprachendistribution ===")
    for lang, n in sorted(by_lang.items(), key=lambda x: -x[1]):
        print(f"  {lang:10s} {n}")
    print(f"\nGesamt: {len(files)} Quelldateien analysiert")
    print(f"\n=== NICHT in Hilfsdateien abgedeckt: {len(missing)} ===")
    for rel in missing:
        print("  " + rel)
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
