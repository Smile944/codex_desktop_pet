The media converter is a separate FFmpeg executable built from FFmpeg 7.1
(LGPL-2.1-or-later), libvpx 1.14.1 (BSD-3-Clause), and libwebp 1.4.0
(BSD-3-Clause). The application invokes it as a child process to import
VP9-alpha WebM character packs. No GPL or nonfree FFmpeg features are enabled.
No imageio binary is distributed.

`codex/media-lock.json` records source archive SHA256 hashes, URLs, and each
release binary checksum. The exact build recipe is `codex/build_media.py`.
Original copyright notices, license texts, patent grants, and author lists
are retained beside this file and in the complete source archives.

Release maintainers must distribute `media-source.tar.gz` beside the application
downloads on the same release. It contains all three complete, unmodified
upstream source archives, the build recipe, lock, and license notices. This is
the corresponding source for the separately distributed media executable;
the source archive must remain available for as long as that release binary.
The binary's `-L` and `-buildconf` output identify its license and build options.

To rebuild, extract `media-source.tar.gz` into an empty folder, then run
`python3 codex/build_media.py --arch arm64` or
`python3 codex/build_media.py --arch x86_64` on macOS with Xcode Command Line
Tools installed. Python 3.9 or newer, clang, make, ar and the macOS SDK suffice;
Homebrew, CMake, NASM and pkg-config are not required. Source archives in the
extracted folder are reused without a network request. Output is written to
`codex/dist/media-cache/<arch>/ffmpeg`. Original source files are not patched.
Compiler/SDK differences can change the binary checksum; a new release must
record the checksum from its actual build, and must include its corresponding
source archive. Configure logs stay in the local build cache; the source
archive includes the reproducible recipe without local environment dumps.
