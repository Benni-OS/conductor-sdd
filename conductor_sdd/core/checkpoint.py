"""Atomic workspace checkpoint and cryptographic SHA-256 rollback protocol."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from conductor_sdd.spec import ConductorSpec

CHECKPOINTS_DIR = Path(".conductor/checkpoints")


@dataclass(slots=True)
class CheckpointInfo:
    """Metadata describing an immutable workspace checkpoint."""

    checkpoint_id: str
    label: str
    created_at: float
    file_count: int
    root_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _should_ignore(rel_parts: tuple[str, ...], ignored: set[str]) -> bool:
    return any(part in ignored for part in rel_parts)


def create_checkpoint(
    root: str | Path,
    spec: ConductorSpec,
    label: str = "manual-checkpoint",
) -> CheckpointInfo:
    """Snapshot tracked workspace files into `.conductor/checkpoints/<id>` with SHA-256 hashes."""
    base = Path(root).resolve()
    ignored = {p.strip("/\\") for p in spec.scope.ignored_paths} | {".conductor", ".git"}

    files_meta: dict[str, str] = {}
    root_hasher = hashlib.sha256()

    candidates: list[tuple[str, Path]] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if _should_ignore(rel.parts, ignored):
            continue
        if path.suffix.lower() in {".py", ".yaml", ".yml", ".json", ".toml", ".md"}:
            candidates.append((rel.as_posix(), path))

    for rel_posix, src in candidates:
        digest = _sha256_file(src)
        files_meta[rel_posix] = digest
        root_hasher.update(f"{rel_posix}:{digest}\n".encode())

    root_sha256 = root_hasher.hexdigest()
    checkpoint_id = f"{int(time.time())}_{root_sha256[:8]}"
    cp_dir = base / CHECKPOINTS_DIR / checkpoint_id
    files_dir = cp_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    for rel_posix, src in candidates:
        dest = files_dir / rel_posix
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    info = CheckpointInfo(
        checkpoint_id=checkpoint_id,
        label=label,
        created_at=time.time(),
        file_count=len(candidates),
        root_sha256=root_sha256,
    )
    manifest = {
        "info": info.to_dict(),
        "files": files_meta,
    }
    (cp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return info


def list_checkpoints(root: str | Path) -> list[CheckpointInfo]:
    """List available checkpoints sorted newest-first."""
    base = Path(root).resolve()
    cp_root = base / CHECKPOINTS_DIR
    if not cp_root.exists():
        return []

    found: list[CheckpointInfo] = []
    for entry in cp_root.iterdir():
        manifest_path = entry / "manifest.json"
        if entry.is_dir() and manifest_path.exists():
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            found.append(CheckpointInfo(**raw["info"]))

    return sorted(found, key=lambda c: c.created_at, reverse=True)


def rollback_checkpoint(
    root: str | Path,
    checkpoint_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Verify stored hashes and restore workspace files to the specified (or latest) checkpoint."""
    base = Path(root).resolve()
    available = list_checkpoints(base)
    if not available:
        raise FileNotFoundError("No checkpoints found under `.conductor/checkpoints`.")

    target_id = checkpoint_id or available[0].checkpoint_id
    cp_dir = base / CHECKPOINTS_DIR / target_id
    manifest_path = cp_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Checkpoint `{target_id}` does not exist.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files_meta: dict[str, str] = manifest["files"]
    files_dir = cp_dir / "files"

    # Pre-verify all stored artifacts before touching workspace files (atomic check)
    for rel_posix, expected_hash in files_meta.items():
        stored_file = (files_dir / rel_posix).resolve()
        if not str(stored_file).startswith(str(files_dir.resolve())):
            raise ValueError(f"Unsafe path in checkpoint manifest: {rel_posix}")
        if not stored_file.exists():
            raise FileNotFoundError(f"Missing artifact in checkpoint `{target_id}`: {rel_posix}")
        actual_hash = _sha256_file(stored_file)
        if actual_hash != expected_hash:
            raise ValueError(f"Checksum mismatch in checkpoint `{target_id}` for `{rel_posix}`.")

    restored: list[str] = []
    for rel_posix in sorted(files_meta):
        stored_file = files_dir / rel_posix
        dest_file = (base / rel_posix).resolve()
        if not str(dest_file).startswith(str(base)):
            raise ValueError(f"Unsafe destination path: {rel_posix}")
        needs_restore = not dest_file.exists() or _sha256_file(dest_file) != files_meta[rel_posix]
        if needs_restore:
            restored.append(rel_posix)
            if not dry_run:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(stored_file, dest_file)

    return {
        "checkpoint_id": target_id,
        "dry_run": dry_run,
        "verified_files": len(files_meta),
        "restored_files": restored,
    }
