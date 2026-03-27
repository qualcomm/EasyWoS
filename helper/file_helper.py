"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
import os
import datetime
import aiofiles
from util.common import datetime_toString_without_space
from util.command import execute_linux_command
from util.http import rsp
from sanic.response import file_stream
from util.const import WORKSPACE_PATH, FILE_TEMPORY_PATH


async def upload_file(file):

    await execute_linux_command(f'mkdir -p {FILE_TEMPORY_PATH}')
    today = datetime_toString_without_space(datetime.datetime.today())
    path = os.path.join(FILE_TEMPORY_PATH, f'{today}_{file.name}')
    async with aiofiles.open(path, 'wb') as f:
        await f.write(file.body)

    return {
        'code': 200,
        'message': 'Success',
        'data': {
            'file_path': path
        }
    }


async def delete_file(relative_path):
    if not relative_path:
        return {
            'code': 400,
            'message': 'Invalid request',
            'data': {
                'file_path': relative_path
            }
        }
    file_path = os.path.join(os.getcwd(), relative_path)
    if not os.path.exists(file_path):
        return {
            'code': 400,
            'message': 'File Not Found',
            'data': {
                'file_path': relative_path
            }
        }

    os.remove(file_path)

    return {
        'code': 200,
        'message': 'Success',
        'data': {
            'file_path': file_path
        }
    }


async def get_file(relative_path):
    if not relative_path:
        return rsp(code=400, message='Invalid request')
    file_path = os.path.join(os.getcwd(), relative_path)
    if not os.path.exists(file_path):
        return rsp(code=400, message='File Not Found', data={'file_path': relative_path})
    return await file_stream(file_path)


async def download_file(relative_path, file_name):
    if not relative_path:
        return rsp(code=400, message='Invalid request')
    file_path = os.path.join(os.getcwd(), relative_path)
    if not os.path.exists(file_path):
        return rsp(code=400, message='File Not Found', data={'file_path': relative_path})
    headers = {'Content-Disposition': f'attachment; filename={file_name}'}
    return await file_stream(file_path, headers=headers)


async def check_disk_space():
    result, error, code = await execute_linux_command(f'df -h {WORKSPACE_PATH} | tail -n 1 | awk \'{{print $4}}\'')
    return rsp(data=result)
