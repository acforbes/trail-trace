from fastapi import APIRouter
from app.api.v1.endpoints import gps

v1_router = APIRouter()

# Includes your GPS route group under tags for clean Swagger documentation
v1_router.include_router(gps.router, tags=["GPS Processing"])
