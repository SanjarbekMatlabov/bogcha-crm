from pydantic import BaseModel, Field
from typing import List, Optional
import datetime
from database import UserRole # UserRole ni database.py dan import qilamiz

# --- Product Schemas ---
class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, example="Go'sht")
    # quantity_grams bu yerda create uchun boshlang'ich miqdor bo'lishi mumkin,
    # lekin odatda mahsulot turi yaratiladi, keyin unga ProductDelivery orqali miqdor qo'shiladi
    # Shuning uchun create da quantity_grams ni olib tashlashimiz mumkin yoki default=0 qoldirishimiz mumkin.
    # Agar yangi mahsulot turi kiritilayotganda darhol uning boshlang'ich miqdori ham kiritilsa:
    initial_quantity_grams: Optional[float] = Field(0.0, ge=0, example=1000.0) # Boshlang'ich miqdor
    delivery_date: Optional[datetime.datetime] = None # Bu birinchi kirim sanasi bo'lishi mumkin

class ProductCreate(ProductBase):
    pass # Boshlang'ich miqdor ProductBase dan keladi

class ProductUpdate(BaseModel): # Mahsulot nomini yangilash uchun
    name: Optional[str] = Field(None, min_length=1, example="Yangi Nom")
    # Miqdorni yangilash alohida endpoint orqali (ProductDelivery) amalga oshiriladi

class Product(BaseModel): # Productni qaytarish uchun schema
    id: int
    name: str
    quantity_grams: float # Ombordagi joriy miqdor
    delivery_date: Optional[datetime.datetime] # Oxirgi kirim sanasi

    class Config:
        orm_mode = True

# --- ProductDelivery Schemas (Yangi) ---
class ProductDeliveryBase(BaseModel):
    product_id: int
    quantity_received: float = Field(..., gt=0, example=5000.0) # 0 dan katta bo'lishi kerak
    delivery_date: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    supplier: Optional[str] = Field(None, example="Asosiy Yetkazib Beruvchi")

class ProductDeliveryCreate(ProductDeliveryBase):
    pass

class ProductDelivery(ProductDeliveryBase):
    id: int
    class Config:
        orm_mode = True

# --- MealIngredient Schemas (Recipe part) ---
class MealIngredientBase(BaseModel):
    product_id: int
    required_grams: float = Field(..., gt=0, example=150.0)

class MealIngredientCreate(MealIngredientBase):
    pass

class MealIngredientSchema(MealIngredientBase):
    id: int
    product: Product # Mahsulot ma'lumotlarini ham ko'rsatish uchun (o'zgarmagan)
    class Config:
        orm_mode = True

# --- Meal Schemas ---
class MealBase(BaseModel):
    name: str = Field(..., min_length=1, example="Osh")

class MealCreate(MealBase):
    ingredients: List[MealIngredientCreate] = []

class MealUpdate(MealBase): # Endi name va ingredients ni o'zgartirish mumkin
    ingredients: Optional[List[MealIngredientCreate]] = None

class Meal(MealBase):
    id: int
    ingredients: List[MealIngredientSchema] = []
    class Config:
        orm_mode = True

# --- MealServing Schemas ---
class ServeMealRequest(BaseModel): # Ovqat berish uchun so'rov modeli
    portions_to_serve: int = Field(..., gt=0, example=50) # Kamida 1 porsiya

class MealServingLogBase(BaseModel):
    meal_id: int
    portions_served: int # Qancha porsiya berilgani

class MealServingLogCreate(MealServingLogBase):
    pass # served_by_user_id va serving_time avtomatik olinadi

class MealServingLogSchema(MealServingLogBase):
    id: int
    served_by_user_id: int
    serving_time: datetime.datetime
    meal: Meal # Qaysi ovqat berilganini ko'rsatish uchun
    served_by: 'UserSchema' # Kim tomonidan berilganini ko'rsatish uchun (Circular import oldini olish)
    class Config:
        orm_mode = True

# --- User Schemas ---
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, example="admin_user")
    role: UserRole

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=6)

class UserSchema(UserBase):
    id: int
    is_active: bool
    class Config:
        orm_mode = True

MealServingLogSchema.update_forward_refs() # UserSchema uchun

# --- Token Schemas (o'zgarmagan) ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- Portion Calculation Schema (o'zgarmagan) ---
class PortionCalculationResponse(BaseModel):
    meal_id: int
    meal_name: str
    calculable_portions: int

# --- Alert Schemas (o'zgarmagan) ---
class LowStockAlert(BaseModel):
    product_id: int
    product_name: str
    current_quantity_grams: float
    message: str

class PotentialAbuseAlert(BaseModel):
    month: str
    prepared_portions: int
    potential_portions_at_month_end: int
    difference_percentage: float
    message: str

# --- Report Schemas (o'zgarmagan) ---
class MonthlyReportSchema(BaseModel):
    month: str
    total_prepared_portions: int # Bu endi MealServingLog.portions_served ni jamlashi kerak
    average_potential_portions: int
    difference_percentage: float
    potential_abuse_signal: bool

class IngredientConsumption(BaseModel):
    product_name: str
    total_consumed_grams: float
    consumption_periods: List[dict]
class DailyConsumptionDataPoint(BaseModel): # Yoki shunchaki DailyConsumption
    date: str = Field(..., example="2023-05-15")
    consumed_grams: float = Field(..., example=250.5)

    class Config:
        orm_mode = True
class AuditLogBase(BaseModel):
    username: Optional[str] = None
    # status_code: int
    method: str
    endpoint_path: str
    client_host: Optional[str] = None
    user_agent: Optional[str] = None
    details: str

class AuditLogCreate(AuditLogBase):
    pass

class AuditLogSchema(AuditLogBase):
    id: int
    timestamp: datetime.datetime

    class Config:
        orm_mode = True