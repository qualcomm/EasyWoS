"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from typing import List

from .find_port import find_matching_line_num
from .incompatible_header_file_issue import IncompatibleHeaderFileIssue
from .inline_asm_issue import InlineAsmIssue
from .intrinsic_issue import IntrinsicIssue
from .cpp_std_issue import CPPStdCodesIssue
from .arm64ec_issue import ARM64ECIncompatibleGrammarIssue
from .issue import Issue
from .naive_comment_parser import NaiveCommentParser
from .naive_cpp import NaiveCpp, PreprocessorDirective
from .naive_function_parser import NaiveFunctionParser
from .pragma_issue import PragmaIssue
from .preprocessor_error_issue import PreprocessorErrorIssue
from .localization import _
from .scanner import Scanner
from .report_factory import ReportOutputFormat
from .continuation_parser import ContinuationParser
from .checkpoint import Checkpoint
from .arch_strings import AARCH64_ARCHS
from .checkpoints import AARCH64_INCOMPATIBLE_INTRINSICS
from .checkpoints import AARCH64_INLINE_ASSEMBLY_CHECKPOINTS
from .checkpoints import X86_PRAGMA
from .checkpoints import CPP_STD_CODES
from .checkpoints import INCOMPATIBLE_HEADER_FILE
from .checkpoints import ARM64EC_INCOMPATIBLE_GRAMMAR

import os
import re
import logging

logger = logging.getLogger(__name__)

# Matches '#define MACRO_NAME' or '#  define MACRO_NAME'
_DEFINE_RE = re.compile(r'#\s*define\s+(\w+)')


