# app/api/v1/router.py
from fastapi import APIRouter
from app.api.v1 import endpoints

# 1. Define the router configuration
# router = APIRouter(
#     prefix="/items",
#     tags=["items"],
# )

# 2. Map paths and HTTP verbs to the endpoint handlers
# router.add_api_route("/", endpoint=endpoints.get_items, methods=["GET"])
# router.add_api_route("/{item_id}", endpoint=endpoints.get_item_by_id, methods=["GET"])
# router.add_api_route("/", endpoint=endpoints.create_item, methods=["POST"])

router = APIRouter()

router.add_api_route(
    path="/health",
    endpoint=endpoints.health,
    methods=["GET"]
)
