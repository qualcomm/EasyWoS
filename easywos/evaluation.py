"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from sanic import Blueprint

from sanic_jwt.decorators import protected

from helper import evaluation_helper

evaluation = Blueprint("evaluation", url_prefix="/evaluation")


@evaluation.get('/')
@protected()
async def get_evaluation_task(request):
    id = request.args.get('id')
    host = request.args.get('host')
    page_num = int(request.args.get('page_num', 1))
    page_size = int(request.args.get('page_size', 20))
    result = await evaluation_helper.list_evaluation_task(page_num=page_num, page_size=page_size, id=id, host=host)
    return result


@evaluation.delete('/<id>')
@protected()
async def delete_evaluation_task(request, id):
    result = await evaluation_helper.delete_evaluation_task(
        id=id
    )
    return result


@evaluation.post('/')
@protected()
async def post_create_ance_task(request):
    data = request.json
    machine_id = data.get('machine_id')
    target_os_release = data.get('target_os_release')
    target_arch = data.get('target_arch')
    res = await evaluation_helper.create_evaluation_task(
        machine_id=machine_id,
        target_os_release=target_os_release,
        target_arch=target_arch
    )
    return res


@evaluation.get('/<id>')
@protected()
async def get_evaluation_task_by_id(request, id):
    res = await evaluation_helper.query_evaluation_by_id(
        id=id
    )
    return res


@evaluation.get('/result')
@protected()
async def get_evaluation_task_result(request):
    id = request.args.get('id')
    type = request.args.get('type')
    result = await evaluation_helper.get_evaluation_task_result(id=id, type=type)
    return result
