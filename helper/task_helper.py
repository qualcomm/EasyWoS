"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
import os
import datetime
import asyncio
import aiofiles
import json
import filetype
import zipfile
import tarfile
import rarfile
from jinja2 import Environment, FileSystemLoader
from typing import Union

from app.log import log

from sanic import json as sanic_json
from sanic.response import file_stream

from models.task import Task, TaskResult
from util.http import rsp
from util.common import datetime_toString_without_space, datetime_toString
from util.const import WORKSPACE_PATH
from util.command import execute_linux_command, execute_linux_command_with_log_redirect
from util.command import execute_linux_command_without_log_redirect
from .scanner_helper import generate_scan_command


async def list_task(page_num, page_size, id=None, name=None):
    """

    :return:
    """

    condition = dict()
    if id:
        condition['id'] = id
    if name:
        condition['name'] = name
    tasks = await Task.query_page(page_num=page_num, page_size=page_size, condition=condition, desc=True)
    # columns = [
    #     'name', 'userid', 'file_path', 'language', 'repeat_type'
    # ]
    # taskList = [task.serialize(columns=columns) for task in tasks]
    return rsp(data=tasks)


async def create_task(data) -> rsp:
    if data.get('language') and data.get('language').lower() == 'c/c++/asm':
        data['language'] = 'cpp'

    # Pre-save Validation
    if data.get('method') == 'git':
        # upload via git repo
        repo_url = data.get('file_path')
        branch = data.get('branch')
        
        if not repo_url.startswith('http://') and not repo_url.startswith('https://'):
             return rsp(code=500, message='Invalid git repository URL. Only HTTP/HTTPS is supported.')

        if not repo_url.endswith('.git'):
             return rsp(code=500, message='Invalid git repository URL. URL should end with .git')

        if branch:
            check_branch_cmd = f'git ls-remote --heads {repo_url} {branch}'
            stdout, stderr, code = await execute_linux_command(check_branch_cmd)
            if code != 0:
                 return rsp(code=500, message=f'Failed to check branch: {stderr}')
            
            if not any(line.endswith(f'refs/heads/{branch}') for line in stdout.splitlines()):
                 return rsp(code=500, message=f'Branch "{branch}" not found in repository.')
    else:
        temp_path = data.get('file_path')
        kind = filetype.guess(temp_path)
        supported_extensions = ['zip', 'tar', 'gz', 'xz', 'rar']
        if not kind or kind.extension not in supported_extensions:
             await execute_linux_command(f'rm -f {temp_path}')
             return rsp(code=500, message=f'Unsupported file type {kind.extension if kind else "None"}. Supported types: {", ".join(supported_extensions)}')

    task, message, http_code = await Task().save(data)
    if not task:
        # If file upload mode, temp file is still there?
        if data.get('method') != 'git':
             temp_path = data.get('file_path')
             await execute_linux_command(f'rm -f {temp_path}')
        return rsp(code=http_code, message=message)
    columns = [
        'name', 'userid', 'file_path', 'language', 'repeat_type', 'locale', 'build_tool'
    ]
    response_data = {
        'task': task.serialize(columns=columns)
    }
    scan_path = os.path.join(WORKSPACE_PATH, 'codescan', f'{task.id}', 'src')

    # this part is to handle git repo clone
    if data.get('method') == 'git':
        repo_url = data.get('file_path')
        branch = data.get('branch')
        commit = data.get('commit')

        await execute_linux_command(f'mkdir -p {os.path.dirname(scan_path)}')
        cmd = f'git clone {repo_url} {scan_path}'
        if branch:
            cmd += f' -b {branch}'
        
        try:
            # Set timeout to 10 minutes (600 seconds)
            stdout, stderr, code = await asyncio.wait_for(execute_linux_command(cmd), timeout=600)
            if code != 0:
                await Task.delete(Task.id == task.id)
                await execute_linux_command(f'rm -rf {os.path.dirname(scan_path)}')
                return rsp(code=500, message=f'Git clone failed: {stderr}')
        except asyncio.TimeoutError:
            await Task.delete(Task.id == task.id)
            await execute_linux_command(f'rm -rf {os.path.dirname(scan_path)}')
            return rsp(code=500, message='Git clone timeout (exceeded 10 minutes)')

        if commit:
             cmd = f'cd {scan_path} && git checkout {commit}'
             stdout, stderr, code = await execute_linux_command(cmd)
             if code != 0:
                 await Task.delete(Task.id == task.id)
                 await execute_linux_command(f'rm -rf {os.path.dirname(scan_path)}')
                 return rsp(code=500, message=f'Git checkout failed: {stderr}')

        stdout, stderr, code = await execute_linux_command(f'du -sb {scan_path}')
        if code == 0:
            try:
                size = int(stdout.split()[0])
                if size > 2 * 1024 * 1024 * 1024:
                    await execute_linux_command(f'rm -rf {scan_path}')
                    await Task.delete(Task.id == task.id)
                    return rsp(code=500, message='Git repository size exceeds 2GB limit.')
            except Exception as e:
                log.logger.error(f'Check git repo size failed: {e}')

        task.file_path = scan_path
        await task.update()
    # this part is to handle file upload
    else:
        temp_path = data.get('file_path')
        # We already validated file type.
        
        filename = os.path.basename(temp_path)
        await execute_linux_command(f'mkdir -p {scan_path} && cp {temp_path} {scan_path}')
        task.file_path = os.path.join(scan_path, filename)
        await task.update()

        unzip_file_path = await unzip_file(task.file_path)
        log.logger.info(f'unzip_file_path: {unzip_file_path}')
        await execute_linux_command(f'rm -f {temp_path}')
    return rsp(code=http_code, message=message, data=response_data or None)


