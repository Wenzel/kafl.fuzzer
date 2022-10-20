"""
From https://gist.github.com/dmontagu/b91d5fd5319ae6fe004ecd28771d985e
"""
from typing import Any, Dict

from setuptools.command.build_ext import build_ext
from setuptools.extension import Extension


class ExtensionBuilder(build_ext):
    def run(self) -> None:
        super().run()

    def build_extension(self, ext: Extension) -> None:
        super().build_extension(ext)

def build(setup_kwargs: Dict[str, Any]) -> None:
    bitmap_ext = Extension(
        "kafl_fuzzer.native.bitmap",
        sources=['kafl_fuzzer/native/bitmap.c'],
        extra_compile_args=["-O3", "-fPIC", "-mtune=native"]
    )
    setup_kwargs.update(
        {
            "ext_modules": [bitmap_ext],
            "cmdclass": {
                build_ext: ExtensionBuilder
            },
        }
    )
