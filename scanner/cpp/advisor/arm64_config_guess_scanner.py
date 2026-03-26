import re
from .config_guess_issue import ConfigGuessIssue
from .config_guess_scanner import ConfigGuessScanner


class Arm64ConfigGuessScanner(ConfigGuessScanner):

    """
    Scanner that scans config.guess files for aarch64 support.
    """

    TARGET_ARCH_RE = re.compile(r'(aarch64|arm64).*:Linux')

    def __init__(self, output_format, arch, march):
        self.output_format = output_format
        self.arch = arch
        self.march = march

    def scan_file_object(self, filename, file_obj, report):

        _lines = file_obj.readlines()
        self.FILE_SUMMARY[self.AUTOCONF]['count'] += 1
        self.FILE_SUMMARY[self.AUTOCONF]['loc'] += len(_lines)

        for line in _lines:
            match = Arm64ConfigGuessScanner.TARGET_ARCH_RE.search(line)

            if match:
                break

        # no match found.
        else:
            report.add_issue(ConfigGuessIssue(filename=filename,
                                              remark="autoconf config.guess needs updating to recognize aarch64 architecture"))
