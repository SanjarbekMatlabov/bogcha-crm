from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLAlchemyEnum, Boolean
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
import datetime
import enum

DATABASE_URL = "sqlite:///./bogcha_app.db" # .db fayli loyiha papkasida paydo bo'ladi

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} # SQLite uchun kerak
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Foydalanuvchi rollari uchun Enum
class UserRole(str, enum.Enum):
    admin = "admin"
    chef = "chef"
    manager = "manager"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLAlchemyEnum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)

    served_meals = relationship("MealServingLog", back_populates="served_by")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    # Bu mahsulotning ombordagi joriy umumiy miqdori
    quantity_grams = Column(Float, nullable=False, default=0.0)
    # Oxirgi yetkazib berilgan sana (yoki birinchi kiritilgan sana)
    # Asosiy yetkazib berish tarixi ProductDelivery da bo'ladi
    delivery_date = Column(DateTime, default=datetime.datetime.utcnow)

    meal_ingredients = relationship("MealIngredient", back_populates="product")
    deliveries = relationship("ProductDelivery", back_populates="product", cascade="all, delete-orphan")


# YANGI MODEL: Mahsulot yetkazib berish (qabul qilish) uchun
class ProductDelivery(Base):
    __tablename__ = "product_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity_received = Column(Float, nullable=False) # Qabul qilingan miqdor
    delivery_date = Column(DateTime, default=datetime.datetime.utcnow) # Yetkazib berilgan sana
    supplier = Column(String, nullable=True) # Yetkazib beruvchi (ixtiyoriy)
    # Masalan, hisob-faktura raqami yoki boshqa ma'lumotlar uchun maydon qo'shish mumkin

    product = relationship("Product", back_populates="deliveries")


class Meal(Base):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    ingredients = relationship("MealIngredient", back_populates="meal", cascade="all, delete-orphan")
    serving_logs = relationship("MealServingLog", back_populates="meal")


class MealIngredient(Base):
    __tablename__ = "meal_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    meal_id = Column(Integer, ForeignKey("meals.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    required_grams = Column(Float, nullable=False) # Bir porsiya uchun kerakli miqdor

    meal = relationship("Meal", back_populates="ingredients")
    product = relationship("Product", back_populates="meal_ingredients")


class MealServingLog(Base):
    __tablename__ = "meal_serving_logs"

    id = Column(Integer, primary_key=True, index=True)
    meal_id = Column(Integer, ForeignKey("meals.id"), nullable=False)
    served_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    serving_time = Column(DateTime, default=datetime.datetime.utcnow)
    portions_served = Column(Integer, nullable=False, default=1) # YANGI USTUN: Berilgan porsiyalar soni

    meal = relationship("Meal", back_populates="serving_logs")
    served_by = relationship("User", back_populates="served_meals")


def create_db_and_tables():
    print("DATABASE.PY: `create_db_and_tables` chaqirildi. Jadvallar yaratilmoqda (agar mavjud bo'lmasa)...")
    Base.metadata.create_all(bind=engine)
    print("DATABASE.PY: Jadvallarni yaratish jarayoni tugadi.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()