async def update_task(id, data) -> rsp:
    tasks = await Task.query(Task.id == id)
    if not tasks:
        return rsp(code=400, message=f'Task {id} doesn\'t exist')
    task = tasks[0]
    language = data.get('language')
    repeat_type = data.get('repeat_type')
    description = data.get('description')
    locale = data.get('locale')
    build_tool = data.get('build_tool')
    if language is not None:
        if language.lower() == 'c/c++/asm':
            language = 'cpp'
        task.language = language
    if repeat_type:
        task.repeat_type = repeat_type
    if description:
        task.description = description
    if locale:
        task.locale = locale
    if build_tool:
        task.build_tool = build_tool
    await task.update()
    return rsp(message=f'Update Task {id} success', code=200)


async def delete_task(id) -> rsp:
    tasks = await Task.delete(Task.id == id)
    print(tasks)
    return rsp()


async def query_task_by_id(id):
    """

    :return:
    """

    tasks = await Task.query(Task.id == id)
    task_columns = [
        'name', 'userid', 'file_path', 'language', 'repeat_type', 'arch', 'description', 'issue_found'
    ]
    if not tasks:
        return rsp(code=401, message=f'task {id} not exist')
    task = tasks[0].serialize(columns=task_columns)
    task_results = await TaskResult.query(TaskResult.task_id == id)
    task_result_columns = [
        'task_id', 'result_file_path', 'result_status', 'language', 'log_path', 'issue_found'
    ]
    task_result_list = [task_result.serialize(columns=task_result_columns) for task_result in task_results]
    data = dict(
        task=task,
        task_results=task_result_list
    )
    return rsp(data=data)


async def update_task_result(future, task_result: TaskResult, status: str):
    task_result.result_status = status
    await task_result.update()


async def query_task_result_by_id(id):
    """

    :return:
    """

    task_results = await TaskResult.query(TaskResult.id == id)
    if not task_results:
        return rsp(code=401, message=f'task result {id} not exist')
    result_file_path = task_results[0].result_file_path
    res = await file_stream(result_file_path)
    return res


async def delete_task_result(id) -> rsp:
    task_results = await TaskResult.query(TaskResult.id == id)
    if not task_results:
        return rsp(code=401, message=f'task result {id} not exist')
    for task in asyncio.all_tasks():
        if task.get_name() == task_results[0].name:
            task.cancel()
            await task
    await TaskResult.delete(TaskResult.id == id)
    return rsp(message=f'Delete task result {id} success')


async def query_task_result_json_by_id(id):
    """

    :return:
    """

    task_results = await TaskResult.query(TaskResult.id == id)
    if not task_results:
        return rsp(code=401, message=f'task result {id} not exist')
    result_file_path = task_results[0].result_file_path.split('html')[0] + 'json'
    json_content = await read_json_file(result_file_path)

    return sanic_json(json_content, ensure_ascii=False)


