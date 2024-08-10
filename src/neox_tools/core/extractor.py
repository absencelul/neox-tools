from __future__ import annotations

import os
import struct
import tempfile
import zipfile
import zlib
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple, Union, Callable

import lz4.block
import zstandard
from tqdm import tqdm

from neox_tools.core.key import Keys
from .rotor import NewRotor


class FileType(Enum):
    NXPK = auto()
    EXPK = auto()


class CompressionType(Enum):
    NONE = 0
    ZLIB = 1
    LZ4 = 2


@dataclass
class FileInfo:
    sign: Tuple[int, int]
    offset: int
    length: int
    original_length: int
    zcrc: int
    crc: int
    structure: Optional[bytes]
    compression_type: CompressionType
    flag: int


class NPKExtractor:
    def __init__(
        self,
        path: Union[str, Path],
        output_dir: Union[str, Path],
        no_nxfn=False,
        delete_compressed=False,
        max_workers=os.cpu_count(),
    ):
        self.path = Path(path)
        self.output_dir = Path(output_dir)
        self.no_nxfn = no_nxfn
        self.delete_compressed = delete_compressed
        self.keys = Keys()
        self.max_workers = max_workers

    def unpack(
        self, progress_callback: Optional[Callable[[float], None]] = None
    ) -> None:
        self.output_dir.mkdir(exist_ok=True)

        with self.path.open("rb") as f:
            try:
                file_type = self._read_file_type(f)
                file_count = self._read_uint32(f)
                _unknown = self._read_uint32(f)
                encryption_mode = self._read_uint32(f)
                _hash_mode = self._read_uint32(f)
                index_offset = self._read_uint32(f)

                nxfn_files = self._read_nxfn_files(
                    f, file_count, index_offset, encryption_mode
                )
                index_table = self._read_index_table(
                    f, file_count, index_offset, file_type, nxfn_files
                )

                self._extract_files_parallel(
                    f, index_table, file_type, progress_callback
                )
            except ValueError as e:
                print(f"\nValue Error: Unpacking {self.path.stem}, {e}\n")
                self.output_dir.rmdir()
            except Exception as e:
                print(f"\nError: Unpacking {self.path.stem}, {e}\n")
                self.output_dir.rmdir()

    @staticmethod
    def _read_file_type(f: BinaryIO) -> FileType:
        data = f.read(4)
        if data == b"NXPK":
            return FileType.NXPK
        elif data == b"EXPK":
            return FileType.EXPK
        else:
            raise ValueError("Not a valid NXPK/EXPK file")

    @staticmethod
    def _read_uint32(f: BinaryIO) -> int:
        return struct.unpack("I", f.read(4))[0]

    @staticmethod
    def _read_uint16(f: BinaryIO) -> int:
        return struct.unpack("H", f.read(2))[0]

    @staticmethod
    def _read_nxfn_files(
        f: BinaryIO, file_count: int, index_offset: int, encryption_mode: int
    ) -> List[bytes]:
        if encryption_mode != 256:
            return []

        f.seek(index_offset + (file_count * 28) + 16)
        nxfn_data = f.read()
        return [x for x in nxfn_data.split(b"\x00") if x]

    def _read_index_table(
        self,
        f: BinaryIO,
        file_count: int,
        index_offset: int,
        file_type: FileType,
        nxfn_files: List[bytes],
    ) -> List[FileInfo]:
        f.seek(index_offset)
        with tempfile.TemporaryFile() as tmp:
            data = f.read(file_count * 28)
            if file_type == FileType.EXPK:
                data = self.keys.decrypt(data)
            tmp.write(data)
            tmp.seek(0)

            return [
                self._read_file_info(tmp, nxfn_files[i] if nxfn_files else None)
                for i in range(file_count)
            ]

    def _read_file_info(
        self, tmp: BinaryIO, file_structure: Optional[bytes]
    ) -> FileInfo:
        return FileInfo(
            sign=(self._read_uint32(tmp), tmp.tell()),
            offset=self._read_uint32(tmp),
            length=self._read_uint32(tmp),
            original_length=self._read_uint32(tmp),
            zcrc=self._read_uint32(tmp),
            crc=self._read_uint32(tmp),
            structure=file_structure,
            compression_type=CompressionType(self._read_uint16(tmp)),
            flag=self._read_uint16(tmp),
        )

    def _extract_files_parallel(
        self,
        f: BinaryIO,
        index_table: List[FileInfo],
        file_type: FileType,
        progress_callback: Optional[Callable[[float], None]],
    ) -> None:
        total_files = len(index_table)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for i, file_info in enumerate(index_table):
                f.seek(file_info.offset)
                data = f.read(file_info.length)
                if file_type == FileType.EXPK:
                    data = self.keys.decrypt(data=data)
                futures.append(
                    executor.submit(
                        self._process_and_save_file,
                        data,
                        file_info,
                        i,
                    )
                )

            for i, future in enumerate(as_completed(futures)):
                future.result()
                if progress_callback:
                    progress_callback((i + 1) / total_files * 100)

    def _process_and_save_file(
        self,
        data: bytes,
        file_info: FileInfo,
        index: int,
    ) -> None:
        data = self._process_file_data(data, file_info)
        self._save_file(data, file_info, index)

    def _process_file_data(self, data: bytes, file_info: FileInfo) -> bytes:
        if file_info.flag in (3, 4):
            data = self._decrypt_file_data(data=data, file_info=file_info)

        ext = get_file_extension(data)

        if ext == "rot":
            data = self._process_rot_file(data)
        elif ext == "nxs3":
            data = self._process_nxs3_file(data)

        if file_info.compression_type != CompressionType.NONE and ext != "rot":
            data = self._decompress_data(
                data, file_info.compression_type, file_info.original_length
            )

        return data

    @staticmethod
    def _decrypt_file_data(data: bytes, file_info: FileInfo) -> bytes:
        if file_info.flag == 3:
            b = file_info.crc ^ file_info.original_length
            start = (
                (file_info.crc >> 1) % (file_info.length - 0x80)
                if file_info.length > 0x80
                else 0
            )
            size = (
                2 * file_info.original_length % 0x60 + 0x20
                if file_info.length > 0x80
                else file_info.length
            )

            key = [(x + b) & 0xFF for x in range(0x100)]
            data = bytearray(data)
            for j in range(size):
                data[start + j] ^= key[j % len(key)]
        elif file_info.flag == 4:
            offset = (
                (file_info.original_length >> 1) % (file_info.length - 0x80)
                if file_info.length >= 0x81
                else 0
            )
            length = (
                (((file_info.crc << 1) & 0xFFFFFFFF) % 0x60 + 0x20)
                if file_info.length >= 0x81
                else file_info.length
            )

            key = (file_info.original_length ^ file_info.crc) & 0xFF
            data = bytearray(data)

            for i in range(offset, min(offset + length, file_info.original_length)):
                data[i] ^= key
                key = (key + 1) & 0xFF

        return bytes(data)

    @staticmethod
    def _process_rot_file(data: bytes) -> bytes:
        rotor = init_rotor()
        data = rotor.decrypt(buffer=data)
        data = zlib.decompress(data)
        return NPKExtractor._reverse_string(s=data)

    @staticmethod
    def _process_nxs3_file(data: bytes) -> bytes:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        import subprocess

        subprocess.run(["./de_nxs3", tmp_path, f"{tmp_path}.out"], check=True)

        with open(f"{tmp_path}.out", "rb") as f:
            data = f.read()

        os.unlink(tmp_path)
        os.unlink(f"{tmp_path}.out")
        return data

    @staticmethod
    def _decompress_data(
        data: bytes, compression_type: CompressionType, original_length: int
    ) -> bytes:
        if compression_type == CompressionType.ZLIB:
            return zlib.decompress(data)
        elif compression_type == CompressionType.LZ4:
            return lz4.block.decompress(data, uncompressed_size=original_length)
        return data

    @staticmethod
    def _reverse_string(s: bytes) -> bytes:
        return bytes(reversed(bytes(x ^ 154 for x in s[:128]) + s[128:]))

    def _save_file(self, data: bytes, file_info: FileInfo, index: int) -> None:
        ext = get_file_extension(data)

        if file_info.structure and not self.no_nxfn:
            file_path = self.output_dir / file_info.structure.decode().replace(
                "\\", "/"
            )
        else:
            file_path = self.output_dir / f"{index:08}.{ext}"

        file_path.parent.mkdir(parents=True, exist_ok=True)

        if ext == "zst":
            if not self.delete_compressed:
                (file_path.with_suffix(".zst")).write_bytes(data)
            dctx = zstandard.ZstdDecompressor()
            data = dctx.decompress(data)
            file_path.write_bytes(data)
        elif ext == "zip":
            file_path.write_bytes(data)
            with zipfile.ZipFile(file_path, "r") as zip_file:
                zip_file.extractall(file_path.with_suffix(""))
            if self.delete_compressed:
                file_path.unlink()
        else:
            file_path.write_bytes(data)


