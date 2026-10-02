"""Agent core namespace; import runtime components from their owning modules.

Keeping this package initializer free of runtime assembly lets lifecycle phases
import core values/support without recursively importing the passive pipeline.
"""
