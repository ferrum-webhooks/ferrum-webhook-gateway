FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Argon2 allocates a 19 MiB buffer per hash. With glibc's default dynamic mmap threshold and
# per-thread arenas, each of the ~40 request threads kept its own freed 19 MiB buffer: 40 hashes
# across 40 threads peaked at 805 MiB (OOM-kill in a 384 MiB pod). A fixed 1 MiB mmap threshold
# makes big buffers return to the OS on free: same workload peaks at 106 MiB (measured).
ENV MALLOC_ARENA_MAX=2 MALLOC_MMAP_THRESHOLD_=1048576
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --system --uid 10001 ferrum && chown -R ferrum /app
USER 10001

EXPOSE 8000

# Schema migrations are NOT run here: with N replicas (and rolling updates) every pod would race
# to migrate. They run once, as a separate step: the `migrate` Job in k8s / service in compose
# (`alembic upgrade head`, same image).
#
# Exec form (no `sh -c`) so uvicorn is PID 1 and receives SIGTERM: it stops accepting, drains
# in-flight requests for up to --timeout-graceful-shutdown, then runs the lifespan shutdown.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "20", "--proxy-headers"]
