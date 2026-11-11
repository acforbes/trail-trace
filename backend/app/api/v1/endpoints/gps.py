import math
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, status
from typing import Annotated
from pathlib import Path
from starlette.concurrency import run_in_threadpool

from app.schemas.gps import ProcessingResult, GPSJobForm
from app.services import gps as gps_service
from app.core.constants import MAX_UPLOAD_BYTES

router = APIRouter()

@router.post("/process-gps", response_model=ProcessingResult, status_code=status.HTTP_200_OK)
async def process_gps(
    file: Annotated[UploadFile, File(description="The GPS track log file")],
    form_data: Annotated[GPSJobForm, Depends()],
) -> ProcessingResult:
    """HTTP validation wrapper around the GPS core logic."""
    try:
        filename = file.filename or ""
        suffix = Path(filename.replace("\\", "/")).suffix.lower()
        if suffix not in {".gpx", ".tcx"}:
            raise HTTPException(status_code=400, detail="Upload a .gpx or .tcx track.")
        if not math.isfinite(form_data.radius_meters):
            raise HTTPException(status_code=400, detail="Radius must be a finite number.")
        if (form_data.start_latitude is None) != (form_data.start_longitude is None):
            raise HTTPException(
                status_code=400,
                detail="Provide both start latitude and longitude, or neither.",
            )

        content = await file.read(MAX_UPLOAD_BYTES + 1)
        await file.close()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Track files must be 25 MB or smaller.",
            )
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        # Hand off clean data types to the framework-agnostic logic layer
        return await run_in_threadpool(
            gps_service.process_gps_file,
            content=content,
            suffix=suffix,
            radius_meters=form_data.radius_meters,
            start_time=form_data.start_time,
            start_latitude=form_data.start_latitude,
            start_longitude=form_data.start_longitude,
        )

    except ValueError as e:
        # Map logic errors cleanly into HTTP exceptions
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
