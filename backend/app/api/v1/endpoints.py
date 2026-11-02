# app/api/v1/items/endpoints.py
# from fastapi import Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from app.dependencies import get_db
# from app.schemas.item import ItemCreate, ItemResponse
# from app.services import item_service

# async def get_items(db: Session = Depends(get_db)) -> list[ItemResponse]:
#     return item_service.all_items(db)

# async def get_item_by_id(item_id: int, db: Session = Depends(get_db)) -> ItemResponse:
#     item = item_service.get_by_id(db, item_id)
#     if not item:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
#     return item

# async def create_item(payload: ItemCreate, db: Session = Depends(get_db)) -> ItemResponse:
#     return item_service.create(db, payload)

async def health() -> dict[str, str]:
    return {"status": "ok"}
