"""
Android Environment Package

This package provides Android emulator environment management and automation capabilities.
"""

from .android_env import AndroidEnvironment
from .base import Environment

__all__ = ['AndroidEnvironment', 'Environment']
