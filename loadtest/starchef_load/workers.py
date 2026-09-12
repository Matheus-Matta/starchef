"""Geracao de carga: ritmo alvo (open-loop) + pool de threads.

Duas formas de medir sao diferentes de proposito:

- `Pacer` define a taxa de CHEGADA desejada (ex.: 1000/s). Se o servidor nao
  aguenta, a fila de trabalho cresce e isso aparece como saturacao — que e
  justamente o que queremos ver.
- o pool tem tamanho fixo: mais threads nao consertam um backend saturado,
  so escondem o problema atras da latencia.
"""
import queue
import threading
import time


class Pacer:
    """Distribui horarios de disparo para atingir uma taxa alvo."""

    def __init__(self, rate_per_second):
        self.rate = float(rate_per_second or 0)
        self._lock = threading.Lock()
        self._next = None
        self.late_slots = 0

    def wait(self):
        if self.rate <= 0:
            return
        interval = 1.0 / self.rate
        with self._lock:
            now = time.perf_counter()
            if self._next is None or self._next < now - 1.0:
                self._next = now
            slot = self._next
            self._next += interval
            if slot < now:
                self.late_slots += 1
        delay = slot - time.perf_counter()
        if delay > 0:
            time.sleep(delay)


class Stop(Exception):
    """Sinaliza fim de carga para dentro de um worker."""


class LoadRunner:
    """Executa `task(worker_index)` em N threads ate acabar tempo ou contagem."""

    def __init__(self, workers=32, rate=0, duration=0, count=0):
        self.workers = max(1, int(workers))
        self.pacer = Pacer(rate)
        self.duration = float(duration or 0)
        self.count = int(count or 0)
        self._issued = 0
        self._lock = threading.Lock()
        self._deadline = None
        self.stopped = threading.Event()

    def _claim(self):
        if self.stopped.is_set():
            return False
        if self._deadline and time.perf_counter() >= self._deadline:
            return False
        with self._lock:
            if self.count and self._issued >= self.count:
                return False
            self._issued += 1
        return True

    def run(self, task, on_error=None):
        """`task(worker_index, iteration)` roda em laco ate o criterio de parada."""
        self._deadline = time.perf_counter() + self.duration if self.duration else None
        threads = []

        def loop(index):
            iteration = 0
            while self._claim():
                self.pacer.wait()
                try:
                    task(index, iteration)
                except Exception as exc:  # noqa: BLE001 - carga nao pode morrer por um caso
                    if on_error:
                        on_error(exc)
                iteration += 1

        for index in range(self.workers):
            thread = threading.Thread(target=loop, args=(index,), daemon=True, name=f"load-{index}")
            thread.start()
            threads.append(thread)
        try:
            for thread in threads:
                thread.join()
        except KeyboardInterrupt:
            self.stopped.set()
            raise
        return self._issued


def run_parallel(items, worker, workers=16, on_error=None):
    """Roda `worker(item)` para cada item, com um pool simples."""
    work = queue.Queue()
    for item in items:
        work.put(item)

    def loop():
        while True:
            try:
                item = work.get_nowait()
            except queue.Empty:
                return
            try:
                worker(item)
            except Exception as exc:  # noqa: BLE001
                if on_error:
                    on_error(exc)
            finally:
                work.task_done()

    threads = [threading.Thread(target=loop, daemon=True) for _ in range(max(1, min(workers, len(items) or 1)))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
