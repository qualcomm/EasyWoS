"""
Copyright 2017-2018 Arm Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

SPDX-License-Identifier: Apache-2.0
"""

import re
import textwrap
import os
from .localization import _


class ReportItem(object):

    NON_EMPTY_LINE_RE = re.compile(r'\S')

    SUMMARY = {'type': 'summary', 'des': 'SUMMARY', 'des-zh': '总结'}
    PREPROCESSOR_ERROR = {'type': 'PreprocessorErrorIssue', 'des': 'Target platform detected, this file may enter the #Error preprocessor logic.', 'des-zh': '检测到目标平台，该文件可能会进入 #Error 预处理器逻辑。'}
    PRAGMA = {'type': 'PragmaIssue', 'des': 'Detected that this #Pragma may be incompatible with the target platform compiler.', 'des-zh': '检测到此 #Pragma 可能与目标平台编译器不兼容。'}
    CPP_LIB_VERSION = {'type': 'CppLibVersionIssue', 'des': 'Detected that this library version may be incompatible with the target platform compiler.', 'des-zh': '检测到此库版本可能与目标平台编译器不兼容。'}
    CPP_LIB_RECOMMEND = {'type': 'CppLibRecommendIssue', 'des': 'Detected that a better optimized version of this library may exist.', 'des-zh': '检测到可能存在此库的更好优化版本。'}
    COMPILER_SPECIFIC = {'type': 'CompilerSpecificIssue', 'des': 'Detected code strongly related to compiler version or type, potential compatibility issues.', 'des-zh': '检测到与编译器版本或类型密切相关的代码，可能存在兼容性问题。'}
    CPP_STD_CODES = {'type': 'CPPStdCodes', 'des': 'Detected C++ code compatibility issues or optimization logic related to processor platform memory ordering.', 'des-zh': '检测到 C++ 代码兼容性问题或与处理器平台内存排序相关的优化逻辑。'}
    INCOMPATIBLE_HEADER_FILE = {'type': 'IncompatibleHeaderFileIssue', 'des': 'Detected incompatible header file.', 'des-zh': '检测到不兼容的头文件。'}
    INLINE_ASM = {'type': 'InlineAsmIssue', 'des': 'Detected inline assembly usage on target platform, potential platform compatibility issues.', 'des-zh': '检测到目标平台上的内联汇编使用，可能存在平台兼容性问题。'}
    INTRINSIC = {'type': 'IntrinsicIssue', 'des': 'Detected usage of Intrinsic functions with compatibility issues on the target platform.', 'des-zh': '检测到在目标平台上存在兼容性问题的 Intrinsic 函数使用。'}
    ARCH_SPECIFIC_LIBRARY = {'type': 'ArchSpecificLibraryIssue', 'des': 'Detected usage of libraries strongly related to processor architecture, potential compatibility issues.', 'des-zh': '检测到与处理器架构密切相关的库的使用，可能存在兼容性问题。'}
    OLD_CRT = {'type': 'OldCrtIssue', 'des': 'Detected usage of older C runtime library versions, compatibility issues or optimization space may exist.', 'des-zh': '检测到旧版 C 运行时库版本的使用，可能存在兼容性问题或优化空间。'}
    DEFINE_OTHER_ARCH = {'type': 'DefineOtherArchIssue', 'des': 'Code contains detection logic for other processor platform types, potential platform compatibility issues.', 'des-zh': '代码包含针对其他处理器平台类型的检测逻辑，可能存在平台兼容性问题。'}
    CROSS_COMPILE = {'type': 'CrossCompileIssue', 'des': 'Detected cross-compilation compatibility issues.', 'des-zh': '检测到交叉编译兼容性问题。'}
    ASM_SOURCE = {'type': 'AsmSourceIssue', 'des': 'Detected processor architecture-related assembly code in assembly source files, manual check required.', 'des-zh': '在汇编源文件中检测到处理器架构相关的汇编代码，需要手动检查。'}
    CONFIG_GUESS = {'type': 'ConfigGuessIssue', 'des': 'Detected missing target platform architecture configuration in config.guess file, adaptation may be needed.', 'des-zh': '在 config.guess 文件中检测到缺少目标平台架构配置，可能需要适配。'}
    NO_EQUIVALENT_INTRINSIC = {'type': 'NoEquivalentIntrinsicIssue', 'des': 'Detected usage of Intrinsic functions that do not exist on the target platform.', 'des-zh': '检测到目标平台上不存在的 Intrinsic 函数使用。'}
    NO_EQUIVALENT_INLINE_ASM = {'type': 'NoEquivalentInlineAsmIssue', 'des': 'Detected usage of inline assembly code that does not exist on the target platform.', 'des-zh': '检测到目标平台上不存在的内联汇编代码使用。'}
    NO_EQUIVALENT = {'type': 'NoEquivalentIssue', 'des': 'NO_EQUIVALENT', 'des-zh': '无等价物'}
    HOST_CPU_DETECTION = {'type': 'HostCpuDetectionIssue', 'des': 'Makefile contains detection logic for processor platform types, potential platform compatibility issues.', 'des-zh': 'Makefile 包含针对处理器平台类型的检测逻辑，可能存在平台兼容性问题。'}
    BUILD_COMMAND = {'type': 'BuildCommandIssue', 'des': 'Detected potential compatibility issues related to build commands.', 'des-zh': '检测到与构建命令相关的潜在兼容性问题。'}
    AVX256_INTRINSIC = {'type': 'Avx256IntrinsicIssue', 'des': 'Detected usage of AVX256 instruction set on target platform, potential compatibility issues.', 'des-zh': '检测到目标平台上 AVX256 指令集的使用，可能存在兼容性问题。'}
    AVX512_INTRINSIC = {'type': 'Avx512IntrinsicIssue', 'des': 'Detected usage of AVX512 instruction set on target platform, potential compatibility issues.', 'des-zh': '检测到目标平台上 AVX512 指令集的使用，可能存在兼容性问题。'}
    ARM64EC_INCOMPATIBLE_GRAMMAR = {'type': 'ARM64ECIncompatibleGrammarIssue', 'des': 'Detected incompatible syntax on the ARM64EC platform.', 'des-zh': '检测到 ARM64EC 平台上的不兼容语法。'}
    NO_ISSUES_FOUND_REMARK = {'type': 'NoIssuesFoundRemark', 'des': 'NO_ISSUES_FOUND_REMARK', 'des-zh': '未发现问题备注'}
    PORTED_SOURCE_FILES_REMARK = {'type': 'PortedSourceFilesRemark', 'des': 'Detected that this source file already has a ported version on the target platform, recommending the target platform specific version.', 'des-zh': '检测到此源文件在目标平台上已有移植版本，建议使用目标平台特定版本。'}
    PORTED_INLINE_ASM_REMARK = {'type': 'PortedInlineAsmRemark', 'des': 'Detected that the used intrinsics already have a ported version on the target platform, recommending the target platform specific version.', 'des-zh': '检测到所使用的 intrinsics 在目标平台上已有移植版本，建议使用目标平台特定版本。'}
    SIGNED_CHAR = {'type': 'SignedCharIssue', 'des': 'Detected signed Char type data compatibility issues.', 'des-zh': '检测到有符号 Char 类型数据兼容性问题。'}
    ARCH_CONFIG_MISS = {'type': 'ArchConfigMissIssue', 'des': 'Misssing configuration of target arch.', 'des-zh': '缺乏目标架构的配置。'}
    OTHER = {'type': 'OtherIssue', 'des': 'When the code scanning tool uses the scan issue limit option, issues exceeding the limit will be classified as OtherIssue.', 'des-zh': '当代码扫描工具使用扫描问题限制选项时，超过限制的问题将被归类为 OtherIssue。'}
    ERROR = {'type': 'Error', 'des': 'Indicates an exception encountered by the code scanning program during the scan, not a code logic issue itself, user can ignore.', 'des-zh': '表示代码扫描程序在扫描过程中遇到的异常，并非代码逻辑问题本身，用户可以忽略。'}

    TYPES = [SUMMARY,
             PREPROCESSOR_ERROR,
             PRAGMA,
             COMPILER_SPECIFIC,
             CPP_STD_CODES,
             CPP_LIB_VERSION,
             CPP_LIB_RECOMMEND,
             INCOMPATIBLE_HEADER_FILE,
             INLINE_ASM,
             INTRINSIC,
             ARCH_SPECIFIC_LIBRARY,
             OLD_CRT,
             DEFINE_OTHER_ARCH,
             CROSS_COMPILE,
             ASM_SOURCE,
             CONFIG_GUESS,
             NO_EQUIVALENT_INTRINSIC,
             NO_EQUIVALENT_INLINE_ASM,
             NO_EQUIVALENT,
             HOST_CPU_DETECTION,
             BUILD_COMMAND,
             AVX256_INTRINSIC,
             AVX512_INTRINSIC,
             ARM64EC_INCOMPATIBLE_GRAMMAR,
             NO_ISSUES_FOUND_REMARK,
             PORTED_SOURCE_FILES_REMARK,
             PORTED_INLINE_ASM_REMARK,
             SIGNED_CHAR,
             ARCH_CONFIG_MISS,
             ARCH_SPECIFIC_LIBRARY,
             OTHER,
             ERROR]

    def __init__(self, description, filename=None, lineno=None, issue_type=OTHER, checkpoint=None):

        self.filename = filename
        self.lineno = lineno         # start from 1!!
        self.filename = filename
        self.description = description
        self.issue_type = issue_type
        self.checkpoint = checkpoint
        self.snippet = None

    def set_code_snippet(self, snippet):
        self.snippet = snippet

    def get_code_snippets(self, lines=None, with_highlights=True):
        snippets_size_in_line = 8           # number of non-empty lines above or below the issue line
        snippets = ""

        if not lines:
            with open(self.filename, 'r') as fp:
                lines = fp.readlines()

        lineno_offset = 1
        nonempty_snippet_line_count = 0
        while (nonempty_snippet_line_count < snippets_size_in_line):

            if (self.lineno - lineno_offset) > 0:

                current_line = lines[self.lineno - lineno_offset]

                if with_highlights:
                    snippets = current_line.replace('<', '&lt;') + snippets
                else:
                    snippets = current_line + snippets

                if bool(self.NON_EMPTY_LINE_RE.search(current_line)):
                    nonempty_snippet_line_count += 1

                lineno_offset += 1
            else:   # no more lines
                break

        if with_highlights:
            dedented_line = textwrap.dedent(lines[self.lineno]).replace('\n', '')

            highlighted_line = lines[self.lineno].replace(dedented_line,
                                                          "<font style='color:red;'>" + dedented_line.replace('<', '&lt;') + "</font>")
            snippets += highlighted_line
        else:
            snippets += lines[self.lineno]

        lineno_offset = 1
        nonempty_snippet_line_count = 0
        while (nonempty_snippet_line_count < snippets_size_in_line):

            if (self.lineno + lineno_offset) < len(lines):

                current_line = lines[self.lineno + lineno_offset]

                if with_highlights:
                    snippets += current_line.replace('<', '&lt;')
                else:
                    snippets += current_line

                if bool(self.NON_EMPTY_LINE_RE.search(current_line)):
                    nonempty_snippet_line_count += 1

                lineno_offset += 1
            else:
                break

        return textwrap.dedent(snippets)

    def __str__(self):

        #  TODO: for the moment only sw64 support the presentation of codes
        if self.snippet:

            if self.description:
                return _('%(file)s:%(lineno)s (%(checkpoint)s): \ncode snippet: \n%(snippet)s\ndescription:\n%(description)s') % {
                    'file': self.filename,
                    'lineno': self.lineno,
                    'checkpoint': self.checkpoint,
                    'snippet': self.snippet,
                    'description': self.description
                }
            else:
                return _('%(file)s:%(lineno)s (%(checkpoint)s): \ncode snippet: \n%(snippet)s') % {
                    'file': self.filename,
                    'lineno': self.lineno,
                    'checkpoint': self.checkpoint,
                    'snippet': self.snippet
                }

        elif self.lineno:

            if self.checkpoint:
                return _('%(file)s:%(lineno)s (%(checkpoint)s): %(description)s') % {
                    'file': self.filename,
                    'lineno': self.lineno,
                    'checkpoint': self.checkpoint,
                    'description': self.description
                }
            else:
                return _('%(file)s:%(lineno)s: %(description)s') % {
                    'file': self.filename,
                    'lineno': self.lineno,
                    'description': self.description
                }

        elif self.filename:

            if self.checkpoint:
                return _('%(file)s (%(checkpoint)s): %(description)s') % {
                    'file': self.filename,
                    'checkpoint': self.checkpoint,
                    'description': self.description
                }
            else:
                return _('%(file)s: %(description)s') % {
                    'file': self.filename,
                    'description': self.description
                }

        else:

            if self.checkpoint:
                return _('%(checkpoint)s: %(description)s') % {
                    'checkpoint': self.checkpoint,
                    'description': self.description
                }
            else:
                return _('%(description)s') % {
                    'description': self.description
                }