async def run_task(id) -> rsp:
    tasks = await Task.query(Task.id == id)
    if not tasks:
        return rsp(code=400, message=f'Task {id} doesn\'t exist')
    task = tasks[0]
    language_list = [language.strip().lower() for language in task.language.split(',')]
    arch = task.arch if task.arch else 'arm64'
    build_tool = task.build_tool
    log.logger.debug(f'run_task receive arch: {arch}')
    log.logger.debug(f'run_task receive locale: {task.locale}')
    current_time = datetime_toString_without_space(datetime.datetime.today())

    task_result_to_added = dict(
        task_id=id
    )

    task_result, message, http_code = await TaskResult().save(task_result_to_added)
    if http_code != 200:
        return rsp(message=message, http_code=http_code)

    scan_path = os.path.dirname(task.file_path)
    result_folder_path = os.path.join(WORKSPACE_PATH, 'codescan', str(task.id), str(task_result.id))
    await execute_linux_command(f'mkdir -p {result_folder_path}')
    result_path = f'{result_folder_path}/{task.name}_{current_time}'
    code_scan_task = asyncio.create_task(
        execute_code_scan(
            task=task,
            task_result=task_result,
            file_path=task.file_path,
            language_list=language_list,
            result_path=result_path,
            arch=arch,
            scan_path=scan_path,
            locale=task.locale,
            build_tool=build_tool
        ),
        name=f'code_scan_task_{task.name}_{task_result.id}'
    )
    task_result.name = code_scan_task.get_name()
    return rsp()


async def unzip_file(file_path):
    unzip_file_path = ''
    work_path = os.path.dirname(file_path)

    kind = filetype.guess(file_path)
    if not kind:
        return
    log.logger.info(f'file extension: {kind.extension}')

    if kind.extension == 'zip':
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(work_path)
                print(zip_ref.namelist()[0])
                unzip_file_path = os.path.join(work_path, zip_ref.namelist()[0])
        except Exception as e:
            print(e)

    elif kind.extension in ['tar', 'gz', 'xz']:
        with tarfile.open(file_path, 'r') as tar_ref:
            tar_ref.extractall(work_path)
            print(tar_ref.getnames()[0])
            unzip_file_path = os.path.join(work_path, tar_ref.getnames()[0])

    elif kind.extension == 'rar':
        try:
            with rarfile.RarFile(file_path, 'r') as rar_ref:
                rar_ref.extractall(work_path)
                unzip_file_path = os.path.join(work_path)
        except Exception as e:
            print(e)

    return unzip_file_path


async def execute_code_scan(
    task: Task, task_result: TaskResult,
    file_path: str, language_list: list,
    result_path: str, arch: str, scan_path: str,
    locale: str, build_tool: str = None
):
    task_result.result_status = 'scanning'
    task_result.log_path = f'{result_path}.log'
    await task_result.update()
    command_dict = generate_scan_command(
        language_list=language_list,
        result_path=result_path,
        arch=arch,
        scan_path=scan_path,
        file_path=file_path,
        log_name=result_path,
        locale=locale,
        build_tool=build_tool
    )

    result_path, generate_report_success, issue_found = await generate_report(
        file_path=file_path,
        language_list=language_list,
        command_dict=command_dict,
        result_path=result_path,
        log_path=task_result.log_path,
        arch=arch,
        locale=locale
    )
    if generate_report_success:
        task_result.result_status = 'success'
        task_result.result_file_path = result_path
        task_result.issue_found = issue_found
    else:
        task_result.result_status = 'fail'
    await task_result.update()

    if generate_report_success:
        task.issue_found = issue_found
        await task.update()


