"""
Labor Relations Platform API - Main application entry point.

Run with: py -m uvicorn api.main:app --reload --port 8001
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import PROJECT_ROOT, FILES_DIR
from .middleware.auth import AuthMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.logging import LoggingMiddleware
from .routers import (
    health,
    lookups,
    density,
    projections,
    employers,
    unions,
    nlrb,
    osha,
    organizing,
    whd,
    trends,
    corporate,
    vr,
    public_sector,
    museums,
    sectors,
)

app = FastAPI(
    title="Labor Relations Research API",
    version="7.0",
    description="Integrated platform: OLMS union data, F-7 employers, BLS density & projections, NLRB elections, OSHA safety",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(LoggingMiddleware)


# ---------- Frontend ----------
@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(str(FILES_DIR), "organizer_v5.html"))


app.mount("/files", StaticFiles(directory=str(FILES_DIR)), name="files")


# ---------- Routers ----------
app.include_router(health.router)
app.include_router(lookups.router)
app.include_router(density.router)
app.include_router(projections.router)
app.include_router(employers.router)
app.include_router(unions.router)
app.include_router(nlrb.router)
app.include_router(osha.router)
app.include_router(organizing.router)
app.include_router(whd.router)
app.include_router(trends.router)
app.include_router(corporate.router)
app.include_router(vr.router)
app.include_router(public_sector.router)
app.include_router(museums.router)
app.include_router(sectors.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
