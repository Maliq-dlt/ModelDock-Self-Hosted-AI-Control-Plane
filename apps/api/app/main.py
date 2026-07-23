from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, select
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.api.routes import router
from app.core.config import get_settings
from app.core.db import dispose_db, ensure_bootstrap_admin, init_db, session_factory
from app.models import AuditLog, RequestRecord

settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await ensure_bootstrap_admin()
    yield
    await dispose_db()

app = FastAPI(title="ModelDock API", version="0.1.0", lifespan=lifespan)
if settings.otel_exporter_otlp_endpoint:
    tracer_provider = TracerProvider(resource=Resource.create({"service.name": "modeldock-api"}))
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)))
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def enforce_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_request_body_bytes:
                return JSONResponse(status_code=413, content={"error": {"message": "Request body too large", "type": "request_too_large"}})
        except ValueError:
            return JSONResponse(status_code=400, content={"error": {"message": "Invalid content length", "type": "invalid_request"}})
    response = await call_next(request)
    if request.url.path.startswith("/api/") and request.method in {"POST", "PATCH", "PUT", "DELETE"} and not request.url.path.startswith("/api/auth/login"):
        try:
            actor = "admin-key" if request.headers.get("x-modeldock-admin-key") else "admin-session"
            async with session_factory() as session:
                session.add(AuditLog(actor=actor, action=f"{request.method} {request.url.path}", resource_type="api", resource_id=None, metadata_json={"status_code": response.status_code}))
                await session.commit()
        except Exception:
            pass
    return response

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    async with session_factory() as session:
        rows = (await session.execute(select(RequestRecord.status, func.count(RequestRecord.id)).group_by(RequestRecord.status))).all()
        total = sum(int(row[1]) for row in rows)
        lines = [
            "# HELP modeldock_requests_total Total gateway requests.",
            "# TYPE modeldock_requests_total counter",
            f"modeldock_requests_total {total}",
        ]
        for status, count in rows:
            lines.append(f'modeldock_requests_by_status{{status="{status}"}} {int(count)}')
        return "\n".join(lines) + "\n"

app.include_router(router)
