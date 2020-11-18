"""cliutil - Utilities for CLI tools"""
PKGNAME = 'paypal_rest'
LICENSE = """
Copyright © 2020  Brett Smith

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>."""

import argparse
import enum
import logging
import operator
import os
import pkg_resources
import signal
import sys
import traceback
import types

from pathlib import Path

import requests

from typing import (
    Any,
    Callable,
    Iterator,
    NoReturn,
    Optional,
    Sequence,
    TextIO,
    Type,
    Union,
)

VERSION = pkg_resources.require(PKGNAME)[0].version

class ExceptHook:
    def __init__(self, logger: Optional[logging.Logger]=None) -> None:
        if logger is None:
            logger = logging.getLogger()
        self.logger = logger

    def __call__(self,
                 exc_type: Type[BaseException],
                 exc_value: BaseException,
                 exc_tb: types.TracebackType,
    ) -> NoReturn:
        error_type = type(exc_value).__name__
        msg = ": ".join(str(arg) for arg in exc_value.args)
        if isinstance(exc_value, KeyboardInterrupt):
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            os.kill(0, signal.SIGINT)
            signal.pause()
        elif isinstance(exc_value, requests.HTTPError):
            error_type = "PayPal API error"
            if exc_value.response is None:
                status_code = 500
            else:
                status_code = exc_value.response.status_code
            if (status_code == requests.codes.UNAUTHORIZED
                or status_code == requests.codes.FORBIDDEN):
                exitcode = os.EX_NOPERM
            elif status_code < 500:
                exitcode = os.EX_SOFTWARE
            else:
                exitcode = os.EX_UNAVAILABLE
        elif isinstance(exc_value, OSError):
            if exc_value.filename is None:
                exitcode = os.EX_OSERR
                error_type = "OS error"
                msg = exc_value.strerror
            else:
                # There are more specific exit codes for input problems vs.
                # output problems, but without knowing how the file was
                # intended to be used, we can't use them.
                exitcode = os.EX_IOERR
                error_type = "I/O error"
                msg = f"{exc_value.filename}: {exc_value.strerror}"
        else:
            exitcode = os.EX_SOFTWARE
            error_type = f"internal {error_type}"
        self.logger.critical("%s%s%s", error_type, ": " if msg else "", msg)
        self.logger.debug(
            ''.join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        raise SystemExit(exitcode)


class InfoAction(argparse.Action):
    def __call__(self,
                 parser: argparse.ArgumentParser,
                 namespace: argparse.Namespace,
                 values: Union[Sequence[Any], str, None]=None,
                 option_string: Optional[str]=None,
    ) -> NoReturn:
        if isinstance(self.const, str):
            info = self.const
            exitcode = 0
        else:
            info, exitcode = self.const
        print(info)
        raise SystemExit(exitcode)


class LogLevel(enum.IntEnum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    WARN = WARNING
    ERR = ERROR
    CRIT = CRITICAL

    @classmethod
    def from_arg(cls, arg: str) -> int:
        try:
            return cls[arg.upper()].value
        except KeyError:
            raise ValueError(f"unknown loglevel {arg!r}") from None

    @classmethod
    def choices(cls) -> Iterator[str]:
        for level in sorted(cls, key=operator.attrgetter('value')):
            yield level.name.lower()


def add_loglevel_argument(parser: argparse.ArgumentParser,
                          default: LogLevel=LogLevel.INFO) -> argparse.Action:
    return parser.add_argument(
        '--loglevel',
        metavar='LEVEL',
        default=default.value,
        type=LogLevel.from_arg,
        help="Show logs at this level and above."
        f" Specify one of {', '.join(LogLevel.choices())}."
        f" Default {default.name.lower()}.",
    )

def add_version_argument(parser: argparse.ArgumentParser) -> argparse.Action:
    progname = parser.prog or sys.argv[0]
    return parser.add_argument(
        '--version', '--copyright', '--license',
        action=InfoAction,
        nargs=0,
        const=f"{progname} version {VERSION}\n{LICENSE}",
        help="Show program version and license information",
    )

def make_entry_point(mod_name: str, prog_name: str=sys.argv[0]) -> Callable[[], int]:
    """Create an entry_point function for a tool

    The returned function is suitable for use as an entry_point in setup.py.
    It sets up the root logger and excepthook, then calls the module's main
    function.
    """
    def entry_point():  # type:ignore
        prog_mod = sys.modules[mod_name]
        setup_logger()
        prog_mod.logger = logging.getLogger(prog_name)
        sys.excepthook = ExceptHook(prog_mod.logger)
        return prog_mod.main()
    return entry_point

def setup_logger(logger: Union[str, logging.Logger]='',
                 stream: TextIO=sys.stderr,
                 fmt: str='%(name)s: %(levelname)s: %(message)s',
) -> logging.Logger:
    """Set up a logger with a StreamHandler with the given format"""
    if isinstance(logger, str):
        logger = logging.getLogger(logger)
    formatter = logging.Formatter(fmt)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def set_loglevel(logger: logging.Logger, loglevel: int=logging.INFO) -> None:
    """Set the loglevel for a tool or module

    If the given logger is not under a hierarchy, this function sets the
    loglevel for the root logger, along with some specific levels for libraries
    used by reporting tools. Otherwise, it's the same as
    ``logger.setLevel(loglevel)``.
    """
    if '.' not in logger.name:
        logger = logging.getLogger()
    logger.setLevel(loglevel)
