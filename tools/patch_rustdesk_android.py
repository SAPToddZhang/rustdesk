#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/patch_rustdesk_android.py

目标（对应你截图那套改法）：
- 替换 Android 端：包名 / 应用名 / scheme / service / class / 固定文案
- 可选迁移 Kotlin 包目录（删旧目录，建新目录并搬文件）
- 生成报告：todd_patch_report.md（方便你在 GitHub 里核对）
- 做必要校验：关键点没改到会直接报错退出（避免编出来安装就崩）
- 重要安全：保护 native so 库名（librustdesk.so / System.loadLibrary("rustdesk")），避免 UnsatisfiedLinkError

用法（Actions 里会自动跑）：
  python3 tools/patch_rustdesk_android.py --repo . --move-kotlin-dir
"""

from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple, Dict, List


TEXT_EXTS = {".kt", ".java", ".xml", ".gradle", ".properties", ".txt", ".md", ".dart"}


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
        # 只做“安全”的全局替换：包名、App 名
        # ⚠️ scheme 绝对不要全局替换：会误伤 librustdesk.so / loadLibrary("rustdesk")
        return {
            self.old_package: self.new_package,
            self.old_app_name: self.new_app_name,
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

    # 1) 全局：包名、App 名（安全）
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
    #    注意：RustDesk Input 不要替换成 ToddDesk（会丢 Input），改为 ToddDesk Input
    fixed_strings = {
        "RustDesk Input": f"{cfg.new_app_name} Input",
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

    # =========================
    # ✅ scheme：只做“定点替换”
    # =========================
    # 8) AndroidManifest 的 scheme：android:scheme="rustdesk" -> new_scheme
    rules.append((
        re.compile(r'android:scheme="' + re.escape(cfg.old_scheme) + r'"'),
        f'android:scheme="{cfg.new_scheme}"'
    ))
    # 9) 显式 rustdesk:// -> new_scheme://（不会影响 loadLibrary("rustdesk") / librustdesk.so）
    rules.append((
        re.compile(re.escape(cfg.old_scheme) + r"://"),
        f"{cfg.new_scheme}://"
    ))

    # ==========================================
    # ✅ 保护 native so / loadLibrary（非常关键）
    # ==========================================
    # 10) 兜底修复：如果有人把 System.loadLibrary("rustdesk") 改成了别的，强制改回
    rules.append((
        re.compile(r'System\.loadLibrary\("(?:' + re.escape(cfg.old_scheme) + r'|' + re.escape(cfg.new_scheme) + r'|rustdesk|todddesk)"\)'),
        'System.loadLibrary("rustdesk")'
    ))
    # 11) 如果出现 libtodddesk.so（或 lib<new_scheme>.so），强制改回 librustdesk.so
    #     这里做宽松兜底：任何 lib<new_scheme>.so 都回退为 librustdesk.so
    rules.append((
        re.compile(r'lib' + re.escape(cfg.new_scheme) + r'\.so'),
        'librustdesk.so'
    ))
    rules.append((
        re.compile(r'libtodddesk\.so'),
        'librustdesk.so'
    ))

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
    lines.append("# Todd Android Patch Report\n\n")
    lines.append("## Targets\n\n")
    lines.append(f"- old_package: `{cfg.old_package}`\n")
    lines.append(f"- new_package: `{cfg.new_package}`\n")
    lines.append(f"- old_app_name: `{cfg.old_app_name}`\n")
    lines.append(f"- new_app_name: `{cfg.new_app_name}`\n")
    lines.append(f"- old_scheme: `{cfg.old_scheme}`\n")
    lines.append(f"- new_scheme: `{cfg.new_scheme}`\n")
    lines.append(f"- old_service: `{cfg.old_service}`\n")
    lines.append(f"- new_service: `{cfg.new_service}`\n")
    lines.append(f"- accessibility_desc: `{cfg.accessibility_desc}`\n")

    lines.append("\n## File changes\n\n")
    lines.append(f"- changed_files_count: **{len(changed_files)}**\n")
    for f in changed_files[:400]:
        lines.append(f"  - `{f.as_posix()}`\n")
    if len(changed_files) > 400:
        lines.append(f"  - ... and {len(changed_files)-400} more\n")

    lines.append("\n## Directory move / notes\n\n")
    if report_lines:
        for x in report_lines:
            lines.append(f"{x}\n")
    else:
        lines.append("- (none)\n")

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

    # 1) build.gradle: applicationId
    gradle = repo / "flutter/android/app/build.gradle"
    if gradle.exists():
        must_contain(gradle, f'applicationId "{cfg.new_package}"', "applicationId 必须是新包名")
        must_not_contain(gradle, f'applicationId "{cfg.old_package}"', "旧 applicationId 必须消失")

    # 2) AndroidManifest 关键项
    manifest = repo / "flutter/android/app/src/main/AndroidManifest.xml"
    if manifest.exists():
        must_contain(manifest, f'package="{cfg.new_package}"', "manifest package 必须是新包名")
        # 有的项目 label 在 manifest 里是 @string/app_name，这里不强制必须 android:label="ToddDesk"
        # 只要 strings.xml 里 app_name 已经被强制替换即可
        must_contain(manifest, f'android:name=".{cfg.new_service}"', "service android:name 必须是新 Service")
        must_contain(manifest, f'android:scheme="{cfg.new_scheme}"', "scheme 必须是新 scheme")

    # 3) flutter/android 内不允许残留旧包名（最重要）
    hits_pkg = scan_any(android_root, cfg.old_package)
    if hits_pkg:
        show = "\n".join([f"- {h.as_posix()}" for h in hits_pkg[:50]])
        raise SystemExit(
            f"[FAIL] flutter/android 仍残留旧包名 `{cfg.old_package}`，示例文件：\n{show}\n"
            f"（请把 todd_patch_report.md 和失败日志发我）"
        )

    # 4) native so 保护校验：不允许出现 lib<new_scheme>.so / libtodddesk.so
    hits_so1 = scan_any(android_root, f"lib{cfg.new_scheme}.so")
    hits_so2 = scan_any(android_root, "libtodddesk.so")
    if hits_so1 or hits_so2:
        show_paths = [p.as_posix() for p in (hits_so1 + hits_so2)[:50]]
        show = "\n".join([f"- {x}" for x in show_paths])
        raise SystemExit(
            f"[FAIL] 检测到 native so 被误改（不允许出现 lib{cfg.new_scheme}.so / libtodddesk.so），示例文件：\n{show}\n"
            f"（这会导致安装后无响应：UnsatisfiedLinkError）"
        )

    # 5) 同理：不允许出现 System.loadLibrary("todddesk") / System.loadLibrary("<new_scheme>")
    hits_ll1 = scan_any(android_root, f'System.loadLibrary("{cfg.new_scheme}")')
    hits_ll2 = scan_any(android_root, 'System.loadLibrary("todddesk")')
    if hits_ll1 or hits_ll2:
        show_paths = [p.as_posix() for p in (hits_ll1 + hits_ll2)[:50]]
        show = "\n".join([f"- {x}" for x in show_paths])
        raise SystemExit(
            f"[FAIL] 检测到 System.loadLibrary 被误改（不允许 loadLibrary(\"{cfg.new_scheme}\")/\"todddesk\"），示例文件：\n{show}\n"
        )

    write_report(repo, cfg, changed_files, report_lines)
    print(f"[OK] scanned={scanned}, changed_files={len(changed_files)}, report=todd_patch_report.md")


if __name__ == "__main__":
    main()
