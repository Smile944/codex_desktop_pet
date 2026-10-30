"""Locate the pinned, locally built LGPL media converter. No runtime downloads."""
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'codex/dist/media-cache'


def load_lock():
    return json.loads(Path(__file__).with_name('media-lock.json').read_text())


def verify_file(path, sha256):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()
    if digest != sha256:
        raise ValueError(f'Media checksum mismatch: {path}')
    return path


def resolve_ffmpeg(resources=None, explicit=None):
    if explicit is not None:
        path = Path(explicit).resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f'Media converter is not executable: {path}')
        return path
    arch = platform.machine()
    root = Path(resources) if resources is not None else ROOT
    candidates = [root / 'media/ffmpeg']
    if resources is None or root.resolve() == ROOT:
        candidates.append(CACHE / arch / 'ffmpeg')
    for path in candidates:
        if path.is_file():
            record = load_lock().get('binaries', {}).get(arch)
            if not record:
                raise ValueError(f'No pinned media converter for {arch}')
            verify_file(path, record['sha256'])
            if not os.access(path, os.X_OK):
                raise ValueError(f'Media converter is not executable: {path}')
            return path
    raise FileNotFoundError('Media converter missing; build it with codex/build_media.py or provide an explicit ffmpeg path.')


def ensure_media(arch):
    if arch not in ('arm64', 'x86_64'):
        raise ValueError(f'Unsupported media architecture: {arch}')
    path = CACHE / arch / 'ffmpeg'
    record = load_lock().get('binaries', {}).get(arch)
    if path.is_file() and record:
        verify_file(path, record['sha256'])
        return path
    subprocess.run([sys.executable, str(Path(__file__).with_name('build_media.py')), '--arch', arch], check=True)
    record = load_lock().get('binaries', {}).get(arch)
    if not record:
        raise ValueError('Built media binary has no checksum record')
    return verify_file(path, record['sha256'])
