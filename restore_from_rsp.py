#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 rsp 文件（base64 编码的压缩包）还原并解压。
支持 RAR 格式；若为 ZIP 则用标准库解压。
"""

import base64
import os
import sys
import zipfile
from pathlib import Path


def get_project_root() -> Path:
    """脚本所在目录视为项目根目录。"""
    return Path(__file__).resolve().parent


def load_base64_from_rsp(rsp_path: Path) -> bytes:
    """从 rsp 文件读取并去除空白后做 base64 解码。"""
    text = rsp_path.read_text(encoding="utf-8").strip()
    return base64.b64decode(text)


def detect_archive_format(data: bytes) -> str:
    """根据文件头判断压缩格式。"""
    if data[:4] == b"Rar!":
        return "rar"
    if data[:2] == b"PK":
        return "zip"
    return "unknown"


def save_archive(data: bytes, out_path: Path) -> Path:
    """将解码后的数据写入文件。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return out_path


def extract_zip(archive_path: Path, extract_dir: Path) -> None:
    """解压 ZIP。"""
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(extract_dir)
    print(f"  已解压到: {extract_dir}")


def extract_rar(archive_path: Path, extract_dir: Path) -> None:
    """解压 RAR（需安装 rarfile 且系统有 unrar）。"""
    try:
        import rarfile
    except ImportError:
        print("  未安装 rarfile，请执行: pip install rarfile")
        print("  Windows 需安装 UnRAR 并将 unrar 加入 PATH")
        print(f"  或手动解压: {archive_path}")
        return
    try:
        with rarfile.RarFile(archive_path, "r") as rf:
            rf.extractall(extract_dir)
        print(f"  已解压到: {extract_dir}")
    except Exception as e:
        print(f"  自动解压失败: {e}")
        print("  请安装 UnRAR (https://www.rarlab.com/rar_add.htm) 或手动解压 restored.rar")


def main() -> None:
    root = get_project_root()
    # 默认 rsp 路径：项目内 test-simulator/tests/rsp
    default_rsp = root / "test-simulator" / "tests" / "rsp"
    rsp_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_rsp

    if not rsp_path.exists():
        print(f"错误: 找不到文件 {rsp_path}")
        sys.exit(1)

    print(f"读取: {rsp_path}")
    data = load_base64_from_rsp(rsp_path)
    fmt = detect_archive_format(data)

    if fmt == "unknown":
        print("错误: 无法识别的压缩格式（仅支持 RAR/ZIP）")
        sys.exit(1)

    # 还原的压缩包放在项目根目录
    archive_name = f"restored.{fmt}"
    archive_path = root / archive_name
    save_archive(data, archive_path)
    print(f"已还原压缩包: {archive_path}")

    # 解压到同名的目录
    extract_dir = root / "restored_extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    print(f"正在解压 ({fmt}) ...")
    if fmt == "zip":
        extract_zip(archive_path, extract_dir)
    else:
        extract_rar(archive_path, extract_dir)


if __name__ == "__main__":
    main()
