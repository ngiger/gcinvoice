# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from builtins import str
from builtins import object
# This is the Yet Another Python Templating Utility, Version 1.2
# Taken from the ActiveState python Cookbook recipe 52305
# by Alex Martelli (https://github.com/ActiveState/)
# Adapted by Roman Bertle for the needs of this module.
# Adapted by Fabian Köster for Python3 support

import sys


# utility stuff to avoid tests in the mainline code
class _nevermatch(object):
    "Polymorphic with a regex that never matches"
    def match(self, line):
        return None


_never = _nevermatch()     # one reusable instance of it suffices


def _identity(string, why):
    "A do-nothing-special-to-the-input, just-return-it function"
    return string


def _nohandle(string):
    "A do-nothing handler that just re-raises the exception"
    raise


# and now the real thing
class copier(object):
    "Smart-copier (YAPTU) class"
    def copyblock(self, i=0, last=None):
        "Main copy method: process lines [i,last) of block"
        def repl(match, self=self):
            "return the eval of a found expression, for replacement"
            # uncomment for debug: print '!!! replacing',match.group(1)
            expr = self.preproc(match.group(1), 'eval')
            try:
                return str(eval(expr, self.globals, self.locals))
            except:
                return str(self.handle(expr))
        block = self.locals['_bl']
        if last is None:
            last = len(block)
        while i < last:
            line = block[i]
            match = self.restat.match(line)
            if match:   # a statement starts "here" (at line block[i])
                # i is the last line to _not_ process
                stat = match.string[match.end(0):].strip()
                j = i+1   # look for 'finish' from here onwards
                nest = 1  # count nesting levels of statements
                while j < last:
                    line = block[j]
                    # first look for nested statements or 'finish' lines
                    if self.restend.match(line):    # found a statement-end
                        nest = nest - 1     # update (decrease) nesting
                        if nest == 0:
                            break   # j is first line to _not_ process
                    elif self.restat.match(line):   # found a nested statement
                        nest = nest + 1     # update (increase) nesting
                    elif nest == 1:
                        # look for continuation only at this nesting
                        match = self.recont.match(line)
                        if match:                   # found a contin.-statement
                            nestat = match.string[match.end(0):].strip()
                            stat = '%s _cb(%s,%s)\n%s' % (stat, i+1, j, nestat)
                            i = j  # again, i is the last line to _not_ process
                    j = j+1
                stat = self.preproc(stat, 'exec')
                stat = '%s _cb(%s,%s)' % (stat, i+1, j)
                # for debugging, uncomment...: print "-> Executing: {"+stat+"}"
                exec(stat, self.globals, self.locals)
                i = j+1
            else:       # normal line, just copy with substitution
                self.ouf.write(self.regex.sub(repl, line))
                i = i+1

    def __init__(self, regex=_never, dict={},
                 restat=_never, restend=_never, recont=_never,
                 preproc=_identity, handle=_nohandle, ouf=sys.stdout):
        "Initialize self's attributes"
        self.regex = regex
        self.globals = dict
        self.locals = {'_cb': self.copyblock}
        self.restat = restat
        self.restend = restend
        self.recont = recont
        self.preproc = preproc
        self.handle = handle
        self.ouf = ouf

    def copy(self, block=None, inf=sys.stdin):
        "Entry point: copy-with-processing a file, or a block of lines"
        if block is None:
            block = inf.readlines()
        self.locals['_bl'] = block
        self.copyblock()
