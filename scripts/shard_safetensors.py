# 담당: [통합] Vercel 컨테이너 이미지의 체크포인트 레이어 패키징.
# 구현할 기능: safetensors 텐서 바이트를 값 변경 없이 제한 크기의 샤드로 나눈다.
# 완료 기준: 원본 모델 가중치의 dtype·shape·값을 보존하고 Hugging Face 샤드 인덱스를 만든다.
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

MAX_SHARD_BYTES = 350 * 1024 * 1024
HEADER_LENGTH_BYTES = 8
COPY_CHUNK_BYTES = 1024 * 1024


def _read_checkpoint_header(path: Path) -> tuple[int, dict[str, Any]]:
    with path.open("rb") as checkpoint:
        length_bytes = checkpoint.read(HEADER_LENGTH_BYTES)
        if len(length_bytes) != HEADER_LENGTH_BYTES:
            raise ValueError("checkpoint is missing its safetensors header length")
        header_length = struct.unpack("<Q", length_bytes)[0]
        header_bytes = checkpoint.read(header_length)
        if len(header_bytes) != header_length:
            raise ValueError("checkpoint safetensors header is truncated")
    header = json.loads(header_bytes)
    if not isinstance(header, dict) or not header:
        raise ValueError("checkpoint safetensors header is invalid")
    return HEADER_LENGTH_BYTES + header_length, header


def _group_tensors(
    header: dict[str, Any], *, data_size: int, max_shard_bytes: int
) -> tuple[list[list[tuple[str, dict[str, Any]]]], dict[str, Any] | None, int]:
    metadata = header.pop("__metadata__", None)
    tensors = sorted(
        header.items(), key=lambda item: item[1]["data_offsets"][0]
    )
    groups: list[list[tuple[str, dict[str, Any]]]] = []
    current: list[tuple[str, dict[str, Any]]] = []
    current_size = 0
    expected_offset = 0

    for name, tensor in tensors:
        start, end = tensor["data_offsets"]
        tensor_size = end - start
        if start != expected_offset or tensor_size < 0:
            raise ValueError(f"checkpoint tensor offsets are invalid at {name}")
        if tensor_size > max_shard_bytes:
            raise ValueError(f"tensor exceeds the configured shard size: {name}")
        if current and current_size + tensor_size > max_shard_bytes:
            groups.append(current)
            current = []
            current_size = 0
        current.append((name, tensor))
        current_size += tensor_size
        expected_offset = end

    if current:
        groups.append(current)
    if expected_offset != data_size:
        raise ValueError("checkpoint tensor offsets do not cover the complete data section")
    if not groups:
        raise ValueError("checkpoint contains no tensors")
    return groups, metadata, expected_offset


def _write_shard(
    source: Path,
    destination: Path,
    group: list[tuple[str, dict[str, Any]]],
    *,
    source_data_offset: int,
    metadata: dict[str, Any] | None,
) -> dict[str, int]:
    output_header: dict[str, Any] = {}
    tensor_sizes: dict[str, int] = {}
    destination_offset = 0
    for name, tensor in group:
        start, end = tensor["data_offsets"]
        size = end - start
        output_header[name] = {
            "dtype": tensor["dtype"],
            "shape": tensor["shape"],
            "data_offsets": [destination_offset, destination_offset + size],
        }
        tensor_sizes[name] = size
        destination_offset += size
    if metadata is not None:
        output_header["__metadata__"] = metadata

    header_bytes = json.dumps(output_header, separators=(",", ":")).encode("utf-8")
    padding = (-len(header_bytes)) % 8
    if padding:
        header_bytes += b" " * padding

    with source.open("rb") as source_file, destination.open("wb") as shard_file:
        shard_file.write(struct.pack("<Q", len(header_bytes)))
        shard_file.write(header_bytes)
        for _, tensor in group:
            start, end = tensor["data_offsets"]
            source_file.seek(source_data_offset + start)
            remaining = end - start
            while remaining:
                block = source_file.read(min(remaining, COPY_CHUNK_BYTES))
                if not block:
                    raise ValueError("checkpoint tensor data is truncated")
                shard_file.write(block)
                remaining -= len(block)
    return tensor_sizes


def shard_checkpoint(
    snapshot_dir: Path, output_dir: Path, *, max_shard_bytes: int = MAX_SHARD_BYTES
) -> None:
    checkpoint_path = snapshot_dir / "model.safetensors"
    index_path = snapshot_dir / "model.safetensors.index.json"
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"pinned checkpoint was not found: {checkpoint_path}")
    if index_path.exists():
        raise FileExistsError(f"refusing to overwrite an existing shard index: {index_path}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty shard directory: {output_dir}")

    source = checkpoint_path.resolve(strict=True)
    source_size = source.stat().st_size
    source_data_offset, header = _read_checkpoint_header(source)
    groups, metadata, tensor_bytes = _group_tensors(
        header,
        data_size=source_size - source_data_offset,
        max_shard_bytes=max_shard_bytes,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    weight_map: dict[str, str] = {}
    for number, group in enumerate(groups, start=1):
        filename = f"model-{number:05d}-of-{len(groups):05d}.safetensors"
        shard_weight_map = _write_shard(
            source,
            output_dir / filename,
            group,
            source_data_offset=source_data_offset,
            metadata=metadata,
        )
        weight_map.update({name: filename for name in shard_weight_map})

    index = {
        "metadata": {"total_size": tensor_bytes},
        "weight_map": weight_map,
    }
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    checkpoint_path.unlink()
    if source != checkpoint_path:
        source.unlink()

    sizes = [path.stat().st_size for path in sorted(output_dir.glob("*.safetensors"))]
    if len(sizes) != len(groups) or max(sizes) > max_shard_bytes + 1024 * 1024:
        raise ValueError("generated safetensors shards do not meet the configured size bound")
    print(
        f"Created {len(sizes)} byte-preserving shards; "
        f"source bytes={source_size}; tensor bytes={tensor_bytes}; "
        f"largest shard bytes={max(sizes)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="safetensors 체크포인트를 값 변경 없이 제한 크기의 샤드로 나눕니다."
    )
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--max-shard-bytes", type=int, default=MAX_SHARD_BYTES)
    arguments = parser.parse_args()
    shard_checkpoint(
        arguments.snapshot_dir,
        arguments.output_dir,
        max_shard_bytes=arguments.max_shard_bytes,
    )


if __name__ == "__main__":
    main()
