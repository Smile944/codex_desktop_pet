"""Build minimal FFmpeg + libvpx + libwebp using only macOS Command Line Tools.

Run for each release architecture. Ship media-source.tar.gz alongside releases;
it contains the unmodified sources, this recipe, lock, and license notices.
"""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from media_runtime import CACHE, load_lock, verify_file


def run(args, directory, env):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=directory, env=env, check=True)


def sources(lock):
    directory = CACHE / 'sources'
    directory.mkdir(parents=True, exist_ok=True)
    for record in lock['sources'].values():
        archive = directory / record['filename']
        supplied = Path(__file__).resolve().parents[1] / record['filename']
        if not archive.exists() and supplied.is_file():
            verify_file(supplied, record['sha256'])
            shutil.copy2(supplied, archive)
        if not archive.exists():
            partial = archive.with_suffix(archive.suffix + '.part')
            # Explicit proxy also handles macOS system proxy settings.
            args = ['curl', '--fail', '--location', '--connect-timeout', '20', '--max-time', '240', '--retry', '2']
            proxy = urllib.request.getproxies().get('https')
            if proxy: args += ['--proxy', proxy]
            subprocess.run(args + ['--output', str(partial), record['url']], check=True)
            verify_file(partial, record['sha256'])
            partial.replace(archive)
        verify_file(archive, record['sha256'])
        target = directory / record['directory']
        if not target.exists():
            with tarfile.open(archive) as bundle:
                for entry in bundle.getmembers():
                    location = directory / entry.name
                    if not location.resolve().is_relative_to(directory.resolve()):
                        raise ValueError('Source archive path escapes extraction root')
                bundle.extractall(directory)
    return directory


def write_pkg_config(pkg, prefix, python=None):
    code = ('import sys\na=sys.argv[1:]\n' +
        'if "--version" in a: print("0.29.2"); sys.exit(0)\n' +
        'known={"vpx":"1.14.1","libwebp":"1.4.0"}\n' +
        'mods=[x for x in a if x in known]\n' +
        'if not mods: sys.exit(1)\n' +
        'if "--modversion" in a: print(known[mods[0]])\n' +
        f'if "--cflags" in a: print("-I{prefix}/include")\n' +
        f'if "--libs" in a: print("-L{prefix}/lib " + " ".join("-lvpx -lm -lpthread" if m=="vpx" else "-lwebp -lsharpyuv -lm" for m in mods))\n')
    pkg.write_text('#!/bin/sh\nexec ' + shlex.quote(str(python or sys.executable)) +
                   ' -c ' + shlex.quote(code) + ' "$@"\n')
    pkg.chmod(0o755)


