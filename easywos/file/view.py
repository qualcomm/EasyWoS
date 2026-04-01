"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from sanic.views import HTTPMethodView
from sanic.response import json
from sanic_ext import openapi
from sanic_jwt.decorators import protected

from .namespace import file
from helper import file_helper


class FileView(HTTPMethodView):
    # decorators = [protected()]

    async def post(self, request):
        file = request.files.get('file')
        res = await file_helper.upload_file(
            file=file
        )
        return json(res)

    @openapi.parameter("file_path", str, required=True)
    async def delete(self, request):
        file_path = request.args.get('file_path')
        result = await file_helper.delete_file(relative_path=file_path)
        return json(result)

    @openapi.parameter("file_path", str, required=True)
    async def get(self, request):
        file_path = request.args.get('file_path')
        result = await file_helper.get_file(relative_path=file_path)
        return result


class FileDownLoadView(HTTPMethodView):
    @openapi.parameter("file_path", str, required=True)
    @openapi.parameter("file_name", str, required=True)
    async def get(self, request):
        file_path = request.args.get('file_path')
        file_name = request.args.get('file_name')
        result = await file_helper.download_file(relative_path=file_path, file_name=file_name)
        return result


class SpaceView(HTTPMethodView):
    decorators = [protected()]

    async def get(self, request):
        res = await file_helper.check_disk_space()
        return res


file.add_route(FileView.as_view(), "/")
file.add_route(FileDownLoadView.as_view(), "/download")
file.add_route(SpaceView.as_view(), "/space")
