import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.system import system_router
from app.api.v1.router import v1_router

app = FastAPI(
    title="GPS Track Analyzer API",
    version="1.0.0",
    description="API for processing GPS track logs and analyzing laps and routes.",
    contact={
        "name": "Trail Trace Support",
        "url": "https://trail-trace.com/support",
        "email": "support@trail-trace.com",
    },
)

# Define allowed origins
# Fetch from environment variables for production flexibility, default to local React Vite port
ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")

# Split comma-separated string into a clean Python list
origins = [origin.strip() for origin in ALLOWED_ORIGINS_ENV.split(",")]

# Apply the CORS security middleware layer
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # Whitelisted URLs allowed to talk to this API
    allow_credentials=True,           # Allows browser cookies/auth headers if needed
    allow_methods=["*"],              # Allows all standard HTTP methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],              # Allows all browser headers
)

app.include_router(system_router, prefix="/system")
app.include_router(v1_router, prefix="/api/v1")
app.include_router(v1_router, prefix="/api")
