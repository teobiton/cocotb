# Copyright (c) 2013, 2018 Potential Ventures Ltd
# Copyright (c) 2013 SolarFlare Communications Inc
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of Potential Ventures Ltd,
#       SolarFlare Communications Inc nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL POTENTIAL VENTURES LTD BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Everything related to logging
"""

import logging
import os
import sys
from typing import TYPE_CHECKING, Union

from cocotb import _ANSI, simulator
from cocotb._deprecation import deprecated
from cocotb._utils import want_color_output
from cocotb.utils import get_sim_time, get_time_from_sim_steps

try:
    _suppress = int(os.environ.get("COCOTB_REDUCED_LOG_FMT", "1"))
except ValueError:
    _suppress = 1

# Column alignment
_LEVEL_CHARS = len("CRITICAL")
_RECORD_CHARS = 34
_FILENAME_CHARS = 20
_LINENO_CHARS = 4
_FUNCNAME_CHARS = 31

# Custom log level
logging.TRACE = 5  # type: ignore[attr-defined]  # type checkers don't like adding module attributes after the fact
logging.addLevelName(5, "TRACE")


def default_config() -> None:
    """Apply the default cocotb log formatting to the root logger.

    This hooks up the logger to write to stdout, using either
    :class:`SimColourLogFormatter` or :class:`SimLogFormatter` depending
    on whether colored output is requested. It also adds a
    :class:`SimTimeContextFilter` filter so that
    :attr:`~logging.LogRecord.created_sim_time` is available to the formatter.

    The logging level for cocotb logs is set based on the
    :envvar:`COCOTB_LOG_LEVEL` environment variable, which defaults to ``INFO``.

    The logging level for GPI logs is set based on the
    :envvar:`GPI_LOG_LEVEL` environment variable, which defaults to ``INFO``.

    If desired, this logging configuration can be overwritten by calling
    ``logging.basicConfig(..., force=True)`` (in Python 3.8 onwards), or by
    manually resetting the root logger instance.
    An example of this can be found in the section on :ref:`rotating-logger`.

    .. versionadded:: 1.4
    """
    # construct an appropriate handler
    hdlr = logging.StreamHandler(sys.stdout)
    hdlr.addFilter(SimTimeContextFilter())
    if want_color_output():
        hdlr.setFormatter(SimColourLogFormatter())
    else:
        hdlr.setFormatter(SimLogFormatter())

    logging.setLoggerClass(SimBaseLog)
    logging.basicConfig()
    logging.getLogger().handlers = [hdlr]  # overwrite default handlers

    def set_level(logger_name: str, envvar: str, default_level: str) -> None:
        log_level = os.environ.get(envvar, default_level)
        log_level = log_level.upper()

        logger = logging.getLogger(logger_name)

        try:
            logger.setLevel(log_level)
        except ValueError:
            valid_levels = ", ".join(
                ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE")
            )
            raise ValueError(
                f"Invalid log level {log_level!r} passed through the "
                f"{envvar} environment variable. Valid log "
                f"levels: {valid_levels}"
            )

    set_level("gpi", "GPI_LOG_LEVEL", "INFO")
    set_level("cocotb", "COCOTB_LOG_LEVEL", "INFO")


if TYPE_CHECKING:
    LoggerClass = logging.Logger
else:
    LoggerClass = logging.getLoggerClass()


class SimBaseLog(LoggerClass):
    # For hooking setLevel to inform the GPI's local log level

    def setLevel(self, level: Union[int, str]) -> None:
        super().setLevel(level)
        if self.name == "gpi":
            simulator.set_gpi_log_level(self.getEffectiveLevel())


@deprecated('Use `logging.getLogger(f"{name}.0x{ident:x}")` instead')
def SimLog(name: str, ident: Union[int, None] = None) -> logging.Logger:
    """Like logging.getLogger, but append a numeric identifier to the name.

    Args:
        name: Logger name.
        ident: Unique integer identifier.

    Returns:
        The Logger named ``{name}.0x{ident:x}``.

    .. deprecated:: 2.0

        Use ``logging.getLogger(f"{name}.0x{ident:x}")`` instead.
    """
    if ident is not None:
        name = f"{name}.0x{ident:x}"
    return logging.getLogger(name)


class SimTimeContextFilter(logging.Filter):
    """
    A filter to inject simulator times into the log records.

    This uses the approach described in the :ref:`Python logging cookbook <python:filters-contextual>`.

    This adds the :attr:`~logging.LogRecord.created_sim_time` attribute.

    .. versionadded:: 1.4
    """

    # needed to make our docs render well
    def __init__(self) -> None:
        """"""
        super().__init__()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.created_sim_time = get_sim_time()
        except RecursionError:
            # get_sim_time may try to log - if that happens, we can't
            # attach a simulator time to this message.
            record.created_sim_time = None
        return True


class SimLogFormatter(logging.Formatter):
    """Log formatter to provide consistent log message handling.

    This will only add simulator timestamps if the handler object this
    formatter is attached to has a :class:`SimTimeContextFilter` filter
    attached, which cocotb ensures by default.
    """

    # Removes the arguments from the base class. Docstring needed to make
    # sphinx happy.
    def __init__(self) -> None:
        """Takes no arguments."""
        super().__init__()

    # Justify and truncate
    @staticmethod
    def ljust(string: str, chars: int) -> str:
        if len(string) > chars:
            return ".." + string[(chars - 2) * -1 :]
        return string.ljust(chars)

    @staticmethod
    def rjust(string: str, chars: int) -> str:
        if len(string) > chars:
            return ".." + string[(chars - 2) * -1 :]
        return string.rjust(chars)

    def _format(
        self, level: str, record: logging.LogRecord, msg: str, coloured: bool = False
    ) -> str:
        sim_time = getattr(record, "created_sim_time", None)
        if sim_time is None:
            sim_time_str = "  -.--ns"
        else:
            time_ns = get_time_from_sim_steps(sim_time, "ns")
            sim_time_str = f"{time_ns:6.2f}ns"
        prefix = (
            sim_time_str.rjust(11)
            + " "
            + level
            + " "
            + self.ljust(record.name, _RECORD_CHARS)
            + " "
        )
        if not _suppress:
            prefix += (
                self.rjust(os.path.split(record.filename)[1], _FILENAME_CHARS)
                + ":"
                + self.ljust(str(record.lineno), _LINENO_CHARS)
                + " in "
                + self.ljust(str(record.funcName), _FUNCNAME_CHARS)
                + " "
            )

        # these lines are copied from the built-in logger
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if msg[-1:] != "\n":
                msg = msg + "\n"
            msg = msg + record.exc_text

        prefix_len = len(prefix)
        if coloured:
            prefix_len -= len(level) - _LEVEL_CHARS
        pad = "\n" + " " * (prefix_len)
        return prefix + pad.join(msg.split("\n"))

    def format(self, record: logging.LogRecord) -> str:
        """Prettify the log output by annotating with simulation time."""

        msg = record.getMessage()
        level = record.levelname.ljust(_LEVEL_CHARS)

        return self._format(level, record, msg)


class SimColourLogFormatter(SimLogFormatter):
    """Log formatter to provide consistent log message handling."""

    loglevel2colour = {
        logging.TRACE: "%s",  # type: ignore[attr-defined]  # type checkers don't like adding module attributes after the fact
        logging.DEBUG: "%s",
        logging.INFO: "%s",
        logging.WARNING: _ANSI.COLOR_WARNING + "%s" + _ANSI.COLOR_DEFAULT,
        logging.ERROR: _ANSI.COLOR_ERROR + "%s" + _ANSI.COLOR_DEFAULT,
        logging.CRITICAL: _ANSI.COLOR_CRITICAL + "%s" + _ANSI.COLOR_DEFAULT,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Prettify the log output by annotating with simulation time."""

        msg = record.getMessage()

        # Need to colour each line in case coloring is applied in the message
        msg = "\n".join(
            [
                SimColourLogFormatter.loglevel2colour.get(record.levelno, "%s") % line
                for line in msg.split("\n")
            ]
        )
        level = SimColourLogFormatter.loglevel2colour.get(
            record.levelno, "%s"
        ) % record.levelname.ljust(_LEVEL_CHARS)

        return self._format(level, record, msg, coloured=True)


def _filter_from_c(logger_name: str, level: int) -> bool:
    return logging.getLogger(logger_name).isEnabledFor(level)


def _log_from_c(
    logger_name: str,
    level: int,
    filename: str,
    lineno: int,
    msg: str,
    function_name: str,
) -> None:
    """
    This is for use from the C world, and allows us to insert C stack
    information.
    """
    logger = logging.getLogger(logger_name)
    if logger.isEnabledFor(level):
        record = logger.makeRecord(
            logger.name, level, filename, lineno, msg, (), None, function_name
        )
        logger.handle(record)
