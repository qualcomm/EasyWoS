"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from ruamel import yaml
from .checkpoint import Checkpoint
from .crypto_file import encrypt_checkpoints, decrypt_aes
import os
import time


def init_checkpoints(checkpoints, exclude_checkpoints=[]):

    _checkpoints = []

    exclude_checkpoints_names = [Checkpoint(_).func_name for _ in exclude_checkpoints]

    for _ in checkpoints:
        cp = Checkpoint(_)

        if cp.pattern:
            _checkpoints.append(cp)
            continue

        if cp.func_name not in exclude_checkpoints_names:
            _checkpoints.append(cp)
            continue

    return _checkpoints


start_time = time.time()

current_path = os.path.abspath(os.path.dirname(__file__))
check_points_yml = os.path.abspath(current_path + './../db/check_points.yaml')
check_points_aes = os.path.abspath(current_path + './../db/check_points.aes')

if os.path.isfile(check_points_yml):
    encrypt_checkpoints(check_points_yml, check_points_aes)

if not os.path.isfile(check_points_aes):
    raise RuntimeError('%s not found!' % check_points_aes)

with open(check_points_aes, 'rb') as f:
    l = f.read()

yaml_loader = yaml.YAML(typ='rt')
content = yaml_loader.load(decrypt_aes(l).decode('utf-8'))

end_time = time.time()
print('Loading of check_points.aes took %f seconds.' % (end_time - start_time))

start_time = time.time()

#  aarch64
AARCH64_INTRINSICS = content["COMMON_INTRINSICS"] + content["AARCH64_INTRINSICS"]

AARCH64_INCOMPATIBLE_INTRINSICS = init_checkpoints(
    content['X86_INTRINSICS'] +
    content['INCOMPATIBLE_UCRT_INTRINSICS'], AARCH64_INTRINSICS)

AARCH64_COMPILER_OPTION_CHECKPOINTS = init_checkpoints(
    content["AARCH64_COMPILER_OPTION_CHECKPOINTS"])

AARCH64_INLINE_ASSEMBLY_CHECKPOINTS = init_checkpoints(
    content["AARCH64_INLINE_ASSEMBLY_CHECKPOINTS"])

#  arm64ec
ARM64EC_INCOMPATIBLE_GRAMMAR = init_checkpoints(
    content['ARM64EC_INCOMPATIBLE_GRAMMAR'])

#  x86/64
X86_PRAGMA = init_checkpoints(content['X86_PRAGMA'])

#  CPP std lib suggestions
CPP_STD_CODES = init_checkpoints(content['CPP_STD_CODES'])

#  CPP header file suggestions
INCOMPATIBLE_HEADER_FILE = init_checkpoints(content['INCOMPATIBLE_HEADER_FILE'])

# please remember to remove lines for profiling after optimizing :)
end_time = time.time()
print('Initialization of checkpoints took %f seconds.' % (end_time - start_time))
