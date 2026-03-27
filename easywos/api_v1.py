"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from sanic import Blueprint
from easywos.user.view import user
from easywos.machine.view import machine
from easywos.task.view import task
from easywos.file.view import file
from easywos.evaluation import evaluation

api_v1 = Blueprint.group(user, machine, task, file, evaluation, url_prefix='/api')
