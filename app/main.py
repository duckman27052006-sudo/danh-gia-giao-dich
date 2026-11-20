from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import BASE_DIR, settings
from app.db import SessionLocal, engine, init_db
from app.ml.service import metadata
from app.routers import audit, auth, cases, dashboard, rules, transactions, users
from app.routers import settings as settings_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("fraudlens")

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
STATIC_CACHE = "public, max-age=31536000, immutable"

# Chỉ áp cho trang SPA (không áp cho /api nên Swagger UI vẫn chạy bình thường).
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

WEAK_JWT_SECRETS = {"", "dev-only-change-me-in-production", "change-me"}


def _validate_production_config() -> None:
    """Chặn khởi động production với cấu hình nguy hiểm thay vì chỉ cảnh báo."""
    if not settings.is_production:
        return
    problems: list[str] = []
    if len(settings.jwt_secret) < 32 or settings.jwt_secret in WEAK_JWT_SECRETS:
        problems.append("JWT_SECRET phải là chuỗi ngẫu nhiên >= 32 ký tự (không dùng giá trị mặc định)")
    if not settings.cookie_secure:
        problems.append("COOKIE_SECURE phải = true khi chạy sau HTTPS")
    if "*" in settings.cors_origin_list:
        problems.append("CORS_ORIGINS không được để '*' khi allow_credentials=true")
    if problems:
        raise RuntimeError("Cấu hình production chưa an toàn: " + "; ".join(problems))

    if settings.demo_mode:
        logger.warning(
            "DEMO_MODE=true trên production — tài khoản demo dùng mật khẩu công khai, "
            "ai biết email cũng đăng nhập được. Đổi mật khẩu hoặc tắt DEMO_MODE trước khi mở rộng."
        )
    if settings.seed_on_start and not settings.demo_mode:
        logger.warning("SEED_ON_START=true trên production: dữ liệu demo sẽ được tạo vào database thật.")
    if settings.trust_proxy_headers:
        logger.info("TRUST_PROXY_HEADERS=true — X-Forwarded-For được tin cậy (chỉ bật khi có reverse proxy).")
    else:
        logger.info("TRUST_PROXY_HEADERS=false — dùng IP kết nối trực tiếp, không đọc X-Forwarded-For.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _validate_production_config()
    init_db()
    if settings.seed_on_start:
        from app.seed import seed_demo_data, seed_summary

        with SessionLocal() as db:
            seed_demo_data(db)
            logger.info("Demo data ready: %s", seed_summary(db))
    try:
        logger.info("Model loaded: %s", metadata()["version"])
    except Exception as exc:  # pragma: no cover - chỉ log khi artifact lỗi
        logger.warning("Không tải được model: %s", exc)
    yield


app = FastAPI(
    title="FraudLens API",
    description="Hệ thống chấm điểm rủi ro giao dịch có AI giải thích cảnh báo.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.docs_visible else None,
    redoc_url="/api/redoc" if settings.docs_visible else None,
    openapi_url="/api/openapi.json" if settings.docs_visible else None,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
if settings.allowed_host_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > settings.max_body_bytes:
        return JSONResponse(status_code=413, content={"detail": "Request quá lớn"})

    response = await call_next(request)
    path = request.url.path
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif path.startswith("/assets/"):
        response.headers["Cache-Control"] = STATIC_CACHE
    else:
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY

    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Có lỗi xảy ra, vui lòng thử lại."})


@app.get("/api/health", tags=["system"])
def health() -> dict:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        model_meta = metadata()
        return {
            "status": "ok",
            "database": engine.dialect.name,
            "model": model_meta["version"],
            "model_auc": model_meta["auc"],
            "environment": settings.environment,
            "demo_mode": settings.demo_mode,
        }
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "degraded", "detail": str(exc)})


app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api"):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        status_code=200,
        content={
            "service": "FraudLens API",
            "docs": "/api/docs",
            "note": "Frontend chưa build. Chạy npm run build trong thư mục frontend.",
        },
    )


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
