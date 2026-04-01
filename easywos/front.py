"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from sanic import Blueprint
from easywos.page.view import page

page = Blueprint.group(page)
