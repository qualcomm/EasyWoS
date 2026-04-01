"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
import os
import logging
import logging.config
from util.const import WORKSPACE_PATH


class SanicLog(object):

    def __init__(self):
        self.logger = None

    def init_app(self, app):
        # 1. 确保日志目录存在
        log_dir = os.path.join(WORKSPACE_PATH, 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 2. 加载 logging.conf 配置文件
        # 假设 logging.conf 在项目根目录下
        conf_path = os.path.join(os.getcwd(), 'logging.conf')
        
        # 如果是在 Docker 或其他环境中，可能需要调整路径，这里使用绝对路径更安全
        if os.path.exists(conf_path):
            logging.config.fileConfig(conf_path, disable_existing_loggers=False)
        else:
            print(f"Warning: Logging configuration file not found at {conf_path}")

        # 3. 获取 logger 实例
        self.logger = logging.getLogger("sanic.root")


log = SanicLog()