def get_file_extension(data: bytes) -> str:
    if not data:
        return "none"

    extension_map = {
        b"CocosStudio-UI": "coc",
        bytes([0x28, 0xB5, 0x2F, 0xFD]): "zst",
        b"SKELETON": "skeleton",
        b"%": "tpl",
        b"{": "json",
        b"hit": "hit",
        b"PKM": "pkm",
        b"PVR": "pvr",
        b"DDS": "dds",
        b"BM": "bmp",
        b"from typing import ": "pyi",
        b"KTX": "ktx",
        b"PNG": "png",
        b"VANT": "vant",
        b"MDMP": "mdmp",
        b"RGIS": "gis",
        b"NTRK": "ntrk",
        b"RIFF": "riff",
        b"BKHD": "bnk",
        b"-----BEGIN PUBLIC KEY-----": "pem",
        b"<": "xml",
        bytes([0x50, 0x4B, 0x03, 0x04]): "zip",
        bytes([0x50, 0x4B, 0x05, 0x06]): "zip",
        bytes([0x34, 0x80, 0xC8, 0xBB]): "mesh",
        bytes([0x14, 0x00, 0x00, 0x00]): "type1",
        bytes([0x04, 0x00, 0x00, 0x00]): "type2",
        bytes([0x00, 0x01, 0x00, 0x00]): "type3",
        bytes([0xE3, 0x00, 0x00, 0x00]): "pyc",
        bytes([0x63, 0x00, 0x00, 0x00]): "pyc",
    }

    for prefix, ext in extension_map.items():
        if data.startswith(prefix):
            return ext

    if data[-18:-2] == b"TRUEVISION-XFILE" or data[:3] in [
        bytes([0x00, 0x00, 0x02]),
        bytes([0x0D, 0x00, 0x02]),
    ]:
        return "tga"
    elif data[:2] in [bytes([0x28, 0xB5]), bytes([0x1D, 0x04]), bytes([0x15, 0x23])]:
        return "rot"
    elif data[7:15] == bytes([0x4E, 0x58, 0x53, 0x33, 0x03, 0x00, 0x00, 0x01]):
        return "nxs3"

    if len(data) < 1000000:
        lower_data = data.lower()
        if b"package google.protobuf" in lower_data:
            return "proto"
        if b"#ifndef google_protobuf" in lower_data:
            return "h"
        if b"#include <google/protobuf" in lower_data:
            return "cc"
        if any(
            keyword in lower_data
            for keyword in [b"void", b"main(", b"include", b"float"]
        ):
            return "shader"
        if b"technique" in lower_data or b"ifndef" in lower_data:
            return "shader"
        if b"?xml" in lower_data:
            return "xml"
        if b"<script" in lower_data:
            return "html"
        if b"javascript" in lower_data:
            return "js"
        if any(
            keyword in lower_data
            for keyword in [b"biped", b"bip001", b"bone", b"bone001", b"bip01"]
        ):
            return "model"
        if b"div.document" in lower_data:
            return "css"

    return "dat"


