#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/patch_rustdesk_android.py

目标（对应你截图那套改法）：
- 替换 Android 端包名/应用名/scheme/service/class/文案
- 可选迁移 Kotlin 包目录（删旧目录，建新目录并搬文件）
- 生成报告：todd_patch_report.md（方便你在 GitHub 里核对）
- 做必要校验：如果关键点没改到会直接报错退出（避免编出来安装就崩）

用法（Actions 里会自动跑）：
  python3 tools/patch_rustdesk_android.py --repo . --move-kotlin-dir
"""

from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple, Dict


TEXT_EXTS = {".kt", ".java", ".xml", ".gradle", ".properties", ".txt", ".md"}


@dataclass
class PatchConfig:
    old_package: str
    new_package: str
    old_app_name: str
    new_app_name: str
    old_scheme: str
    new_scheme: str
    old_service: str
    new_service: str
    accessibility_desc: str

    def mapping(self) -> Dict[str, str]:
        return {
            self.old_package: self.new_package,
            self.old_app_name: self.new_app_name,
            self.old_scheme: self.new_scheme,
        }


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8", newline="\n")


def iter_text_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_EXTS:
            yield p


def safe_word_replace(word: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(word)}\b")


def replace_in_file(p: Path, rules: Iterable[Tuple[re.Pattern, str]]) -> bool:
    src = read_text(p)
    dst = src
    for pat, repl in rules:
        dst = pat.sub(repl, dst)
    if dst != src:
        write_text(p, dst)
        return True
    return False


def build_rules(cfg: PatchConfig) -> list[Tuple[re.Pattern, str]]:
    rules: list[Tuple[re.Pattern, str]] = []

    # 1) 全局：包名、App 名、Scheme
    for old, new in cfg.mapping().items():
        rules.append((re.compile(re.escape(old)), new))

    # 2) strings.xml：强制替换 app_name + accessibility_service_description
    rules.append((
        re.compile(r'(<string\s+name="accessibility_service_description">).*?(</string>)', re.DOTALL),
        rf"\1{cfg.accessibility_desc}\2"
    ))
    rules.append((
        re.compile(r'(<string\s+name="app_name">).*?(</string>)', re.DOTALL),
        rf"\1{cfg.new_app_name}\2"
    ))

    # 3) Manifest：service 名（.InputService -> .ToddService）
    rules.append((
        re.compile(r'android:name="\.' + re.escape(cfg.old_service) + r'"'),
        f'android:name=".{cfg.new_service}"'
    ))

    # 4) Kotlin/Java：类名 InputService -> ToddService（完整单词）
    rules.append((safe_word_replace(cfg.old_service), cfg.new_service))

    # 5) 你截图里出现的固定文案（避免误伤，不做泛化 RustDesk->ToddDesk）
    fixed_strings = {
        "RustDesk Input": cfg.new_app_name,
        "RustDesk Service": f"{cfg.new_app_name} Service",
        "RustDesk Service Channel": f"{cfg.new_app_name} Service Channel",
        "Show RustDesk": f"Show {cfg.new_app_name}",
    }
    for old, new in fixed_strings.items():
        rules.append((re.compile(re.escape(old)), new))

    # 6) Kotlin：logTag "input service" -> "Todd service"（按你截图）
    rules.append((re.compile(r'"input\s+service"'), '"Todd service"'))

    # 7) Kotlin：idShowRustDesk -> idShowToddDesk
    rules.append((safe_word_replace("idShowRustDesk"), "idShowToddDesk"))

    return rules


def move_kotlin_dir(repo: Path, cfg: PatchConfig, report_lines: list[str]) -> None:
    kotlin_root = repo / "flutter" / "android" / "app" / "src" / "main" / "kotlin"
    if not kotlin_root.exists():
        report_lines.append(f"- Kotlin root not found: {kotlin_root}")
        return

    old_dir = kotlin_root / Path(*cfg.old_package.split("."))
    new_dir = kotlin_root / Path(*cfg.new_package.split("."))

    if not old_dir.exists():
        report_lines.append(f"- Old kotlin dir not found (skip move): {old_dir}")
        return

    new_dir.parent.mkdir(parents=True, exist_ok=True)
    if new_dir.exists():
        report_lines.append(f"- New kotlin dir exists, merge files: {new_dir}")
        for item in old_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(old_dir)
                dst = new_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)
        shutil.rmtree(old_dir, ignore_errors=True)
        report_lines.append(f"- Deleted old kotlin dir: {old_dir}")
    else:
        shutil.move(str(old_dir), str(new_dir))
        report_lines.append(f"- Moved kotlin dir: {old_dir} -> {new_dir}")


def must_contain(p: Path, needle: str, hint: str) -> None:
    s = read_text(p)
    if needle not in s:
        raise SystemExit(f"[FAIL] 校验失败：{p} 不包含 '{needle}'（{hint}）")


def must_not_contain(p: Path, needle: str, hint: str) -> None:
    s = read_text(p)
    if needle in s:
        raise SystemExit(f"[FAIL] 校验失败：{p} 仍包含 '{needle}'（{hint}）")


def scan_any(root: Path, needle: str) -> list[Path]:
    hits: list[Path] = []
    for f in iter_text_files(root):
        if needle in read_text(f):
            hits.append(f)
    return hits


def write_report(repo: Path, cfg: PatchConfig, changed_files: list[Path], report_lines: list[str]) -> None:
    rp = repo / "todd_patch_report.md"
    lines: list[str] = []
    lines.append(f"# Todd Android Patch Report\n")
    lines.append(f"## Targets\n")
    lines.append(f"- old_package: `{cfg.old_package}`\n")
    lines.append(f"- new_package: `{cfg.new_package}`\n")
    lines.append(f"- old_app_name: `{cfg.old_app_name}`\n")
    lines.append(f"- new_app_name: `{cfg.new_app_name}`\n")
    lines.append(f"- old_scheme: `{cfg.old_scheme}`\n")
    lines.append(f"- new_scheme: `{cfg.new_scheme}`\n")
    lines.append(f"- old_service: `{cfg.old_service}`\n")
    lines.append(f"- new_service: `{cfg.new_service}`\n")
    lines.append(f"- accessibility_desc: `{cfg.accessibility_desc}`\n")

    lines.append("\n## File changes\n")
    lines.append(f"- changed_files_count: **{len(changed_files)}**\n")
    for f in changed_files[:300]:
        lines.append(f"  - `{f.as_posix()}`\n")
    if len(changed_files) > 300:
        lines.append(f"  - ... and {len(changed_files)-300} more\n")

    lines.append("\n## Directory move / notes\n")
    for x in report_lines:
        lines.append(f"{x}\n")

    write_text(rp, "".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="仓库根目录（包含 flutter/）")
    ap.add_argument("--old-package", default="com.carriez.flutter_hbb")
    ap.add_argument("--new-package", default="com.celonis.work")
    ap.add_argument("--old-app-name", default="RustDesk")
    ap.add_argument("--new-app-name", default="ToddDesk")
    ap.add_argument("--old-scheme", default="rustdesk")
    ap.add_argument("--new-scheme", default="todddesk")
    ap.add_argument("--old-service", default="InputService")
    ap.add_argument("--new-service", default="ToddService")
    ap.add_argument("--accessibility-desc", default="Made by Todd")
    ap.add_argument("--move-kotlin-dir", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    cfg = PatchConfig(
        old_package=args.old_package,
        new_package=args.new_package,
        old_app_name=args.old_app_name,
        new_app_name=args.new_app_name,
        old_scheme=args.old_scheme,
        new_scheme=args.new_scheme,
        old_service=args.old_service,
        new_service=args.new_service,
        accessibility_desc=args.accessibility_desc,
    )

    android_root = repo / "flutter" / "android"
    if not android_root.exists():
        raise SystemExit(f"[FAIL] 未找到 flutter/android：{android_root}")

    rules = build_rules(cfg)

    changed_files: list[Path] = []
    scanned = 0
    for f in iter_text_files(android_root):
        scanned += 1
        if replace_in_file(f, rules):
            changed_files.append(f.relative_to(repo))

    report_lines: list[str] = []
    if args.move_kotlin_dir:
        move_kotlin_dir(repo, cfg, report_lines)

    # ======= 关键校验（防止“看似改了但没改到关键点”）=======
    # build.gradle: applicationId
    gradle = repo / "flutter/android/app/build.gradle"
    if gradle.exists():
        must_contain(gradle, f'applicationId "{cfg.new_package}"', "applicationId 必须是新包名")
        must_not_contain(gradle, f'applicationId "{cfg.old_package}"', "旧 applicationId 必须消失")

    manifest = repo / "flutter/android/app/src/main/AndroidManifest.xml"
    if manifest.exists():
        must_contain(manifest, f'package="{cfg.new_package}"', "manifest package 必须是新包名")
        must_contain(manifest, f'android:label="{cfg.new_app_name}"', "app label 必须是新名称")
        must_contain(manifest, f'android:name=".{cfg.new_service}"', "service android:name 必须是新 Service")
        must_contain(manifest, f'android:scheme="{cfg.new_scheme}"', "scheme 必须是新 scheme")

    # 全库扫描：flutter/android 内不允许残留旧包名（最重要）
    hits = scan_any(android_root, cfg.old_package)
    if hits:
        show = "\n".join([f"- {h.as_posix()}" for h in hits[:50]])
        raise SystemExit(f"[FAIL] flutter/android 仍残留旧包名 `{cfg.old_package}`，示例文件：\n{show}\n（请把日志/报告发我）")

    write_report(repo, cfg, changed_files, report_lines)
    print(f"[OK] scanned={scanned}, changed_files={len(changed_files)}, report=todd_patch_report.md")


if __name__ == "__main__":
    main()
