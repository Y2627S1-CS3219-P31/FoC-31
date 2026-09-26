from datetime import datetime

from pydantic import BaseModel

class OrderCreate(BaseModel):
    name: str
    details: str
    reward: int
    deadline: datetime
    supplier_id: str
    pickup_location: str
    delivery_location: str

class OrderResponse(BaseModel):
    id: int
    name: str
    details: str
    reward: int
    deadline: datetime
    supplier_id: str
    pickup_location: str
    delivery_location: str