"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
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
