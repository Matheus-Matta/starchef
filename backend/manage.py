#!/usr/bin/env python
import sys

from config.env import configure_django_settings


def main():
    configure_django_settings()
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
