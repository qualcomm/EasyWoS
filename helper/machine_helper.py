# import logging
from app.log import log
from sqlalchemy import select, delete
from app.database import db
from models.machine import Machine
from util.command import execute_cmd
from util.http import rsp


async def list_machine(page_num, page_size, id, name):
    """

    :return:
    """

    condition = dict()
    if id:
        condition['id'] = id
    if name:
        condition['username'] = name
    columns = ['name', 'host', 'username', 'port', 'status', 'arch', 'os_release', 'kernel_version', 'description']
    machines = await Machine.query_page(
        page_num=page_num,
        page_size=page_size,
        condition=condition,
        columns=columns
    )
    return rsp(data=machines)


async def get_machine(id=None, name=None):
    """

    :return:
    """
    if id:
        log.logger.info(f'machine id: {id}')
        machines = await Machine.query(Machine.id == id)
    if name:
        log.logger.info(f'machine name: {name}')
        machines = await Machine.query(Machine.name == name)
    columns = [
        'name', 'host', 'username', 'port', 'status', 'arch',
        'os_release', 'kernel_version'
    ]
    machineList = []
    for machine in machines:
        machineList.append(machine.serialize(columns=columns))
    return machineList


async def add_machine(name, host, username, password, port, description) -> rsp:
    machine = dict(
        name=name,
        host=host,
        username=username,
        password=password,
        port=port,
        description=description
    )
    machine, message, http_code = await Machine().save(machine)
    if not machine:
        return rsp(code=http_code, message=message)
    columns = [
        'name', 'host', 'username', 'password', 'port', 'description'
    ]
    response_data = {
        'machine': machine.serialize(columns=columns)
    }
    return rsp(code=http_code, message=message, data=response_data or None)


async def update_machine(
    id, status=False, username=None, password=None, port=None, os_release=None,
    kernel_version=None,
    description=None
) -> rsp:
    machine = await Machine.query(Machine.id == id)
    if not machine:
        return rsp(code=400, message=f'Machine {id} doesn\'t exit')
    machine = machine[0]
    if username:
        machine.username = username
    if password:
        machine.password = password
    if port:
        machine.port = port
    if status:
        machine.status = status
    if os_release:
        machine.os_release = os_release
    if kernel_version:
        machine.kernel_version = kernel_version
    if description:
        machine.description = description
    await machine.update()
    # await session.update(machine)
    # await session.commit()
    return rsp(code=200, message=f'Update machine {id} success')


async def verify_machine(id) -> rsp:
    machine = await Machine.query(Machine.id == id)
    if not machine:
        return rsp(code=400, message=f'Machine {id} doesn\'t exit')
    machine = machine[0]
    host = machine.host
    username = machine.username
    password = machine.password
    port = machine.port

    cmd = 'cat /etc/os-release | grep PRETTY_NAME | awk -F\'"\' \'{print $2, $4}\' && uname -r && uname -m'
    response = {
        'status': False,
        'os_release': None,
        'kernel_version': None,
        'arch': None
    }

    result, err = await execute_cmd(host, username, password, port, cmd=cmd)
    if err:
        return rsp(code=503, message=err, data=response)
    os_release, kernel_version, arch = result.split('\n')
    machine.status = True
    machine.os_release = os_release
    machine.kernel_version = kernel_version
    machine.arch = arch
    await machine.update()
    response = {
        'status': True,
        'os_release': os_release,
        'kernel_version': kernel_version,
        'arch': arch
    }
    return rsp(code=200, message='Success', data=response)


async def delete_machine(id) -> rsp:
    async with db.conn() as session:
        machine = (await session.execute(select(Machine).filter(Machine.id == id))).first()
        if not machine:
            return rsp(code=400, message=f'Machine {id} doesn\'t exit')
        await session.execute(delete(Machine).where(Machine.id == id))
        await session.commit()
    return rsp(code=200, message=f'Delete machine {id} success')
