from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import time
import json
import urllib.parse
from datetime import datetime

app = FastAPI()

# CORRECTED CORS CONFIGURATION
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # <-- FIXED
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
TOTAL_ORDERS = 42
RATE_LIMIT = 16
WINDOW_SECONDS = 10

# Storage
orders_catalog = {}
orders_by_key = {}
order_id_counter = 0
client_requests = {}

def create_order_data(order_id: int):
    return {
        "id": order_id,
        "status": "created",
        "created_at": datetime.now().isoformat(),
        "item": f"Order #{order_id}",
        "amount": 100.0 + (order_id * 10),
    }

# Initialize orders
for i in range(1, TOTAL_ORDERS + 1):
    orders_catalog[i] = create_order_data(i)

print("=" * 50)
print("🚀 Orders API Server Started")
print("=" * 50)
print(f"📦 Total Orders: {TOTAL_ORDERS}")
print(f"🚦 Rate Limit: {RATE_LIMIT} requests per {WINDOW_SECONDS}s")
print("=" * 50)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id")
    
    if client_id and request.url.path not in ["/docs", "/openapi.json", "/redoc"]:
        current_time = time.time()
        
        if client_id not in client_requests:
            client_requests[client_id] = []
        
        cutoff_time = current_time - WINDOW_SECONDS
        client_requests[client_id] = [
            t for t in client_requests[client_id] if t > cutoff_time
        ]
        
        if len(client_requests[client_id]) >= RATE_LIMIT:
            oldest = min(client_requests[client_id])
            retry_after = int(WINDOW_SECONDS - (current_time - oldest) + 1)
            
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)}
            )
        
        client_requests[client_id].append(current_time)
    
    response = await call_next(request)
    return response

@app.get("/")
async def root():
    return {"message": "Welcome to Orders API!"}

@app.get("/health")
async def health():
    return {"status": "healthy", "total_orders": TOTAL_ORDERS}

@app.post("/orders", status_code=201)
async def create_order(
    idempotency_key: str = Header(..., alias="Idempotency-Key")
):
    global order_id_counter
    
    if idempotency_key in orders_by_key:
        return orders_by_key[idempotency_key]
    
    order_id_counter += 1
    new_order = create_order_data(order_id_counter)
    orders_by_key[idempotency_key] = new_order
    orders_catalog[order_id_counter] = new_order
    
    return new_order

@app.get("/orders")
async def get_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Limit must be positive")
    
    if limit > 100:
        limit = 100
    
    start_id = 1
    if cursor:
        try:
            decoded_cursor = urllib.parse.unquote(cursor)
            cursor_data = json.loads(decoded_cursor)
            start_id = cursor_data.get("last_id", 0) + 1
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")
    
    items = []
    for order_id in range(start_id, TOTAL_ORDERS + 1):
        if len(items) >= limit:
            break
        if order_id in orders_catalog:
            items.append(orders_catalog[order_id])
    
    next_cursor = None
    if len(items) == limit:
        last_id = items[-1]["id"]
        if last_id < TOTAL_ORDERS:
            next_cursor = json.dumps({"last_id": last_id})
    
    return {
        "items": items,
        "next_cursor": next_cursor
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)