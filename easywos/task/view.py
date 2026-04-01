"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from sanic.views import HTTPMethodView
from sanic_ext import openapi
from sanic_ext.extensions.openapi.definitions import RequestBody
from sanic_jwt.decorators import protected

from .namespace import task
from .profile import TaskProfile, UpdateTaskProfile
from helper import task_helper


class TaskView(HTTPMethodView):
    decorators = [protected()]

    @openapi.parameter("id", int, required=False)
    @openapi.parameter("name", str, required=False)
    @openapi.parameter("page_num", int, required=False)
    @openapi.parameter("page_size", int, required=False)
    async def get(self, request):
        id = request.args.get('id')
        name = request.args.get('name')
        page_num = int(request.args.get('page_num', 1))
        page_size = int(request.args.get('page_size', 20))
        result = await task_helper.list_task(page_num=page_num, page_size=page_size, id=id, name=name)
        return result

    @openapi.body(RequestBody(TaskProfile, required=True))
    async def post(self, request):
        data = request.json
        res = await task_helper.create_task(
            data=data
        )
        return res

    # @openapi.parameter("id", int, required=True)
    # @openapi.body(RequestBody(UpdateTaskProfile))
    # async def put(self, request):
    #     id = request.args.get('id')

    #     data = request.json
    #     res = await task_helper.update_task(
    #         id=id,
    #         data=data
    #     )
    #     return res

    # @openapi.parameter("id", int, required=False)
    # async def delete(self, request):
    #     id = request.args.get('id')
    #     result = await task_helper.delete_task(id=id)
    #     return result


class TaskByIdView(HTTPMethodView):
    async def get(self, request, id):
        res = await task_helper.query_task_by_id(
            id=id
        )
        return res

    @openapi.body(RequestBody(UpdateTaskProfile))
    async def put(self, request, id):
        data = request.json
        res = await task_helper.update_task(
            id=id,
            data=data
        )
        return res

    async def delete(self, request, id):
        res = await task_helper.delete_task(
            id=id
        )
        return res


class TaskRunView(HTTPMethodView):
    async def post(self, request, id):
        res = await task_helper.run_task(
            id=id
        )
        return res


class TaskResultByIdView(HTTPMethodView):
    async def delete(self, request, id):
        res = await task_helper.delete_task_result(
            id=id
        )
        return res


class TaskResultDetailView(HTTPMethodView):
    async def get(self, request, id):
        res = await task_helper.query_task_result_by_id(
            id=id
        )
        return res


class TaskResultJsonlView(HTTPMethodView):
    async def get(self, request, id):
        res = await task_helper.query_task_result_json_by_id(
            id=id
        )
        return res


task.add_route(TaskView.as_view(), "/")
task.add_route(TaskRunView.as_view(), "/run/<id>")
task.add_route(TaskByIdView.as_view(), "/<id>")
task.add_route(TaskResultByIdView.as_view(), "/result/<id>")
task.add_route(TaskResultDetailView.as_view(), "/result/detail/<id>")
task.add_route(TaskResultJsonlView.as_view(), "/result/json/<id>")
