#!/usr/bin/env python
import sys

from config.env import configure_django_settings


def main():
    # No Windows, o autoreloader do comando runserver fornecido pelo Daphne
    # pode iniciar duas cadeias do launcher da virtualenv e ambas tentarem
    # escutar a mesma porta (WinError 10048). O reload continua disponível
    # reiniciando o comando manualmente, enquanto o servidor fica estável.
    if sys.platform == "win32" and len(sys.argv) > 1 and sys.argv[1] == "runserver" and "--noreload" not in sys.argv:
        sys.argv.append("--noreload")
    configure_django_settings()
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
