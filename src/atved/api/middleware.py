"""
FastAPI middleware.

Request ID tracking, logging, and performance metrics.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger(__name__)

# Metrics
HTTP_REQUESTS = Counter(
    "atved_http_requests_total", 
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)
HTTP_LATENCY = Histogram(
    "atved_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)


class StructlogMiddleware(BaseHTTPMiddleware):
    """Middleware to inject request_id and log request lifecycles."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
        # Bind to structlog context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            client_ip=request.client.host if request.client else None
        )
        
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            process_time = time.perf_counter() - start_time
            
            # Record metrics
            HTTP_REQUESTS.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code
            ).inc()
            
            HTTP_LATENCY.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(process_time)
            
            # Log completion
            if request.url.path != "/metrics":  # Don't spam metrics endpoint
                logger.info(
                    "http.request",
                    status_code=response.status_code,
                    duration_ms=round(process_time * 1000, 2)
                )
                
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            return response
            
        except Exception as e:
            process_time = time.perf_counter() - start_time
            HTTP_REQUESTS.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=500
            ).inc()
            logger.exception("http.unhandled_exception", error=str(e))
            raise
