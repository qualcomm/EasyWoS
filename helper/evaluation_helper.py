"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
import os
import json
import csv
import asyncssh
import asyncio
from util.http import rsp
from models.machine import Machine
from models.evaluation import Evaluation
from app.log import log
from util.command import execute_linux_command
from util.const import WORKSPACE_PATH


async def list_evaluation_task(page_num, page_size, id=None, host=None):
    """

    :return:
    """

    condition = dict()
    if id:
        condition['id'] = id
    if host:
        condition['host'] = host
    evaluations = await Evaluation.query_page(page_num=page_num, page_size=page_size, condition=condition, desc=True)
    return rsp(data=evaluations)


async def query_evaluation_by_id(id):
    """

    :return:
    """

    evaluations = await Evaluation.query(Evaluation.id == id)
    if not evaluations:
        return rsp(code=401, message=f'Evaluation {id} not exist')
    evaluation_columns = [
        'name', 'host', 'arch', 'target_arch', 'os_release', 'target_os_release', 'status', 'detail', 'sys_config'
    ]
    evaluation = evaluations[0].serialize(columns=evaluation_columns)
    return rsp(data=evaluation)


async def create_evaluation_task(machine_id, target_os_release=None, target_arch=None):
    machine = await Machine.query(Machine.id == machine_id)
    if not machine:
        return rsp(code=400, message=f'Machine {id} doesn\'t exit')
    machine = machine[0]

    host = machine.host
    evaluations = await Evaluation.query(Evaluation.host == host, Evaluation.status == 'running')
    if evaluations:
        return rsp(code=400, message=f'Evaluation task is running on {host}')
    evaluation_data = {
        'name': machine.name,
        'host': machine.host,
        'arch': machine.arch,
        'os_release': machine.os_release,
        'target_os_release': target_os_release or 'Alibaba Cloud Linux 3 (Soaring Falcon)',
        'target_arch': target_arch or 'arm64'
    }
    evaluation, message, http_code = await Evaluation().save(evaluation_data)
    if not evaluation:
        return rsp(code=http_code, message=message)
    evaluation_task = asyncio.create_task(
        execute_evaluation_task(machine=machine, evaluation=evaluation),
        name=f'evaluation_task_{evaluation.id}'
    )
    log.logger.info(f'{evaluation_task.get_name()} create success')
    return rsp(message=f'{evaluation_task.get_name()} create success')


async def execute_evaluation_task(machine: Machine, evaluation: Evaluation):
    evaluation_result_local_path = os.path.join(WORKSPACE_PATH, 'evaluation', f'{evaluation.id}')
    await execute_linux_command(f'mkdir -p {evaluation_result_local_path}')
    try:
        evaluation_result = await run_client(
            machine=machine, evaluation=evaluation, evaluation_result_local_path=evaluation_result_local_path
        )
        sys_result = {}
        if evaluation_result:
            for i in os.listdir(evaluation_result_local_path):
                if 'detail.csv' in i:
                    key = i.split('()')[0]
                    value = os.path.join(evaluation_result_local_path, i)
                    sys_result[key] = value
            for i in os.listdir(os.path.join(evaluation_result_local_path, 'kernel')):
                if 'detail.csv' in i:
                    key = i.split('()')[0]
                    value = os.path.join(evaluation_result_local_path, 'kernel', i)
                    sys_result[key] = value
            evaluation.sys_config = json.dumps(sys_result)
            evaluation.status = 'success'
            await evaluation.save()
        else:
            evaluation.status = 'fail'
            await evaluation.save()
    except (OSError, asyncssh.Error) as exc:
        evaluation.status = 'fail'
        await evaluation.save()
        log.logger.error(f'Evaluation task {evaluation.id} failed: ' + str(exc))


