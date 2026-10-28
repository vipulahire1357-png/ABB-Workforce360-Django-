#!/usr/bin/env python
"""Django's command-line utility for Workforce360."""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "workforce360.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