class ClangSourceScanner(Scanner):
    """
    Scanner that scans C, C++ and Fortran source files for potential porting
    issues.
    """

    C_SOURCE_EXTENSIONS = ['.c', '.h', '.i']
    CPP_SOURCE_EXTENSIONS = ['.cc', '.cpp', '.cxx', '.h', '.hxx', '.hpp', '.ii']

    def __init__(self, output_format, arch, march, compiler='gcc', warning_level='L1', locale='en_US'):
        self.output_format = output_format
        self.arch = arch
        self.march = march
        self.compiler = compiler
        self.warning_level = warning_level
        self.check_state = True
        self.locale = locale

        self.with_highlights = bool(
            output_format == ReportOutputFormat.HTML or self.output_format == ReportOutputFormat.JSON)

        # Maps user-defined macro names (that wrap x64-incompatible intrinsics) to
        # (compiled_word_pattern, original_checkpoint_pattern).  Shared across all
        # files in a single scan so that macros defined in headers are detected in
        # the source files that use them.
        self._user_incompatible_macros: dict = {}

    def accepts_file(self, filename):

        _, ext = os.path.splitext(filename)
        return ext.lower() in self.__class__.C_SOURCE_EXTENSIONS or ext.lower() in self.__class__.CPP_SOURCE_EXTENSIONS

    def scan_file_object(self, filename, file_obj, report):
        logger.info(f'Scanning file: {filename}')
        _lines = file_obj.readlines()
        _, ext = os.path.splitext(filename)

        if ext.lower() in self.__class__.C_SOURCE_EXTENSIONS:

            self.FILE_SUMMARY[self.C]['count'] += 1
            self.FILE_SUMMARY[self.C]['loc'] += len(_lines)

        elif ext.lower() in self.__class__.CPP_SOURCE_EXTENSIONS:

            self.FILE_SUMMARY[self.CPP]['count'] += 1
            self.FILE_SUMMARY[self.CPP]['loc'] += len(_lines)

        continuation_parser = ContinuationParser()
        comment_parser = NaiveCommentParser()
        function_parser = NaiveFunctionParser()

        naive_cpp = NaiveCpp(arch=self.arch, march=self.march)

        PRAGMA_CHECKPOINTS: List[Checkpoint]

        if self.arch in AARCH64_ARCHS:
            ARCH_INCOMPATIBLE_INTRINSICS = AARCH64_INCOMPATIBLE_INTRINSICS
            ASSEMBLY_CHECKPOINTS = AARCH64_INLINE_ASSEMBLY_CHECKPOINTS
            PRAGMA_CHECKPOINTS = X86_PRAGMA
        else:
            ARCH_INCOMPATIBLE_INTRINSICS = None
            ASSEMBLY_CHECKPOINTS = None
            PRAGMA_CHECKPOINTS = None

        issues: List[Issue] = []
        lines = {lineno: line for lineno, line in enumerate(_lines, 1)}

        self.check_state = True

        func_start_lineno: int | None = None
        intrinsic_func_seen: set = set()
        inline_asm_func_seen: set = set()

        # directive_stack: List[List[Issue]] = []
        # type of lines.keys() : <int, str>
        for lineno in lines.keys():

            line = lines[lineno]

            line = continuation_parser.parse_line(line)
            if not line or line.strip() == '' or line.strip() == '#':
                continue

            is_comment = comment_parser.parse_line(line)
            if is_comment:
                continue

            #  header file check
            if self.check_state:
                for c in INCOMPATIBLE_HEADER_FILE:
                    match = c.pattern_compiled.search(line)
                    if match:
                        if self.locale.startswith('zh'):
                            issues.append(IncompatibleHeaderFileIssue(filename,
                                                                    lineno=find_matching_line_num(lines, lineno, c.pattern),
                                                                    checkpoint=c.pattern,
                                                                    description='' if not c.help_zh else '\n' + c.help_zh))
                            break
                        if self.locale.startswith('en'):
                            issues.append(IncompatibleHeaderFileIssue(filename,
                                                                    lineno=find_matching_line_num(lines, lineno, c.pattern),
                                                                    checkpoint=c.pattern,
                                                                    description='' if not c.help else '\n' + c.help))
                            break

            # if the line is a PreprocessorDirective, process the possible '\' in the end
            # and combine to a complete macro for latter parsing.
            if line.lstrip().startswith('#'):
                result = naive_cpp.parse_line(line.strip())
                if result.directive_type == PreprocessorDirective.TYPE_DEFINE \
                        and result.body is not None and self.check_state:
                    # Only register macros for later tracking; do NOT report the #define
                    # itself as an issue — only functions that USE the macro are reported.
                    self._register_incompatible_macro(
                        line, ARCH_INCOMPATIBLE_INTRINSICS, ASSEMBLY_CHECKPOINTS, naive_cpp)
                self._check_directive(result, filename,
                                      lineno, line,
                                      function_parser, PRAGMA_CHECKPOINTS, issues)
            else:
                # Always update function tracking regardless of check_state so that
                # func_start_lineno is correct even inside #ifdef blocks that are
                # conditionally disabled (e.g. #ifdef X86_AVX2).
                new_func = function_parser.parse_line(line)
                if new_func is not None:
                    func_start_lineno = lineno
                elif function_parser.current_function is None:
                    func_start_lineno = None

                if self.check_state:
                    self._check_clang(lines, lineno, line, naive_cpp, filename,
                                      ASSEMBLY_CHECKPOINTS, ARCH_INCOMPATIBLE_INTRINSICS, issues,
                                      func_start_lineno, intrinsic_func_seen, inline_asm_func_seen)

        # to extract code snippets
        for issue in issues:
            issue.set_code_snippet(issue.get_code_snippets(lines, with_highlights=self.with_highlights))
            report.add_issue(issue)

    def finalize_report(self, report):
        pass

    def _register_incompatible_macro(self, line, ARCH_INCOMPATIBLE_INTRINSICS,
                                      ASSEMBLY_CHECKPOINTS, naive_cpp):
        """Register the macro name from a #define line if its body contains x64-incompatible
        intrinsics or inline asm (standard or previously-registered user-defined).
        Supports one level of transitivity: macros that reference other user-registered
        macros are also registered.
        """
        if naive_cpp.in_other_arch_specific_code():
            return
        m = _DEFINE_RE.match(line.lstrip())
        if not m:
            return
        macro_name = m.group(1)
        if macro_name in self._user_incompatible_macros:
            return
        # Check body against known intrinsic patterns
        for c in ARCH_INCOMPATIBLE_INTRINSICS:
            if c.pattern_compiled.search(line):
                self._user_incompatible_macros[macro_name] = (
                    re.compile(r'\b' + re.escape(macro_name) + r'\b'),
                    c.pattern,
                )
                return
        # Check body against known inline asm patterns
        for c in (ASSEMBLY_CHECKPOINTS or []):
            if c.pattern_compiled.search(line):
                self._user_incompatible_macros[macro_name] = (
                    re.compile(r'\b' + re.escape(macro_name) + r'\b'),
                    c.pattern,
                )
                return
        # Check body against already-registered user macros (one level of transitivity)
        for _, (compiled_pattern, orig_checkpoint) in self._user_incompatible_macros.items():
            if compiled_pattern.search(line):
                self._user_incompatible_macros[macro_name] = (
                    re.compile(r'\b' + re.escape(macro_name) + r'\b'),
                    orig_checkpoint,
                )
                return

    @staticmethod
    def _extract_function_code(lines, func_start_lineno):
        """Return (code, end_lineno) for the function starting at func_start_lineno.

        Brace-counts from the opening '{' to the matching '}'. Naive (doesn't
        strip string literals or comments), but good enough for display.
        Returns (None, None) when func_start_lineno is None.
        """
        if func_start_lineno is None:
            return None, None
        depth = 0
        result = []
        end_lineno = func_start_lineno
        max_lineno = max(lines.keys())
        for ln in range(func_start_lineno, max_lineno + 1):
            if ln not in lines:
                break
            line = lines[ln]
            result.append(line)
            depth += line.count('{') - line.count('}')
            if depth <= 0 and result:
                end_lineno = ln
                break
        return (''.join(result) if result else None), end_lineno

    def _check_directive(self, result: PreprocessorDirective,
                         # context
                         filename, lineno, line, function_parser,
                         PRAGMA_CHECKPOINTS, issues: List[Issue]):
        # if result.incomplete:
        #     # parse incomplete
        #     pass

        # error directive check
        # if result.directive_type == PreprocessorDirective.TYPE_ERROR and self.check_state:
        #     issues.append(PreprocessorErrorIssue(filename,
        #                                          lineno,
        #                                          line.strip(),
        #                                          checkpoint=function_parser.current_function))

        if result.directive_type == PreprocessorDirective.TYPE_PRAGMA and self.check_state:
            for c in PRAGMA_CHECKPOINTS:
                match = c.pattern_compiled.search(line)
                if match:
                    issues.append(PragmaIssue(filename,
                                              lineno,
                                              line.strip(),
                                              checkpoint=function_parser.current_function))

        # #if/#elif/#ifdef/#ifndef/#else/#endif
        elif result.directive_type == PreprocessorDirective.TYPE_CONDITIONAL:
            # if result.compiler_error:
            #     issues.append(CompilerSpecificIssue(filename,
            #                                         lineno,
            #                                         result.if_line.strip(),
            #                                         checkpoint=function_parser.current_function))
            # Always scan: non-aarch64 guards (#ifdef X86_AVX2, #else of #ifdef __aarch64__, etc.)
            # also contain code that needs porting and must be checked for incompatible intrinsics.
            self.check_state = True

    def _check_clang(self,
                     # context
                     lines, lineno, line, naive_cpp, filename,
                     ASSEMBLY_CHECKPOINTS, ARCH_INCOMPATIBLE_INTRINSICS,
                     # results
                     issues: List[Issue],
                     func_start_lineno=None, intrinsic_func_seen=None,
                     inline_asm_func_seen=None):
        # blank line
        if not lines[lineno].strip() or lines[lineno].strip() == '\n':
            return

        #  inline assembly check
        for c in ASSEMBLY_CHECKPOINTS:

            #  NOTE: inline asm can expand no more than two lines
            if (lineno + 4) <= len(lines.keys()):
                multiline = "".join([lines[_] for _ in range(lineno, lineno + 5)])
                match = c.pattern_compiled.search(multiline)
            elif (lineno + 3) <= len(lines.keys()):
                multiline = "".join([lines[_] for _ in range(lineno, lineno + 4)])
                match = c.pattern_compiled.search(multiline)
            elif (lineno + 2) <= len(lines.keys()):
                multiline = "".join([lines[_] for _ in range(lineno, lineno + 3)])
                match = c.pattern_compiled.search(multiline)
            elif (lineno + 1) <= len(lines.keys()):
                multiline = "".join([lines[_] for _ in range(lineno, lineno + 2)])
                match = c.pattern_compiled.search(multiline)
            else:
                match = c.pattern_compiled.search(line)

            if match and not naive_cpp.in_other_arch_specific_code():
                issue_lineno = func_start_lineno if func_start_lineno is not None else lineno
                if func_start_lineno is not None and inline_asm_func_seen is not None:
                    if issue_lineno in inline_asm_func_seen:
                        break
                    inline_asm_func_seen.add(issue_lineno)
                func_code, func_end_lineno = self._extract_function_code(lines, func_start_lineno)
                if self.locale.startswith('zh'):
                    issue = InlineAsmIssue(filename,
                                           lineno=issue_lineno,
                                           checkpoint=c.pattern,
                                           description='' if not c.help_zh else '\n' + c.help_zh)
                    issue.func_code = func_code
                    issue.func_end_lineno = func_end_lineno
                    issues.append(issue)
                    break
                if self.locale.startswith('en'):
                    issue = InlineAsmIssue(filename,
                                           lineno=issue_lineno,
                                           checkpoint=c.pattern,
                                           description='' if not c.help else '\n' + c.help)
                    issue.func_code = func_code
                    issue.func_end_lineno = func_end_lineno
                    issues.append(issue)
                    break

        #  intrinsics check
        for c in ARCH_INCOMPATIBLE_INTRINSICS:

            match = c.pattern_compiled.search(line)

            if match and not naive_cpp.in_other_arch_specific_code():
                issue_lineno = func_start_lineno if func_start_lineno is not None \
                    else find_matching_line_num(lines, lineno, c.pattern)
                if func_start_lineno is not None and intrinsic_func_seen is not None:
                    if issue_lineno in intrinsic_func_seen:
                        break
                    intrinsic_func_seen.add(issue_lineno)
                func_code, func_end_lineno = self._extract_function_code(lines, func_start_lineno)
                if self.locale.startswith('zh'):
                    issue = IntrinsicIssue(filename,
                                           lineno=issue_lineno,
                                           arch=self.arch,
                                           intrinsic=match.string.strip(),
                                           checkpoint=c.pattern,
                                           description='' if not c.help_zh else '\n' + c.help_zh)
                    issue.func_code = func_code
                    issue.func_end_lineno = func_end_lineno
                    issues.append(issue)
                    break
                if self.locale.startswith('en'):
                    issue = IntrinsicIssue(filename,
                                           lineno=issue_lineno,
                                           arch=self.arch,
                                           intrinsic=match.string.strip(),
                                           checkpoint=c.pattern,
                                           description='' if not c.help else '\n' + c.help)
                    issue.func_code = func_code
                    issue.func_end_lineno = func_end_lineno
                    issues.append(issue)
                    break

        #  user-defined macros that wrap x64-incompatible intrinsics
        if self._user_incompatible_macros and not naive_cpp.in_other_arch_specific_code():
            for macro_name, (compiled_pattern, orig_checkpoint) in self._user_incompatible_macros.items():
                if compiled_pattern.search(line):
                    issue_lineno = func_start_lineno if func_start_lineno is not None else lineno
                    if func_start_lineno is not None and intrinsic_func_seen is not None:
                        if issue_lineno in intrinsic_func_seen:
                            break
                        intrinsic_func_seen.add(issue_lineno)
                    func_code, func_end_lineno = self._extract_function_code(lines, func_start_lineno)
                    description = _("User-defined macro %s wraps x64-incompatible intrinsic: %s") % (
                        macro_name, orig_checkpoint)
                    issue = IntrinsicIssue(filename,
                                           lineno=issue_lineno,
                                           arch=self.arch,
                                           intrinsic=macro_name,
                                           checkpoint=orig_checkpoint,
                                           description=description)
                    issue.func_code = func_code
                    issue.func_end_lineno = func_end_lineno
                    issues.append(issue)
                    break

        #  cpp language check
        for c in CPP_STD_CODES:
            match = c.pattern_compiled.search(line)
            if match and not naive_cpp.in_other_arch_specific_code():
                if self.locale.startswith('zh'):
                    issues.append(CPPStdCodesIssue(filename,
                                               lineno=find_matching_line_num(lines, lineno, c.pattern),
                                               checkpoint=c.pattern,
                                               description='' if not c.help_zh else '\n' + c.help_zh))
                    break
                if self.locale.startswith('en'):
                    issues.append(CPPStdCodesIssue(filename,
                                                lineno=find_matching_line_num(lines, lineno, c.pattern),
                                                checkpoint=c.pattern,
                                                description='' if not c.help else '\n' + c.help))
                    break

        # arm64ec incompatible grammar check
        if self.arch == 'arm64ec':
            for c in ARM64EC_INCOMPATIBLE_GRAMMAR:
                match = c.pattern_compiled.search(line)
                if match and not naive_cpp.in_other_arch_specific_code():
                    if self.locale.startswith('zh'):
                        issues.append(ARM64ECIncompatibleGrammarIssue(filename,
                                                                    lineno=find_matching_line_num(lines, lineno, c.pattern),
                                                                    checkpoint=c.pattern,
                                                                    description='' if not c.help_zh else '\n' + c.help_zh))
                        break
                    if self.locale.startswith('en'):
                        issues.append(ARM64ECIncompatibleGrammarIssue(filename,
                                                                    lineno=find_matching_line_num(lines, lineno, c.pattern),
                                                                    checkpoint=c.pattern,
                                                                    description='' if not c.help else '\n' + c.help))
                        break