async def run_client(machine: Machine, evaluation: Evaluation, evaluation_result_local_path: str):
    host = machine.host
    username = machine.username
    password = machine.password
    port = machine.port
    async with asyncssh.connect(host=host, username=username, password=password, port=port, known_hosts=None) as conn:
        evaluation_tool_version_result = await conn.run('/usr/local/bin/ance version')
        # ance_version_result = await run_command(conn=conn, command='/usr/local/bin/ance version')
        if evaluation_tool_version_result.exit_status != 0:
            log.logger.info('Not found evaluation tool %s:' % (evaluation_tool_version_result.exit_status))

            log.logger.info(f'install evaluation tool on {host}')
            log.logger.info(f'send evaluation tool to {host}')
            ance_file_name = 'ance-0.4.0-20230906154833.dev.x86_64.rpm'
            await asyncssh.scp(f'./resource/{ance_file_name}', (conn, '/tmp'))

            init_ance_script = f'''
                yum install -y epel-release
                yum install -y /tmp/{ance_file_name} --enablerepo=epel
                /usr/local/bin/ance version
            '''
            init_ance_script_result = await conn.run(init_ance_script)
            log.logger.info(init_ance_script_result.exit_status)
            if init_ance_script_result.exit_status != 0:
                return False
        else:
            log.logger.info(evaluation_tool_version_result.stdout)
        log.logger.info(f'Evaluation tools init success on {host}')

        ANCE_SQL_PATH = '/tmp/ance/database'
        log.logger.info(f'send alinux3 data to {host}')
        ance_file_name = 'Alibaba_Cloud_Linux-3_Soaring_Falcon.aarch64.sqlite'
        await asyncssh.scp(f'./resource/{ance_file_name}', (conn, ANCE_SQL_PATH))
        log.logger.info(f'send alinux3 data to {host} success')

        await conn.run('rm -rf /tmp/ance/results/*')
        # run ance
        evaluation_sys_script = f'''
            ance evaluate --subtypes=os_rpmlist,kconfig,os_metadata --etype=os --os1=/ \
            --os2={ANCE_SQL_PATH}/{ance_file_name}
        '''
        log.logger.info(evaluation_sys_script)
        evaluation_sys_script_result = await conn.run(evaluation_sys_script)
        if evaluation_sys_script_result.exit_status != 0:
            evaluation.status = 'fail'
            evaluation.save()
            log.logger.info(evaluation_sys_script_result.stdout)
            return False
        log.logger.info(f'Evaluate success on {host}')
        evaluation_results_exist = await conn.run('ls -d /tmp/ance/results/os-report-*[!tar.gz]')
        log.logger.info(f'evaluation_results: {evaluation_results_exist.stdout}')
        if not evaluation_results_exist.stdout:
            log.logger.info(f'Not found evaluation results on {host}')
            evaluation.status = 'fail'
            evaluation.save()
            return False
        await asyncssh.scp(
            (conn, '/tmp/ance/results/os-report-*[!tar.gz]/*'),
            evaluation_result_local_path,
            preserve=True, recurse=True
        )
        log.logger.info(f'Get evaluate result success on {host}')
        return True


async def delete_evaluation_task(id) -> rsp:
    evaluations = await Evaluation.query(Evaluation.id == id)
    if not evaluations:
        return rsp(code=401, message=f'Evaluation task {id} not exist')
    await Evaluation.delete(Evaluation.id == id)
    return rsp(message=f'Delete evaluation task {id} success')


async def get_evaluation_task_result(id, type) -> rsp:
    evaluations = await Evaluation.query(Evaluation.id == id)
    if not evaluations:
        return rsp(code=401, message=f'Evaluation task {id} not exist')
    evaluation = evaluations[0]
    if not evaluation.sys_config:
        return rsp(code=401, message=f'Evaluation task {id} result not exist')
    evaluation_result_path = json.loads(evaluation.sys_config).get(type)
    if not evaluation_result_path:
        return rsp(code=401, message=f'Evaluation task {id} {type} result not exist')
    if type == 'kconfig':
        return rsp(data=read_csv_with_field(evaluation_result_path, 'descriptions'))
    if type == 'os_rpmlist':
        return rsp(data=read_csv_with_field(evaluation_result_path, 'detail'))
    return rsp(data=read_csv(evaluation_result_path))


def read_csv(csv_path):
    result = None
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            csv_reader = csv.DictReader(f)
            result = [i for i in csv_reader]
    return result


def read_csv_with_field(csv_path: str, field: str):
    result = None
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            csv_reader = csv.DictReader(f)
            row_with_value_in_specified_field = []
            row_without_value_in_specified_field = []
            for row in csv_reader:
                if row.get(field):
                    row_with_value_in_specified_field.append(row)
                else:
                    row_without_value_in_specified_field.append(row)
            result = row_with_value_in_specified_field + row_without_value_in_specified_field
    return result
