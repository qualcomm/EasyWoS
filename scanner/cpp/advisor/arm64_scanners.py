from .arm64_asm_source_scanner import Arm64AsmSourceScanner
from .arm64_config_guess_scanner import Arm64ConfigGuessScanner
from .arm64_makefile_scanner import Arm64MakefileScanner
from .arm64_source_scanner import Arm64SourceScanner
from .arm64_vcxproj_scanner import Arm64VcxprojScanner
from .issue_type_filter import IssueTypeFilter
from .target_os_filter import TargetOsFilter

class Arm64Scanners:

    """
    Set of scanners that may be used to scan for potential porting issues in
    files from x86 Intel processors to aarch64 processors.
    """

    def __init__(self, issue_type_config, output_format, arch, march, compiler, warning_level, locale, build_tool, external_targets=None):
        """
        Args:
            issue_type_config (IssueTypeConfig): issue type filter
            configuration.
        """
        self.scanners = [Arm64SourceScanner(output_format=output_format, arch=arch, march=march,
                                            compiler=compiler, warning_level=warning_level, locale=locale),
                         Arm64AsmSourceScanner(output_format=output_format, arch=arch, march=march, locale=locale)]
        self.filters = []
        self.filters += [IssueTypeFilter(issue_type_config), TargetOsFilter()]
        if build_tool and build_tool.lower() == 'make':
            self.scanners.append(Arm64MakefileScanner(output_format=output_format, arch=arch, march=march, locale=locale, external_targets=external_targets))
            self.scanners.append(Arm64ConfigGuessScanner(output_format=output_format, arch=arch, march=march))
        if build_tool and build_tool.lower() == 'msbuild':
            self.scanners.append(Arm64VcxprojScanner(output_format=output_format, arch=arch, march=march, locale=locale))


    def __iter__(self):
        return self.scanners.__iter__()

    def initialize_report(self, report):
        """
        Initializes the given report for scanning.

        Args:
            report (Report): Report to initialize_report.
        """
        for a_filter in self.filters:
            a_filter.initialize_report(report)

        for scanner in self.scanners:
            scanner.initialize_report(report)

    def finalize_report(self, report):
        """
        Finalizes the given report.

        Args:
            report (Report): Report to finalize_report.
        """
        for scanner in self.scanners:
            scanner.finalize_report(report)

        for a_filter in self.filters:
            a_filter.finalize_report(report)