def init_rotor():
    asdf_dn = "j2h56ogodh3se"
    asdf_dt = "=dziaq."
    asdf_df = '|os=5v7!"-234'
    asdf_tm = (
        asdf_dn * 4
        + (asdf_dt + asdf_dn + asdf_df) * 5
        + "!"
        + "#"
        + asdf_dt * 7
        + asdf_df * 2
        + "*"
        + "&"
        + "'"
    )
    return NewRotor(key=asdf_tm)


def process_npk_file(
    npk_file: Path,
    output_dir: Path,
    no_nxfn: bool,
    delete_compressed: bool,
    max_workers: int = os.cpu_count(),
) -> None:
    """Process a single NPK file."""
    # Create a subdir in the output_dir for the current NPK file
    output_path = output_dir / npk_file.stem
    output_path.mkdir(parents=True, exist_ok=True)

    extractor = NPKExtractor(
        path=npk_file,
        output_dir=output_path,
        no_nxfn=no_nxfn,
        delete_compressed=delete_compressed,
        max_workers=max_workers,
    )

    # track progress
    with tqdm(total=100, desc=f"Extracting {npk_file.name}", unit="%") as pbar:

        def progress_callback(progress: float) -> None:
            pbar.update(progress - pbar.n)

        extractor.unpack(progress_callback=progress_callback)


def process_multiple_npk_files(
    npk_files: List[Path],
    output_dir: Path,
    no_nxfn: bool = False,
    delete_compressed: bool = False,
    max_workers: int = os.cpu_count(),
    progress_callback: Optional[Callable[[float], None]] = None,
) -> None:
    """Process multiple NPK files concurrently."""
    total_files = len(npk_files)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for npk_file in npk_files:
            future = executor.submit(
                process_single_npk_file,
                npk_file,
                output_dir,
                no_nxfn,
                delete_compressed,
                max_workers,
            )
            futures.append(future)

        # Use tqdm to track overall progress
        with tqdm(total=total_files, desc="Extracting NPK files", unit="file") as pbar:
            for future in as_completed(futures):
                future.result()
                pbar.update(1)
                if progress_callback:
                    progress_callback(pbar.n / total_files * 100)


def process_single_npk_file(
    npk_file: Path,
    output_dir: Path,
    no_nxfn: bool,
    delete_compressed: bool,
    max_workers: int,
) -> None:
    """Process a single NPK file with internal concurrency."""
    output_path = output_dir / npk_file.stem
    output_path.mkdir(parents=True, exist_ok=True)

    extractor = NPKExtractor(
        path=npk_file,
        output_dir=output_path,
        no_nxfn=no_nxfn,
        delete_compressed=delete_compressed,
        max_workers=max_workers,
    )

    # Use a thread-safe progress bar for each NPK file
    with tqdm(
        total=100, desc=f"Extracting {npk_file.name}", unit="%", position=1, leave=False
    ) as pbar:

        def file_progress_callback(progress: float) -> None:
            pbar.update(progress - pbar.n)

        extractor.unpack(progress_callback=file_progress_callback)
