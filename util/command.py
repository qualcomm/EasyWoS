import os
import signal
import psutil
import asyncio
import asyncssh
from fabric import Connection
from paramiko import SSHException, AuthenticationException
from app.log import log


async def execute_linux_command(cmd: str):
    log.logger.info(f'cmd: {cmd}')
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stderr=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    log.logger.info(f'{cmd!r} exited with {proc.returncode}')
    return stdout.decode().strip(), stderr.decode().strip(), proc.returncode


async def execute_linux_command_without_log_redirect(cmd: str):
    log.logger.info(f'cmd: {cmd}')
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid
        )
        await process.communicate()
        log.logger.info(f'{cmd!r} exited with {process.returncode}')
    except asyncio.CancelledError:
        if not cmd.startswith('/yoda'):
            process.terminate()
        else:
            children = psutil.Process(process.pid).children(recursive=True)
            log.logger.debug(children)
            if children:
                child = children[0]
                log.logger.debug(child)
                os.kill(child.pid, signal.SIGINT)
                os.kill(child.pid, signal.SIGINT)
    return process.returncode


async def execute_linux_command_with_log_redirect(cmd: str, log_path: str):
    log.logger.info(f'cmd: {cmd}')
    try:
        process = await asyncio.create_subprocess_shell(
            f'exec {cmd} >> {log_path} 2>&1',
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid
        )
        await process.communicate()
        log.logger.info(f'{cmd!r} exited with {process.returncode}')
    except asyncio.CancelledError:
        if not cmd.startswith('/yoda'):
            process.terminate()
        # pgid = os.getpgid(process.pid)
        # print(pgid)

        else:
            children = psutil.Process(process.pid).children(recursive=True)
            log.logger.debug(children)
            if children:
                child = children[0]
                log.logger.debug(child)
                os.kill(child.pid, signal.SIGINT)
                os.kill(child.pid, signal.SIGINT)
                # child.terminate()
    return process.returncode


# run remote command
# hide 表示隐藏远程机器在控制台的输出, 达到静默的效果
# 默认 warn是False, 如果远程机器运行命令出错, 那么本地会抛出异常堆栈. 设为True 则不显示这堆栈.
def run(conn, cmd, hide=True, warn=True):
    r = conn.run(cmd, encoding='utf8', hide=hide, warn=warn)
    result, err = r.stdout.strip(), r.stderr.strip()
    return result, err


async def execute_cmd(host, user, password, port, cmd) -> tuple[None, None]:

    log.logger.info(f'host: {host}, cmd: {cmd}')
    conn = Connection(host=host, user=user, port=port, connect_kwargs={'password': password})
    with conn:
        try:
            result, err = run(conn, cmd)
            log.logger.error(err)
            return result, err
        except AuthenticationException as e:
            log.logger.error(f'Authentication failed. Please verify your credentials: {e}')
            return None, str(e)
        except SSHException as e:
            log.logger.error(f'Unable to establish an SSH connection: {e}')
            return None, str(e)
        except Exception as e:
            log.logger.error(e)
            return None, str(e)


async def run_scp_client(machine, file, remote_path) -> None:
    host = machine.host
    username = machine.username
    password = machine.password
    port = machine.port

    async with asyncssh.connect(host=host, username=username, password=password, port=port, known_hosts=None) as conn:
        await asyncssh.scp(file, (conn, remote_path))


async def run_multiple_scp_clients(machines, file, remote_path) -> None:
    tasks = (run_scp_client(machine, file, remote_path) for machine in machines)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results, 1):
        if isinstance(result, Exception):
            print('Task %d failed: %s' % (i, str(result)))
        else:
            print('Task %d succeeded:' % i)

        print(75 * '-')


async def execute_remote_command(machine, command) -> None:
    host = machine.host
    username = machine.username
    password = machine.password
    port = machine.port
    async with asyncssh.connect(host=host, username=username, password=password, port=port, known_hosts=None) as conn:
        result = await conn.run(command, check=True)
        print(result.stdout, end='')
    return


async def run_client(machine, command: str) -> asyncssh.SSHCompletedProcess:
    host = machine.host
    username = machine.username
    password = machine.password
    port = machine.port
    async with asyncssh.connect(host=host, username=username, password=password, port=port, known_hosts=None) as conn:
        return await conn.run(command)