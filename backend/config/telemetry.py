"""OpenTelemetry setup. Called once inside each forked process (Gunicorn worker)."""
import os
import sys
import traceback

_started = False


def _enabled() -> bool:
    return os.getenv("OTEL_SDK_DISABLED", "true").strip().lower() in ("false", "0", "no")


def init_telemetry() -> None:
    global _started
    if _started or not _enabled():
        return
    _started = True
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create())
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

        DjangoInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()
        RedisInstrumentor().instrument(sanitize_query=True)

        print(f"[otel] tracing enabled in pid {os.getpid()}", file=sys.stderr, flush=True)
    except Exception:
        print("[otel] setup failed, continuing without tracing", file=sys.stderr, flush=True)
        traceback.print_exc()
