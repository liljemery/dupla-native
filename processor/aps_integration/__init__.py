"""Autodesk Platform Services integration for the Dupla processor.

This file MUST exist: it makes ``aps_integration`` a regular package so it is
NOT shadowed by ``motor/aps_integration`` when ``motor/`` is on PYTHONPATH.
scripts/dev.sh exports ``DUPLA_ROOT=motor`` onto PYTHONPATH for the worker, and
``motor/aps_integration`` ships its own ``__init__.py``; without this file the
processor's namespace package loses the import race and the worker silently runs
motor's APS code instead of the processor's.
"""
