"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from distutils.core import setup
from Cython.Build import cythonize
from Cython.Distutils import build_ext
import os

cur_dir = os.path.abspath(os.path.dirname(__file__))
setup_file = os.path.split(__file__)[1]

ext_modules = []

# get all build files
for path, dirs, files in os.walk(cur_dir, topdown=True):
    for file_name in files:
        file = os.path.join(path, file_name)
        if os.path.splitext(file)[1] == '.py':
            if file_name != setup_file:
                ext_modules.append(file)

setup(
    ext_modules=cythonize(
        ext_modules,
        compiler_directives=dict(
            always_allow_keywords=True,
            c_string_encoding='utf-8',
            language_level=3
        )
    ),
    cmdclass=dict(
        build_ext=build_ext
    ),
    script_args=["build_ext", "-b", './build', "-t", './tmp']
)
