from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from app.core.config import settings

def setup_telemetry():
    provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
    try:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)))
    except Exception:
        pass
    trace.set_tracer_provider(provider)

def tracer():
    return trace.get_tracer("enterprise-operations-agent")