def build(arch):
    lock = load_lock()
    src = sources(lock)
    work = CACHE / arch / 'build'
    prefix = work / 'prefix'
    work.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(LC_ALL='C', LANG='C', MACOSX_DEPLOYMENT_TARGET='13.0', ZERO_AR_DATE='1')
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    flags = f'-arch {arch} -isysroot {sdk} -mmacosx-version-min=13.0 -O2'
    env.update(CC='clang', CXX='clang++', CFLAGS=flags, CXXFLAGS=flags, LDFLAGS=flags)
    jobs = str(min(os.cpu_count() or 2, 8))
    records = lock['sources']
    vpx = work / 'libvpx'
    vpx.mkdir(exist_ok=True)
    run([src / records['libvpx']['directory'] / 'configure', f'--prefix={prefix}', '--target=generic-gnu',
         '--disable-examples', '--disable-tools', '--disable-docs', '--disable-unit-tests',
         '--disable-vp8', '--disable-vp9-encoder', '--enable-vp9-decoder', '--disable-webm-io',
         '--disable-runtime-cpu-detect', '--enable-pic'], vpx, env)
    run(['make', '-j' + jobs], vpx, env)
    run(['make', 'install'], vpx, env)
    webp = work / 'libwebp'
    webp.mkdir(exist_ok=True)
    webp_host = 'aarch64-apple-darwin' if arch == 'arm64' else 'x86_64-apple-darwin'
    run([src / records['libwebp']['directory'] / 'configure', f'--prefix={prefix}', f'--host={webp_host}',
         '--disable-shared', '--enable-static', '--disable-gl', '--disable-sdl', '--disable-png',
         '--disable-jpeg', '--disable-tiff', '--disable-gif', '--disable-libwebpmux', '--disable-libwebpdemux'], webp, env)
    run(['make', '-j' + jobs], webp, env)
    run(['make', 'install'], webp, env)
    # Our two static dependencies are the entire pkg-config search domain.
    # This tiny adapter removes a Homebrew/pkg-config prerequisite.
    pkg = work / 'media-pkg-config'
    write_pkg_config(pkg, prefix)
    ffmpeg = work / 'ffmpeg'
    ffmpeg.mkdir(exist_ok=True)
    run([src / records['ffmpeg']['directory'] / 'configure', '--disable-everything', '--disable-autodetect',
         '--disable-gpl', '--disable-nonfree', '--disable-version3', '--disable-doc', '--disable-debug',
         '--disable-shared', '--enable-static', '--disable-ffplay', '--disable-ffprobe', '--disable-x86asm',
         '--disable-network', '--enable-ffmpeg', '--enable-libvpx', '--enable-libwebp',
         '--enable-decoder=libvpx_vp9', '--enable-encoder=libwebp', '--enable-demuxer=matroska',
         '--enable-muxer=image2,webp,rawvideo,null', '--enable-protocol=file,pipe',
         '--enable-filter=fps,crop,scale,pad,format,alphaextract', '--enable-encoder=rawvideo,wrapped_avframe',
         '--enable-swscale', '--enable-avfilter', '--target-os=darwin', f'--arch={arch}',
         '--enable-cross-compile', '--cc=clang', f'--extra-cflags={flags}', f'--extra-ldflags={flags}',
         f'--pkg-config={pkg}', f'--prefix={prefix}'], ffmpeg, env)
    run(['make', '-j' + jobs], ffmpeg, env)
    output = CACHE / arch / 'ffmpeg'
    shutil.copy2(ffmpeg / 'ffmpeg', output)
    output.chmod(0o755)
    subprocess.run(['codesign', '--force', '--sign', '-', '--identifier', 'org.ffmpeg.ffmpeg', str(output)], check=True)
    license_text = subprocess.check_output([str(output), '-hide_banner', '-L'], text=True, stderr=subprocess.STDOUT)
    if 'GNU Lesser General Public License' not in ' '.join(license_text.split()) or 'not legally redistributable' in license_text:
        raise RuntimeError('Unexpected FFmpeg distribution license')
    (CACHE / arch / 'LICENSE-ffmpeg.txt').write_text(license_text)
    binary_record = {'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'size': output.stat().st_size,
              'license': 'LGPL-2.1-or-later', 'builtFrom': {k: v['sha256'] for k, v in records.items()}}
    lock = load_lock()
    lock['binaries'][arch] = binary_record
    Path(__file__).with_name('media-lock.json').write_text(json.dumps(lock, indent=2) + '\n')
    licenses = Path(__file__).with_name('media-licenses')
    licenses.mkdir(exist_ok=True)
    for component, names in {'ffmpeg':['COPYING.LGPLv2.1', 'LICENSE.md'], 'libvpx':['LICENSE', 'PATENTS', 'AUTHORS'],
                             'libwebp':['COPYING', 'PATENTS', 'AUTHORS']}.items():
        for name in names:
            source = src / records[component]['directory'] / name
            if source.exists(): shutil.copy2(source, licenses / (component + '-' + name + '.txt'))
    with tarfile.open(CACHE / 'media-source.tar.gz', 'w:gz') as archive:
        for record in records.values(): archive.add(src / record['filename'], arcname=record['filename'])
        for name in ('build_media.py', 'media_runtime.py', 'media-lock.json'):
            archive.add(Path(__file__).with_name(name), arcname='codex/' + name)
        archive.add(licenses, arcname='codex/media-licenses')
    print(json.dumps({'arch': arch, 'binary': str(output), **binary_record}), flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=('arm64', 'x86_64'), required=True)
    build(parser.parse_args().arch)
