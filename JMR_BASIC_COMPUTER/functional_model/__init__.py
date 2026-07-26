"""JMR BASIC Computer -- Python Functional Model.

Constitution, PYTHON REFERENCE MODEL:

    Every subsystem exists first in Python.
    The Python model is the behavioral truth.

This package is that model.  It is a computer, not an interpreter: the token
stream is its machine code, the dispatch table decodes it, and microcode drives
independent engines that share one 64K address space.

    from functional_model import Machine

    machine = Machine()
    machine.boot()
    machine.type_line('10 PRINT "HELLO"')
    machine.type_line("RUN")
    print(machine.screen_text())
"""

from .machine import Machine
from .memory import Memory
from .sequencer import Status

__all__ = ["Machine", "Memory", "Status"]
