import re


class Checkpoint:

    #  (?aiLmsux)
    #  ---
    #  (One or more letters from the set 'a', 'i', 'L', 'm', 's', 'u', 'x'.)
    #  The
    #  group matches the empty string; the letters set the corresponding flags:
    #  re.A (ASCII-only matching),
    #  re.I (ignore case),
    #  re.L (locale dependent),
    #  re.M (multi-line),
    #  re.S (dot matches all),
    #  re.U (Unicode matching)
    #  re.X (verbose),
    #  for the entire regular expression. (The flags are described in Module
    #  Contents.) This is useful if you wish to include the flags as part of the
    #  regular expression, instead of passing a flag argument to the
    #  re.compile() function. Flags should be used first in the expression
    #  string.
    re_func_name = re.compile(r'(?i)([0-9a-zA-Z_]+)\s*\(')

    def __init__(self, checkpoint):

        try:
            self.section = checkpoint
            self.isa = checkpoint.get("isa", default='').split(',')
            self.signature = checkpoint.get('signature', default='')
            self.pattern = checkpoint.get('pattern', default='')
            self.notes = checkpoint.get('notes', default='')
            # help text is in english, and help_zh is in chinese
            self.help = checkpoint.get('help', default='')
            self.help_zh = checkpoint.get('help-zh', default='')
            self.func_name = None

            #  in case there's no pattern provided, we use function name as the
            #  pattern, the function name was extracted from the fuction
            #  signature
            if not self.pattern:
                # extract the function name from the signature
                match = self.re_func_name.search(self.signature)
                if not match:
                    raise ValueError('invalid checkpoint %s' % checkpoint)
                # this is func_name like __cpuid
                func_name = match.group(1)
                # if function name found, compile it
                if func_name:
                    self.func_name = func_name
                    self.pattern_compiled = re.compile(r'(?i)({})\s*\('.format(func_name))
                else:
                    raise ValueError('invalid checkpoint %s' % checkpoint)

            else:
                self.pattern_compiled = re.compile(format(self.pattern))

        except BaseException:
            raise
