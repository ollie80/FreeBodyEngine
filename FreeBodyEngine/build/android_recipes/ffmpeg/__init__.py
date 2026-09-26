from pythonforandroid.toolchain import Recipe, current_directory, shprint
import os
from os.path import exists, join, realpath
import sh
from multiprocessing import cpu_count


class FFMpegRecipe(Recipe):
    """Local override of p4a's stock `ffmpeg` recipe (see
    `FreeBodyEngine/build/builder.py`'s `_write_local_p4a_recipes()` for how
    this gets placed at the build root so p4a picks it up in place of the
    upstream one), fixing two issues found building/running phonon on a
    real device:

    1. The upstream recipe only copies the built `ffmpeg` binary into the
       app's native libs (as `libffmpegbin.so`, symlinked to `.bin/ffmpeg`
       on-device by the sdl2 bootstrap - see its own `start.c`) - `ffprobe`
       is built right alongside it by the same `make install` but never
       copied anywhere, so it's silently absent from every app despite
       yt-dlp's FFmpegExtractAudio postprocessor needing both (its error
       for either missing is the confusingly-combined "ffprobe and ffmpeg
       not found"). Copied here the same way, as `libffprobebin.so`, so the
       bootstrap's own `.bin/<name>` symlinking (strips "lib" and "bin.so")
       produces a `.bin/ffprobe` next to `.bin/ffmpeg` for free.

    2. The upstream recipe links ffmpeg against this build's bundled
       OpenSSL purely to give ffmpeg its own HTTPS protocol handler
       (`--enable-openssl`/`--enable-protocol=https,tls_openssl`) whenever
       an `openssl` recipe happens to be in the build at all - which it
       always is here, needed by Python's own `ssl` module, entirely
       unrelated to ffmpeg. This engine never uses that protocol handler
       (audio downloads go through yt-dlp/requests; ffmpeg is only ever
       invoked locally, as a postprocessor on an already-downloaded file),
       but linking it in was confirmed live on a real device (Samsung
       Galaxy A17) to crash `ffmpeg` on every single launch:
       `CANNOT LINK EXECUTABLE ".../.bin/ffmpeg": cannot locate symbol
       "OpenSSL_add_all_algorithms" referenced by "/system/lib64/
       libsqlite.so"` - Android's linker unconditionally pulls its own
       system libsqlite.so into any executable's process image, and on
       this device/vendor image that system library needs a legacy OpenSSL
       1.x symbol our bundled OpenSSL 3.x build doesn't export; since our
       own libcrypto.so is first in the search path, the system's own
       (presumably compatible) crypto provider never gets a chance to
       satisfy it, and the process aborts before ffmpeg's main() runs at
       all. Simply never linking ffmpeg against libssl/libcrypto sidesteps
       the whole clash - it doesn't need them for anything this engine
       actually uses it for.
    """

    version = '8.0.1'
    url = 'https://www.ffmpeg.org/releases/ffmpeg-{version}.tar.xz'
    depends = [('sdl2', 'sdl3')]
    opts_depends = ['openssl', 'ffpyplayer_codecs', 'av_codecs']
    patches = ['patches/configure.patch', 'patches/backport-Android15-MediaCodec-fix.patch']
    _libs = [
        "libavcodec.so",
        "libavfilter.so",
        "libavutil.so",
        "libswscale.so",
        "libavdevice.so",
        "libavformat.so",
        "libswresample.so",
        "libffmpegbin.so",
        "libffprobebin.so",
    ]
    built_libraries = dict.fromkeys(_libs, "./lib")

    def should_build(self, arch):
        build_dir = self.get_build_dir(arch.arch)
        return not exists(join(build_dir, 'lib', 'libavcodec.so'))

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env['NDK'] = self.ctx.ndk_dir
        return env

    def build_arch(self, arch):
        with current_directory(self.get_build_dir(arch.arch)):
            env = arch.get_env()

            cflags = []
            ldflags = []

            # enable hardware acceleration codecs
            flags = [
                '--enable-jni',
                '--enable-mediacodec'
            ]

            # No --enable-openssl/https here - see this recipe's own
            # docstring for why linking ffmpeg against OpenSSL at all
            # crashes it outright on some devices, for a protocol handler
            # this engine never uses in the first place.

            # yt-dlp's FFmpegExtractAudio always shells out to the real
            # `libvorbis` encoder for `preferredcodec: "vorbis"` - never
            # ffmpeg's own separate, unrelated native "vorbis" encoder (see
            # yt_dlp/postprocessor/ffmpeg.py's ACODECS table: the tuple's
            # middle element, `'libvorbis'`, is the literal `-acodec` value
            # it passes) - so only `--enable-libvorbis` (linking the real
            # external library) actually registers the encoder yt-dlp will
            # ask for by that exact name; enabling ffmpeg's own "vorbis"
            # instead just leaves it looking for an encoder that was never
            # registered, indistinguishable at the call site from having no
            # Vorbis support at all. Optional exactly like openssl above -
            # only linked when the project's own dependencies list actually
            # requested the `libvorbis`/`libogg` p4a recipes.
            if 'libvorbis' in self.ctx.recipe_build_order:
                flags += ['--enable-libvorbis']
                # configure's own pkg-config auto-detection looks for a
                # cross-prefixed binary (`aarch64-linux-android24-
                # pkg-config`) that doesn't exist in this NDK toolchain -
                # confirmed via ffbuild/config.log: it silently falls back
                # to the shell builtin `false` instead of the real,
                # perfectly usable system `pkg-config` on PATH, so no
                # PKG_CONFIG_PATH/PKG_CONFIG_LIBDIR setting can fix this on
                # its own - `--exists vorbis` always "fails" against
                # `false` regardless of what it's pointed at. This
                # overrides that autodetection outright, same as any
                # ./configure script's usual escape hatch for exactly this
                # cross-compile mismatch.
                flags += ['--pkg-config=pkg-config']
                vorbis_build_dir = Recipe.get_recipe('libvorbis', self.ctx).get_build_dir(arch.arch)
                ogg_build_dir = Recipe.get_recipe('libogg', self.ctx).get_build_dir(arch.arch) \
                    if 'libogg' in self.ctx.recipe_build_order else None
                vorbis_lib_dir = join(vorbis_build_dir, 'lib', '.libs')
                vorbis_inc_dir = join(vorbis_build_dir, 'include')
                cflags += ['-I' + vorbis_inc_dir]
                ldflags += ['-L' + vorbis_lib_dir, '-lvorbis', '-lvorbisenc']
                ogg_lib_dir = ogg_inc_dir = None
                if ogg_build_dir:
                    ogg_lib_dir = join(ogg_build_dir, 'src', '.libs')
                    ogg_inc_dir = join(ogg_build_dir, 'include')
                    cflags += ['-I' + ogg_inc_dir]
                    ldflags += ['-L' + ogg_lib_dir, '-logg']

                # --enable-libvorbis's own configure-time check
                # (check_pkg_config) shells out to real pkg-config (given
                # --pkg-config= above) to look up the "vorbis"/"vorbisenc"
                # modules, using WHATEVER Libs/Cflags fields that module's
                # .pc file declares - not the -I/-L/-l flags set manually
                # above, which only cover ffmpeg's own later compile/link
                # steps once the check itself has already passed. Pointing
                # PKG_CONFIG_PATH directly at libvorbis's/libogg's own
                # build dirs (where their unmodified `./configure` already
                # wrote real vorbis.pc/vorbisenc.pc/ogg.pc files) does NOT
                # work, for two independent reasons confirmed live via
                # ffbuild/config.log: (1) autotools writes `prefix=
                # /usr/local` into these by default (neither recipe passes
                # its own real build dir as `--prefix=`, since neither
                # ever runs `make install`), so libdir/includedir resolve
                # to a nonexistent /usr/local/... path instead of the
                # actual build output; (2) pkg-config prefers an
                # `X-uninstalled.pc` sibling over the plain `X.pc` when
                # both sit in the same searched directory (exactly the
                # case here) - its Libs: field points straight at the raw
                # `libvorbis.la` libtool wrapper, meant to be consumed by
                # `libtool --mode=link`, not handed to a raw linker
                # invocation the way ffmpeg's configure does it: clang
                # fails outright on `.la`'s own internal syntax ("unknown
                # directive: dlname="). Writing minimal, correct .pc files
                # of this recipe's own from scratch - real absolute paths,
                # no "-uninstalled" sibling anywhere alongside them -
                # sidesteps both problems at once.
                pkgconfig_dir = join(self.get_build_dir(arch.arch), '_pkgconfig')
                os.makedirs(pkgconfig_dir, exist_ok=True)

                def _write_pc(name, description, version, libdir, includedir, libs, requires=''):
                    with open(join(pkgconfig_dir, name + '.pc'), 'w') as f:
                        f.write(
                            f'libdir={libdir}\n'
                            f'includedir={includedir}\n\n'
                            f'Name: {name}\n'
                            f'Description: {description}\n'
                            f'Version: {version}\n'
                            f'Requires: {requires}\n'
                            f'Libs: -L${{libdir}} {libs}\n'
                            f'Cflags: -I${{includedir}}\n'
                        )

                if ogg_build_dir:
                    _write_pc('ogg', 'Ogg bitstream library', '1.3.3', ogg_lib_dir, ogg_inc_dir, '-logg')
                _write_pc('vorbis', 'Vorbis codec library', '1.3.6', vorbis_lib_dir, vorbis_inc_dir, '-lvorbis', requires='ogg')
                _write_pc('vorbisenc', 'Vorbis encoder library', '1.3.6', vorbis_lib_dir, vorbis_inc_dir, '-lvorbisenc', requires='vorbis')

                existing_pkg_config_path = env.get('PKG_CONFIG_PATH', '')
                env['PKG_CONFIG_PATH'] = pkgconfig_dir + (':' + existing_pkg_config_path if existing_pkg_config_path else '')

            codecs_opts = {"ffpyplayer_codecs", "av_codecs"}
            if codecs_opts.intersection(self.ctx.recipe_build_order):

                # Enable GPL
                flags += ['--enable-gpl']

                # libx264
                flags += ['--enable-libx264']
                build_dir = Recipe.get_recipe(
                    'libx264', self.ctx).get_build_dir(arch.arch)
                cflags += ['-I' + build_dir + '/include/']
                # Newer versions of FFmpeg prioritize the dynamic library and ignore
                # the static one, unless the static library path is explicitly set.
                ldflags += [build_dir + '/lib/' + 'libx264.a']

                # libshine
                flags += ['--enable-libshine']
                build_dir = Recipe.get_recipe('libshine', self.ctx).get_build_dir(arch.arch)
                cflags += ['-I' + build_dir + '/include/']
                ldflags += ['-lshine', '-L' + build_dir + '/lib/']
                ldflags += ['-lm']

                # libvpx
                flags += ['--enable-libvpx']
                build_dir = Recipe.get_recipe(
                    'libvpx', self.ctx).get_build_dir(arch.arch)
                cflags += ['-I' + build_dir + '/include/']
                ldflags += ['-lvpx', '-L' + build_dir + '/lib/']

                # Enable all codecs:
                flags += [
                    '--enable-parsers',
                    '--enable-decoders',
                    '--enable-encoders',
                    '--enable-muxers',
                    '--enable-demuxers',
                ]
            else:
                # Enable codecs for .mp4 playback, plus everything needed
                # to actually decode a downloaded YouTube audio stream
                # (opus in a webm/matroska container, or aac in m4a -
                # yt-dlp's `bestaudio` picks whichever the source actually
                # has) and remux it into the .ogg container the enabled
                # `libvorbis` encoder above writes into (see this method's
                # own `--enable-libvorbis` block for the encoder itself -
                # a decoder/demuxer/muxer allowlist alone doesn't help
                # without that, and confirmed live on a real device: it's
                # what "audio conversion failed: Error opening output
                # files: Encoder not found" turned out to mean, despite
                # ffmpeg itself linking and running fine by this point).
                flags += [
                    '--enable-parser=aac,ac3,h261,h264,mpegaudio,mpeg4video,mpegvideo,vc1,opus,vorbis',
                    '--enable-decoder=aac,h264,mpeg4,mpegvideo,opus,vorbis,mp3',
                    '--enable-muxer=h264,mov,mp4,mpeg2video,ogg',
                    '--enable-demuxer=aac,h264,m4v,mov,mpegvideo,vc1,rtsp,ogg,matroska,mp3',
                ]

            # needed to prevent _ffmpeg.so: version node not found for symbol av_init_packet@LIBAVFORMAT_52
            # /usr/bin/ld: failed to set dynamic section sizes: Bad value
            flags += [
                '--disable-symver',
            ]

            # disable doc
            flags += [
                '--disable-doc',
            ]

            # other flags:
            flags += [
                '--enable-filter=aresample,resample,crop,adelay,volume,scale',
                '--enable-protocol=file,http,hls,udp,tcp',
                '--enable-small',
                '--enable-hwaccels',
                '--enable-pic',
                '--disable-static',
                '--disable-debug',
                '--enable-shared',
            ]

            if 'arm64' in arch.arch:
                arch_flag = 'aarch64'
            elif 'x86' in arch.arch:
                arch_flag = 'x86'
                flags += ['--disable-asm']
            else:
                arch_flag = 'arm'

            # android:
            flags += [
                '--target-os=android',
                '--enable-cross-compile',
                '--cross-prefix={}-'.format(arch.target),
                '--arch={}'.format(arch_flag),
                '--strip={}'.format(self.ctx.ndk.llvm_strip),
                '--nm={}'.format(self.ctx.ndk.llvm_nm),
                '--sysroot={}'.format(self.ctx.ndk.sysroot),
                '--enable-neon',
                '--prefix={}'.format(realpath('.')),
            ]

            if arch_flag == 'arm':
                cflags += [
                    '-Wno-error=incompatible-pointer-types',
                    '-mfpu=vfpv3-d16',
                    '-mfloat-abi=softfp',
                    '-fPIC',
                ]

            env['CFLAGS'] += ' ' + ' '.join(cflags)
            env['LDFLAGS'] += ' ' + ' '.join(ldflags)

            configure = sh.Command('./configure')
            shprint(configure, *flags, _env=env)
            shprint(sh.make, '-j', f"{cpu_count()}", _env=env)
            shprint(sh.make, 'install', _env=env)
            shprint(sh.cp, "ffmpeg", "./lib/libffmpegbin.so")
            shprint(sh.cp, "ffprobe", "./lib/libffprobebin.so")


recipe = FFMpegRecipe()