async def generate_report(
    file_path, command_dict, result_path, language_list, log_path, arch, locale
) -> tuple[str, bool, Union[None, bool]]:
    result_union = dict(
        language_types=language_list,
        all_issues=[],
        file_summary={},
        root_directory=file_path,
        date=datetime_toString(datetime.datetime.today()),
        arch=arch,
        git_repo='',
        commit='',
        branch='',
        hostIp=''
    )
    language_scan_task_list = []
    for language in command_dict:
        log.logger.info(f'language: {language}')
        command = command_dict.get(language).get('cmd')
        task = scan_code_task(language, command, log_path)
        language_scan_task_list.append(task)

    # language_scan_task_results = await asyncio.gather(*language_scan_task_list)
    try:
        language_scan_task_results = await asyncio.gather(*language_scan_task_list)
    except asyncio.CancelledError as e:
        log.logger.info(e)
        return None, False, None
    except Exception as e:
        log.logger.error(e)
        await execute_linux_command(f'echo "load json result fail" >> {log_path}')
        return None, False, None

    try:
        issue_found = False
        for language_scan_task_result in language_scan_task_results:
            if language_scan_task_result.get('code') == 0:
                result_file_path = command_dict.get(language_scan_task_result.get('language')).get('result_file_path')
                language_scan_task_result_json = await read_json_file(result_file_path)
                if language_scan_task_result_json.get('total_issue_count') != 0:
                    issue_found = True
                result_union['file_summary'].update(language_scan_task_result_json.get('file_summary'))
                result_union['all_issues'].append(language_scan_task_result_json)
    except Exception as e:
        log.logger.error(e)
        await execute_linux_command(f'echo "load json result fail" >> {log_path}')
        return None, False, None

    json_file_path = f'{result_path}.json'
    try:
        async with aiofiles.open(json_file_path, 'w') as f:
            await f.write(json.dumps(result_union))
    except Exception as e:
        log.logger.error(e)
        await execute_linux_command(f'echo "generate json result {json_file_path} fail" >> {log_path}')
        return None, False, issue_found

    await execute_linux_command(f'echo "generate json result {json_file_path} success" >> {log_path}')
    log.logger.info(f'generate json result union file {json_file_path} success')

    html_file_path = f'{result_path}.html'
    generate_report_success = await create_report(
        json_file_path=json_file_path, html_file_path=html_file_path, log_path=log_path, locale=locale
    )
    if not generate_report_success:
        return None, False, issue_found
    return html_file_path, True, issue_found


async def scan_code_task(language, command, log_path):
    await execute_linux_command(f'echo "Scan {language} begin" >> {log_path}')

    try:
        if language in ['python', 'java']:
            code = await asyncio.wait_for(execute_linux_command_without_log_redirect(command), timeout=28800)
        else:
            code = await asyncio.wait_for(execute_linux_command_with_log_redirect(command, log_path), timeout=28800)
        await execute_linux_command(f'echo "Scan {language} end" >> {log_path}')
    except asyncio.TimeoutError:
        code = 99
        log.logger.error(f'Scan {language} timeout')
        await execute_linux_command(f'echo "Scan {language} timeout" >> {log_path}')
    return dict(
        language=language,
        code=code,
        log_path=log_path
    )


async def read_json_file(filename):
    async with aiofiles.open(filename, mode='r') as f:
        content = await f.read()
        return json.loads(content)


async def create_report(json_file_path, html_file_path, log_path, locale):

    data = await read_json_file(json_file_path)
    templateLoader = FileSystemLoader(searchpath="./templates")
    env = Environment(loader=templateLoader)

    template = env.get_template('advice.html')

    file_sum_count = 0
    file_sum_loc = 0
    for file_type in data['file_summary']:
        file_sum_count += data['file_summary'][file_type]['count']
        if "loc" in data['file_summary'][file_type]:
            loc = data['file_summary'][file_type]['loc']
            if (loc is None or loc == 0):
                data['file_summary'][file_type]['loc'] = "-"
            else:
                file_sum_loc += loc
        else:
            data['file_summary'][file_type]["loc"] = "-"

    if data.get('march') is None or data['march'] == "":
        data['march'] = "-"
    try:
        rendered = template.render(
            root_directory=data['root_directory'],
            file_summary=data['file_summary'],
            file_sum_count=file_sum_count,
            file_sum_loc=file_sum_loc,
            march=data['march'],
            language_types=data['language_types'],
            date=data['date'],
            arch=data['arch'],
            all_issues=data['all_issues'],
            git_repo=data['git_repo'],
            commit=data['commit'],
            branch=data['branch'],
            locale=locale
        )
    except Exception as e:
        log.logger.error(e)
        await execute_linux_command(f'echo "generate report {html_file_path} success" >> {log_path}')
        return False
    try:
        async with aiofiles.open(html_file_path, 'w') as f:
            await f.write(rendered)
        await execute_linux_command(f'echo "generate report {html_file_path} success" >> {log_path}')
        log.logger.info(f'generate report {html_file_path} success')
    except Exception as e:
        log.logger.error(e)
        await execute_linux_command(f'echo "generate report {html_file_path} fail" >> {log_path}')
        return False
    return True
