from app.log import log

def generate_scan_command(
        language_list: list(),
        result_path: str,
        arch: str,
        scan_path: str,
        file_path: str,
        log_name: str,
        locale: str,
        build_tool: str = None
):
    log.logger.debug(f'generate_scan_command language_list: {language_list}, arch: {arch}, build_tool: {build_tool}')
    command = dict()
    for language in language_list:
        if language == 'cpp':
            result_file_path = f'{result_path}_{language}_result.json'
            if arch == 'x86_64':
                cmd = f'python3 scanner/cpp/cpp_scanner.py --output {result_file_path} \
                    --arch {arch} --march dhyana {scan_path}'
            else:
                cmd = f'python3 scanner/cpp/cpp_scanner.py --output {result_file_path} --arch {arch} --locale {locale} --build-tool {build_tool} {scan_path}'
            command[language] = dict(
                result_file_path=result_file_path,
                cmd=cmd
            )
    log.logger.info(f'command: {command}')
    return command
