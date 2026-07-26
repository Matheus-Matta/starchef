import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = "8000"
DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = "5173"


class ManagedProcess:
    def __init__(self, name, command, cwd, env):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.env = env
        self.process = None
        self.thread = None

    def start(self):
        is_windows = os.name == "nt"
        kwargs = {
            "cwd": self.cwd,
            "env": self.env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
        }
        if is_windows:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["preexec_fn"] = os.setsid

        self.process = subprocess.Popen(self.command, **kwargs)
        self.thread = threading.Thread(target=self._stream_output, daemon=True)
        self.thread.start()

    def _stream_output(self):
        for line in self.process.stdout:
            print(f"[{self.name}] {line}", end="")

    def poll(self):
        return self.process.poll()

    def stop(self):
        if self.process.poll() is not None:
            return

        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return

        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)


class Command(BaseCommand):
    help = "Run local StarChef services in one terminal and stop all of them on Ctrl+C."

    def add_arguments(self, parser):
        parser.add_argument(
            "backend_addrport",
            nargs="?",
            help="Optional backend bind address, e.g. 0.0.0.0:8001 or 8001.",
        )
        parser.add_argument("--backend-host", default=None)
        parser.add_argument("--backend-port", default=None)
        parser.add_argument("--frontend-host", default=DEFAULT_FRONTEND_HOST)
        parser.add_argument("--frontend-port", default=DEFAULT_FRONTEND_PORT)
        parser.add_argument("--skip-frontend", action="store_true")
        parser.add_argument("--migrate", action="store_true")

    def handle(self, *args, **options):
        backend_dir = Path(settings.BASE_DIR)
        frontend_dir = backend_dir.parent / "frontend"
        env = self._build_env()
        backend_host, backend_port = self._resolve_backend_bind(options)
        frontend_env = self._build_frontend_env(env, backend_host, backend_port)

        # Libera a porta do backend antes de subir: evita o WinError 10048 ("porta ja em uso")
        # quando sobra um processo de uma execucao anterior que nao foi encerrado.
        self._free_port(backend_port)

        if options["migrate"]:
            self.stdout.write(self.style.NOTICE("Running migrations before starting services..."))
            self._run_once([sys.executable, "manage.py", "migrate"], backend_dir, env)

        if settings.DEBUG:
            # Dev: runserver do app daphne (ASGI + WebSocket) COM auto-reload ao salvar.
            backend_command = [
                sys.executable,
                "manage.py",
                "runserver",
                f"{backend_host}:{backend_port}",
            ]
        else:
            # Producao: daphne puro, sem auto-reload.
            backend_command = [
                sys.executable,
                "-m",
                "daphne",
                "-b",
                backend_host,
                "-p",
                str(backend_port),
                "config.asgi:application",
            ]

        backend_process = ManagedProcess(
            "backend",
            backend_command,
            backend_dir,
            env,
        )
        processes = []

        if not options["skip_frontend"]:
            if not frontend_dir.exists():
                raise CommandError(f"Frontend directory not found: {frontend_dir}")

            processes.append(
                ManagedProcess(
                    "frontend",
                    [
                        self._npm_command(),
                        "run",
                        "dev",
                        "--",
                        "--host",
                        options["frontend_host"],
                        "--port",
                        str(options["frontend_port"]),
                    ],
                    frontend_dir,
                    frontend_env,
                )
            )

        if settings.CELERY_TASK_ALWAYS_EAGER:
            self.stdout.write(
                self.style.WARNING(
                    "DEBUG/local memory is active: Celery runs tasks eagerly, so worker/beat are not started."
                )
            )
        else:
            processes.extend(
                [
                    ManagedProcess(
                        "celery-worker",
                        [sys.executable, "-m", "celery", "-A", "config", "worker", "-l", "info"],
                        backend_dir,
                        env,
                    ),
                    ManagedProcess(
                        "celery-beat",
                        [sys.executable, "-m", "celery", "-A", "config", "beat", "-l", "info"],
                        backend_dir,
                        env,
                    ),
                ]
            )

        if settings.DEBUG:
            self._run_dev_backend_in_foreground(
                backend_process,
                processes,
            )
        else:
            self._start_and_wait([backend_process, *processes])

    def _build_env(self):
        env = os.environ.copy()
        if env.get("STARCHEF_SETTINGS_AUTO") == "1":
            env.pop("DJANGO_SETTINGS_MODULE", None)
        else:
            env.setdefault("DJANGO_SETTINGS_MODULE", os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.development"))

        env["DJANGO_DEBUG"] = "True" if settings.DEBUG else "False"
        if settings.DEBUG:
            env.setdefault("USE_LOCAL_MEMORY_SERVICES", "True")
            env.setdefault("USE_SQLITE_DATABASE", "True")
        return env

    def _build_frontend_env(self, env, backend_host, backend_port):
        frontend_env = env.copy()
        frontend_env.setdefault("VITE_API_BASE_URL", self._frontend_api_base_url(backend_host, backend_port))
        return frontend_env

    def _frontend_api_base_url(self, backend_host, backend_port):
        browser_host = backend_host
        if browser_host in {"0.0.0.0", "::"}:
            browser_host = "localhost"
        if ":" in browser_host and not browser_host.startswith("["):
            browser_host = f"[{browser_host}]"
        return f"http://{browser_host}:{backend_port}/api/v1"

    def _resolve_backend_bind(self, options):
        backend_host = DEFAULT_BACKEND_HOST
        backend_port = DEFAULT_BACKEND_PORT

        if options["backend_addrport"]:
            backend_host, backend_port = self._parse_backend_addrport(options["backend_addrport"])

        if options["backend_host"] is not None:
            backend_host = options["backend_host"]
        if options["backend_port"] is not None:
            backend_port = options["backend_port"]

        self._validate_port(backend_port)
        return backend_host, backend_port

    def _parse_backend_addrport(self, value):
        value = value.strip()
        if not value:
            raise CommandError("Backend address cannot be empty.")

        if value.startswith("["):
            closing_bracket = value.find("]")
            if closing_bracket == -1 or value[closing_bracket + 1 : closing_bracket + 2] != ":":
                raise CommandError("Use IPv6 backend addresses in the form [::1]:8001.")
            backend_host = value[1:closing_bracket]
            backend_port = value[closing_bracket + 2 :]
        elif ":" in value:
            backend_host, backend_port = value.rsplit(":", 1)
            backend_host = backend_host or DEFAULT_BACKEND_HOST
        else:
            backend_host = DEFAULT_BACKEND_HOST
            backend_port = value

        return backend_host, backend_port

    def _validate_port(self, value):
        try:
            port = int(value)
        except (TypeError, ValueError):
            raise CommandError(f"Backend port must be a number: {value}") from None

        if port < 1 or port > 65535:
            raise CommandError(f"Backend port must be between 1 and 65535: {value}")

    def _run_once(self, command, cwd, env):
        result = subprocess.run(command, cwd=cwd, env=env, check=False)
        if result.returncode:
            if "manage.py" in command and "migrate" in command:
                raise CommandError(
                    f"Command failed with exit code {result.returncode}: {' '.join(command)}\n\n"
                    "If this is a disposable local SQLite database with inconsistent migration history, run: "
                    "python manage.py seed_demo --reset-sqlite"
                )
            raise CommandError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")

    def _start_and_wait(self, processes):
        self.stdout.write(self.style.SUCCESS("Starting services. Press Ctrl+C to stop all."))
        for process in processes:
            self.stdout.write(f"Starting {process.name}: {' '.join(process.command)}")
            process.start()

        try:
            while True:
                for process in processes:
                    exit_code = process.poll()
                    if exit_code is not None:
                        self._stop_all(processes)
                        raise CommandError(f"{process.name} exited with code {exit_code}")
                time.sleep(0.25)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nStopping services..."))
            self._stop_all(processes)
            self.stdout.write(self.style.SUCCESS("All services stopped."))

    def _run_dev_backend_in_foreground(self, backend, auxiliary_processes):
        """Mantem o Django preso ao terminal no desenvolvimento.

        O backend nao usa Popen nem um grupo de processo independente. Assim,
        fechar com Ctrl+C encerra o servidor e evita deixar a porta ocupada por
        um Daphne orfao no Windows.
        """
        self.stdout.write(
            self.style.SUCCESS(
                "Starting development services. The backend is running in the foreground; "
                "press Ctrl+C to stop."
            )
        )
        for process in auxiliary_processes:
            self.stdout.write(f"Starting {process.name}: {' '.join(process.command)}")
            process.start()

        self.stdout.write(f"Starting backend in foreground: {' '.join(backend.command)}")
        try:
            result = subprocess.run(
                backend.command,
                cwd=backend.cwd,
                env=backend.env,
                check=False,
            )
            if result.returncode not in {0, 130, 3221225786}:
                raise CommandError(f"backend exited with code {result.returncode}")
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nStopping development services..."))
        finally:
            self._stop_all(auxiliary_processes)
            self.stdout.write(self.style.SUCCESS("All development services stopped."))

    def _stop_all(self, processes):
        for process in processes:
            process.stop()

    def _npm_command(self):
        return "npm.cmd" if os.name == "nt" else "npm"

    def _free_port(self, port):
        """Encerra qualquer processo que ainda esteja escutando na porta do backend.

        Best-effort: se nada estiver na porta, nao faz nada. Torna o `runservices`
        idempotente — voce pode reiniciar sem precisar matar o processo antigo na mao.
        """
        pids = self._pids_on_port(str(port))
        if not pids:
            return
        self.stdout.write(self.style.WARNING(f"Porta {port} em uso por {', '.join(pids)}; liberando..."))
        for pid in pids:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                subprocess.run(["kill", "-9", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        time.sleep(1)

    def _pids_on_port(self, port):
        """PIDs escutando na porta (netstat no Windows, lsof no restante)."""
        try:
            if os.name == "nt":
                output = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, check=False).stdout
                pids = set()
                for line in output.splitlines():
                    parts = line.split()
                    # Ex.: TCP  0.0.0.0:8001  0.0.0.0:0  LISTENING  1234
                    if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].endswith(f":{port}"):
                        if parts[-1].isdigit() and parts[-1] != "0":
                            pids.add(parts[-1])
                return list(pids)
            result = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True, check=False)
            return [pid for pid in result.stdout.split() if pid.isdigit()]
        except Exception:
            return []
