"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
import os
import sys


class GitUtils(object):

    @staticmethod
    def __run_cmd(self, cmd):
        os.system(cmd)

    @staticmethod
    def clone(cls, repo, options=None):
        GitUtils.run_cmd('git clone %s' % repo)
