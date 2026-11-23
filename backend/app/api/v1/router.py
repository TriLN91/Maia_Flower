from fastapi import APIRouter

from app.api.v1 import (
    admin_catalog,
    admin_inventory,
    admin_orders,
    auth,
    health,
    shop,
    shop_orders,
    staff,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(staff.router)
api_router.include_router(admin_catalog.router)
api_router.include_router(admin_inventory.router)
api_router.include_router(shop.router)
api_router.include_router(shop_orders.router)
api_router.include_router(admin_orders.router)
