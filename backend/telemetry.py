import json
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult, SpanExporter

from database import get_connection


def trace_id_from_span(span):
    return f'{span.get_span_context().trace_id:032x}'


class PostgresSpanExporter(SpanExporter):
    def export(self, spans):
        rows = []
        for span in spans:
            context = span.get_span_context()
            if not context.is_valid:
                continue
            attributes = dict(span.attributes or {})
            start_time = datetime.fromtimestamp(span.start_time / 1_000_000_000, tz=timezone.utc)
            end_time = datetime.fromtimestamp(span.end_time / 1_000_000_000, tz=timezone.utc)
            rows.append(
                (
                    f'{context.trace_id:032x}',
                    f'{context.span_id:016x}',
                    f'{span.parent.span_id:016x}' if span.parent and span.parent.is_valid else None,
                    span.name,
                    span.kind.name,
                    span.status.status_code.name.lower(),
                    span.status.description or None,
                    start_time,
                    end_time,
                    round((span.end_time - span.start_time) / 1_000_000),
                    attributes.get('credit.deal_id'),
                    attributes.get('credit.section_number'),
                    attributes.get('credit.draft_id'),
                    attributes.get('credit.workflow'),
                    json.dumps(attributes, default=str),
                )
            )
        if not rows:
            return SpanExportResult.SUCCESS

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO otel_spans (
                            trace_id, span_id, parent_span_id, span_name, span_kind,
                            status, status_message, start_time, end_time, duration_ms,
                            deal_id, section_number, draft_id, workflow, attributes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (trace_id, span_id) DO NOTHING;
                        """,
                        rows,
                    )
                conn.commit()
        except Exception:
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS


def configure_telemetry():
    provider = TracerProvider(resource=Resource.create({'service.name': 'credit-pitch-book-backend'}))
    provider.add_span_processor(SimpleSpanProcessor(PostgresSpanExporter()))
    trace.set_tracer_provider(provider)


def get_tracer():
    return trace.get_tracer('credit-pitch-book')
