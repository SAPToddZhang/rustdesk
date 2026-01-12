#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
patch_rustdesk_android.py

目标：
- 直接修改仓库里的 flutter/android 相关文件（用于“改包名/改显示名/改scheme/改Service类名/改Kotlin包目录”）
- 支持生成报告（你能下载/查看改了哪些文件）
- 支持校验（如果漏改某个关键点，直接让 Actions 失败，避免你装包后“无响应/打不开”还不知道哪里漏了）

典型用法（在仓库根目录）：
  python tools/patch_rustdesk_android.py --repo . --move-kotlin-dir --report patch-report.md

参数默认就是你截图那套：
  old_package com.carriez.flutter_hbb  -> new_package com.celonis.work
  RustDesk -> ToddDesk
  rustdesk -> todddesk
  InputService -> ToddService
"""

from __future__ import annotations

import argparse
import difflib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

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


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8", newline="\n")


def iter_text_files(root: Path) -> Iterable[Path]:
    # 排除 build 目录，避免误改产物
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in {"build", ".gradle", ".idea"} for part in p.parts):
            continue
        if p.suffix.lower() in TEXT_EXTS:
            yield p


def safe_word_pat(word: str) -> re.Pattern:
    # 只替换完整标识符（Kotlin/Java）
    return re.compile(rf"\b{re.escape(word)}\b")


def apply_regex_rules(text: str, rules: List[Tuple[re.Pattern, str]]) -> str:
    out = text
    for pat, repl in rules:
        out = pat.sub(repl, out)
    return out


def unified_diff(old: str, new: str, filename: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(True),
        new.splitlines(True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    return "".join(diff)


def build_rules(cfg: PatchConfig) -> List[Tuple[re.Pattern, str]]:
    rules: List[Tuple[re.Pattern, str]] = []

    # 1) 包名（全量替换）
    rules.append((re.compile(re.escape(cfg.old_package)), cfg.new_package))

    # 2) scheme（如 rustdesk:// -> todddesk://）
    rules.append((re.compile(re.escape(cfg.old_scheme)), cfg.new_scheme))

    # 3) Service 类名（InputService -> ToddService），限定完整单词
    rules.append((safe_word_pat(cfg.old_service), cfg.new_service))

    # 4) app 名称：在 flutter/android 范围内，RustDesk -> ToddDesk 通常安全
    #    你截图里很多就是 RustDesk 字面量（通知标题、channel名、label等）
    rules.append((re.compile(re.escape(cfg.old_app_name)), cfg.new_app_name))

    # 5) strings.xml 的两个字段做“定点替换”，更稳
    rules.append((
        re.compile(r'(<string\s+name="accessibility_service_description">).*?(</string>)', re.DOTALL),
        rf"\1{cfg.accessibility_desc}\2"
    ))
    rules.append((
        re.compile(r'(<string\s+name="app_name">).*?(</string>)', re.DOTALL),
        rf"\1{cfg.new_app_name}\2"
    ))

    # 6) AndroidManifest service android:name=".InputService" -> ".ToddService"
    rules.append((
        re.compile(r'android:name="\.' + re.escape(cfg.old_service) + r'"'),
        f'android:name=".{cfg.new_service}"'
    ))

    return rules


def move_kotlin_dir(repo: Path, cfg: PatchConfig) -> Tuple[Path | None, Path | None]:
    kotlin_root = repo / "flutter" / "android" / "app" / "src" / "main" / "kotlin"
    if not kotlin_root.exists():
        return None, None

    old_dir = kotlin_root / Path(*cfg.old_package.split("."))
    new_dir = kotlin_root / Path(*cfg.new_package.split("."))

    if not old_dir.exists():
        return old_dir, new_dir

    new_dir.parent.mkdir(parents=True, exist_ok=True)
    if new_dir.exists():
        # 合并
        for item in old_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(old_dir)
                dst = new_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)
        shutil.rmtree(old_dir, ignore_errors=True)
    else:
        shutil.move(str(old_dir), str(new_dir))

    # 尝试清理空目录（比如 com/carriez）
    try:
        cur = old_dir.parent
        while cur != kotlin_root and cur.exists():
            if any(cur.iterdir()):
                break
            cur.rmdir()
            cur = cur.parent
    except Exception:
        pass

    return old_dir, new_dir


def validate(repo: Path, android_root: Path, cfg: PatchConfig) -> List[str]:
    """
    返回 errors 列表；为空表示通过。
    做你截图里那些“必须改到”的点的硬校验。
    """
    errors: List[str] = []

    build_gradle = android_root / "app" / "build.gradle"
    manifest = android_root / "app" / "src" / "main" / "AndroidManifest.xml"

    if build_gradle.exists():
        t = read_text(build_gradle)
        if cfg.new_package not in t:
            errors.append(f"build.gradle 未包含新 applicationId/包名：{cfg.new_package}")
        if cfg.old_package in t:
            errors.append(f"build.gradle 仍包含旧包名：{cfg.old_package}")
    else:
        errors.append("未找到 flutter/android/app/build.gradle")

    if manifest.exists():
        t = read_text(manifest)
        if f'package="{cfg.new_package}"' not in t:
            errors.append(f"AndroidManifest.xml package 属性未改为：{cfg.new_package}")
        if cfg.old_package in t:
            errors.append(f"AndroidManifest.xml 仍包含旧包名：{cfg.old_package}")
        if cfg.new_app_name not in t:
            errors.append(f"AndroidManifest.xml 未出现新应用名：{cfg.new_app_name}")
        if f'android:name=".{cfg.new_service}"' not in t:
            errors.append(f"AndroidManifest.xml service android:name 未改为：.{cfg.new_service}")
        if cfg.new_scheme not in t:
            errors.append(f"AndroidManifest.xml 未出现新 scheme：{cfg.new_scheme}")
    else:
        errors.append("未找到 flutter/android/app/src/main/AndroidManifest.xml")

    # 扫描 flutter/android 全量：不应再出现旧包名 / 旧 scheme / 旧 service 名
    old_hits = []
    for f in iter_text_files(android_root):
        txt = read_text(f)
        if cfg.old_package in txt or cfg.old_scheme in txt or f'.{cfg.old_service}' in txt or safe_word_pat(cfg.old_service).search(txt):
            old_hits.append(str(f.relative_to(repo)))
        if len(old_hits) >= 20:
            break

    if old_hits:
        errors.append("以下文件仍疑似包含旧标识（旧包名/旧scheme/旧Service），请检查：\n  - " + "\n  - ".join(old_hits))

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="代码仓库根目录（包含 flutter/）")
    ap.add_argument("--old-package", default="com.carriez.flutter_hbb")
    ap.add_argument("--new-package", default="com.celonis.work")
    ap.add_argument("--old-app-name", default="RustDesk")
    ap.add_argument("--new-app-name", default="ToddDesk")
    ap.add_argument("--old-scheme", default="rustdesk")
    ap.add_argument("--new-scheme", default="todddesk")
    ap.add_argument("--old-service", default="InputService")
    ap.add_argument("--new-service", default="ToddService")
    ap.add_argument("--accessibility-desc", default="Made by Todd")
    ap.add_argument("--move-kotlin-dir", action="store_true", help="迁移 kotlin 包目录（建议开启）")
    ap.add_argument("--report", default="", help="输出一个 Markdown 报告（包含 diff）")
    ap.add_argument("--dry-run", action="store_true", help="只生成报告/检查，不落盘写文件")
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
        print(f"[ERR] 未找到 flutter/android：{android_root}")
        return 2

    rules = build_rules(cfg)

    changed_files: List[str] = []
    diffs: List[str] = []

    # 先做文本替换
    for f in iter_text_files(android_root):
        old = read_text(f)
        new = apply_regex_rules(old, rules)
        if new != old:
            rel = str(f.relative_to(repo))
            changed_files.append(rel)
            diffs.append(unified_diff(old, new, rel))
            if not args.dry_run:
                write_text(f, new)

    # 再迁移 kotlin 目录
    moved_old, moved_new = None, None
    if args.move_kotlin_dir and not args.dry_run:
        moved_old, moved_new = move_kotlin_dir(repo, cfg)

    # 校验
    errors = validate(repo, android_root, cfg)

    # 报告
    if args.report:
        rp = repo / args.report
        lines = []
        lines.append("# RustDesk Android Patch Report\n")
        lines.append(f"- old_package: `{cfg.old_package}`\n")
        lines.append(f"- new_package: `{cfg.new_package}`\n")
        lines.append(f"- old_app_name: `{cfg.old_app_name}` -> new_app_name: `{cfg.new_app_name}`\n")
        lines.append(f"- old_scheme: `{cfg.old_scheme}` -> new_scheme: `{cfg.new_scheme}`\n")
        lines.append(f"- old_service: `{cfg.old_service}` -> new_service: `{cfg.new_service}`\n\n")
        lines.append(f"## Changed files ({len(changed_files)})\n")
        for x in changed_files:
            lines.append(f"- `{x}`\n")
        lines.append("\n")

        if moved_old is not None and moved_new is not None:
            lines.append("## Kotlin dir move\n")
            lines.append(f"- from: `{moved_old}`\n")
            lines.append(f"- to: `{moved_new}`\n\n")

        lines.append("## Validation\n")
        if errors:
            lines.append("❌ Failed\n\n")
            for e in errors:
                lines.append(f"- {e}\n")
        else:
            lines.append("✅ Passed\n")
        lines.append("\n")

        lines.append("## Diff (truncated per file if too large)\n")
        for d in diffs:
            # 防止报告过大：每个文件最多 400 行
            dl = d.splitlines()
            if len(dl) > 400:
                dl = dl[:400] + ["... (truncated)"]
            lines.append("```diff\n" + "\n".join(dl) + "\n```\n\n")

        if not args.dry_run:
            write_text(rp, "".join(lines))

    print(f"[OK] scanned flutter/android, changed_files={len(changed_files)}, dry_run={args.dry_run}")
    if errors:
        print("[ERR] validation failed:")
        for e in errors:
            print(" -", e)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
