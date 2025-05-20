from sqlalchemy.orm import Session, relationship # relationship ni import qildik
from sqlalchemy import func, extract
import database, schemas, security # 'database' ni 'app.database' deb o'zgartirish mumkin, agar app papkasi PYTHONPATH da bo'lsa
import datetime
from typing import List, Optional

# --- User CRUD (o'zgarmagan, faqat database.User ni to'g'ri ishlatish) ---
def get_user(db: Session, user_id: int) -> Optional[database.User]:
    return db.query(database.User).filter(database.User.id == user_id).first()

def get_user_by_username(db: Session, username: str) -> Optional[database.User]:
    return db.query(database.User).filter(database.User.username == username).first()

def get_users(db: Session, skip: int = 0, limit: int = 100) -> List[database.User]:
    return db.query(database.User).offset(skip).limit(limit).all()

def create_user(db: Session, user: schemas.UserCreate) -> database.User:
    hashed_password = security.get_password_hash(user.password)
    db_user = database.User(
        username=user.username,
        hashed_password=hashed_password,
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate) -> Optional[database.User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    update_data = user_update.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        hashed_password = security.get_password_hash(update_data["password"])
        db_user.hashed_password = hashed_password
        del update_data["password"]
    for key, value in update_data.items():
        setattr(db_user, key, value)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int) -> Optional[database.User]:
    db_user = get_user(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user

# --- Product CRUD (O'zgartirilgan) ---
def get_product(db: Session, product_id: int) -> Optional[database.Product]:
    return db.query(database.Product).filter(database.Product.id == product_id).first()

def get_product_by_name(db: Session, name: str) -> Optional[database.Product]:
    return db.query(database.Product).filter(database.Product.name == name).first()

def get_products(db: Session, skip: int = 0, limit: int = 100) -> List[database.Product]:
    return db.query(database.Product).order_by(database.Product.name).offset(skip).limit(limit).all()

def create_product_type(db: Session, product_in: schemas.ProductCreate) -> database.Product:
    """Yangi mahsulot TURINI yaratadi (agar mavjud bo'lmasa). Miqdor ProductDelivery orqali qo'shiladi."""
    existing_product = get_product_by_name(db, name=product_in.name)
    if existing_product:
        raise ValueError(f"Product type with name '{product_in.name}' already exists. Use receive stock endpoint to add quantity.")

    db_product = database.Product(
        name=product_in.name,
        quantity_grams=0, # Boshlang'ich miqdor 0, ProductDelivery orqali qo'shiladi
        delivery_date=product_in.delivery_date or datetime.datetime.utcnow() # Birinchi kiritilgan sana
    )
    if product_in.initial_quantity_grams > 0 :
        # Agar boshlang'ich miqdor berilsa, uni ham ProductDelivery orqali kiritamiz
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        # Boshlang'ich miqdorni ProductDelivery sifatida qo'shish
        initial_delivery = schemas.ProductDeliveryCreate(
            product_id=db_product.id,
            quantity_received=product_in.initial_quantity_grams,
            delivery_date=db_product.delivery_date, # Mahsulot yaratilgan sana
            supplier="Initial Stock"
        )
        create_product_delivery(db, delivery_in=initial_delivery, product_obj=db_product)
    else:
        db.add(db_product)
        db.commit()
        db.refresh(db_product)

    return db_product


def update_product_name(db: Session, product_id: int, product_update: schemas.ProductUpdate) -> Optional[database.Product]:
    """Faqat mahsulot nomini yangilaydi."""
    db_product = get_product(db, product_id)
    if not db_product:
        return None
    if product_update.name is not None:
        # Yangi nom boshqa mahsulotda mavjud emasligini tekshirish (agar nom unique bo'lsa)
        existing_product_with_new_name = get_product_by_name(db, name=product_update.name)
        if existing_product_with_new_name and existing_product_with_new_name.id != product_id:
            raise ValueError(f"Product with name '{product_update.name}' already exists.")
        db_product.name = product_update.name
        db.commit()
        db.refresh(db_product)
    return db_product

def delete_product(db: Session, product_id: int) -> Optional[database.Product]:
    db_product = get_product(db, product_id)
    if db_product:
        if db_product.meal_ingredients: # Bu bog'liqlikni tekshirish
            raise ValueError(f"Product '{db_product.name}' is used in meal recipes and cannot be deleted first.")
        # ProductDelivery yozuvlari ham cascade orqali o'chishi kerak (modelda to'g'ri sozlanganda)
        db.delete(db_product)
        db.commit()
    return db_product


# --- ProductDelivery CRUD (Yangi) ---
def create_product_delivery(db: Session, delivery_in: schemas.ProductDeliveryCreate, product_obj: Optional[database.Product] = None) -> database.ProductDelivery:
    if not product_obj:
        product_obj = get_product(db, delivery_in.product_id)
    
    if not product_obj:
        raise ValueError(f"Product with ID {delivery_in.product_id} not found to record delivery.")

    db_delivery = database.ProductDelivery(
        product_id=delivery_in.product_id,
        quantity_received=delivery_in.quantity_received,
        delivery_date=delivery_in.delivery_date,
        supplier=delivery_in.supplier
    )
    db.add(db_delivery)

    # Asosiy Product jadvalidagi miqdorni va oxirgi yetkazib berish sanasini yangilash
    product_obj.quantity_grams += delivery_in.quantity_received
    product_obj.delivery_date = delivery_in.delivery_date # Oxirgi kelgan sana

    db.commit()
    db.refresh(db_delivery)
    db.refresh(product_obj) # Product obyektini ham yangilash
    return db_delivery

def get_product_deliveries(db: Session, product_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[database.ProductDelivery]:
    query = db.query(database.ProductDelivery).order_by(database.ProductDelivery.delivery_date.desc())
    if product_id:
        query = query.filter(database.ProductDelivery.product_id == product_id)
    return query.offset(skip).limit(limit).all()


# --- Meal CRUD (update_meal o'zgartirilgan) ---
def get_meal(db: Session, meal_id: int) -> Optional[database.Meal]:
    # relationship() ni to'g'ri import qilinganini tekshiring (fayl boshida)
    # options() da selectinload() ni to'g'ri ishlatish:
    # .options(selectinload(database.Meal.ingredients).selectinload(database.MealIngredient.product))
    # Lekin MealIngredient.product allaqachon MealIngredient schemasida eager load qilinishi mumkin.
    # Asosiy muammo relationship importi edi. selectinload ni ham to'g'rilaymiz.
    from sqlalchemy.orm import selectinload # selectinload ni ham shu yerda import qilish mumkin yoki fayl boshida

    return db.query(database.Meal).options(
        selectinload(database.Meal.ingredients).selectinload(database.MealIngredient.product)
    ).filter(database.Meal.id == meal_id).first()

def get_meal_by_name(db: Session, name: str) -> Optional[database.Meal]:
    return db.query(database.Meal).filter(database.Meal.name == name).first()

def get_meals(db: Session, skip: int = 0, limit: int = 100) -> List[database.Meal]:
    return db.query(database.Meal).order_by(database.Meal.name).offset(skip).limit(limit).all()

def create_meal(db: Session, meal: schemas.MealCreate) -> database.Meal:
    db_meal = database.Meal(name=meal.name)
    db.add(db_meal)
    db.commit()
    db.refresh(db_meal)
    for ingredient_data in meal.ingredients:
        product = get_product(db, ingredient_data.product_id)
        if not product:
            db.rollback() # Xatolik bo'lsa, o'zgarishlarni qaytarish
            raise ValueError(f"Product with ID {ingredient_data.product_id} not found for meal '{meal.name}'.")
        db_ingredient = database.MealIngredient(
            meal_id=db_meal.id,
            product_id=ingredient_data.product_id,
            required_grams=ingredient_data.required_grams
        )
        db.add(db_ingredient)
    db.commit() # Ingredientlar qo'shilgandan keyin yana commit
    db.refresh(db_meal) # Ingredientlar bilan to'liq yuklash uchun
    return db_meal

def update_meal(db: Session, meal_id: int, meal_update: schemas.MealUpdate) -> Optional[database.Meal]:
    db_meal = get_meal(db, meal_id) # Bu get_meal endi ingredientlarni yuklaydi
    if not db_meal:
        return None

    if meal_update.name is not None:
        db_meal.name = meal_update.name

    if meal_update.ingredients is not None: # Bu List[schemas.MealIngredientCreate]
        # Eski ingredientlarni o'chirish
        db.query(database.MealIngredient).filter(database.MealIngredient.meal_id == meal_id).delete(synchronize_session=False)
        
        # Yangi ingredientlarni qo'shish
        for ingredient_schema in meal_update.ingredients:
            product = get_product(db, ingredient_schema.product_id)
            if not product:
                db.rollback()
                raise ValueError(f"Product with ID {ingredient_schema.product_id} not found for meal '{db_meal.name}'.")
            
            db_ingredient = database.MealIngredient(
                meal_id=db_meal.id,
                product_id=ingredient_schema.product_id,
                required_grams=ingredient_schema.required_grams
            )
            db.add(db_ingredient)
            
    db.commit()
    db.refresh(db_meal)
    return db_meal

def delete_meal(db: Session, meal_id: int) -> Optional[database.Meal]:
    db_meal = get_meal(db, meal_id)
    if db_meal:
        # MealIngredient lar cascade orqali o'chishi kerak (modelda to'g'ri sozlanganda)
        db.delete(db_meal)
        db.commit()
    return db_meal

# --- Meal Serving Log CRUD (create o'zgartirilgan) ---
def create_meal_serving_log(db: Session, meal_id: int, user_id: int, portions_served: int) -> database.MealServingLog:
    db_log = database.MealServingLog(
        meal_id=meal_id,
        served_by_user_id=user_id,
        portions_served=portions_served, # Berilgan porsiyalar soni
        serving_time=datetime.datetime.utcnow()
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log

def get_meal_serving_logs(db: Session, skip: int = 0, limit: int = 100,
                          user_id: Optional[int] = None, meal_id: Optional[int] = None,
                          start_date: Optional[datetime.datetime] = None,
                          end_date: Optional[datetime.datetime] = None) -> List[database.MealServingLog]:
    query = db.query(database.MealServingLog).order_by(database.MealServingLog.serving_time.desc())
    if user_id:
        query = query.filter(database.MealServingLog.served_by_user_id == user_id)
    if meal_id:
        query = query.filter(database.MealServingLog.meal_id == meal_id)
    if start_date:
        query = query.filter(database.MealServingLog.serving_time >= start_date)
    if end_date:
        if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
            end_date = end_date.replace(hour=23, minute=59, second=59)
        query = query.filter(database.MealServingLog.serving_time <= end_date)
    return query.offset(skip).limit(limit).all()

def get_total_prepared_portions_for_month(db: Session, year: int, month: int, meal_id: Optional[int] = None) -> int:
    """O'sha oyda berilgan JAMI porsiyalar sonini hisoblaydi."""
    query = db.query(func.sum(database.MealServingLog.portions_served)).filter(
        extract('year', database.MealServingLog.serving_time) == year,
        extract('month', database.MealServingLog.serving_time) == month
    )
    if meal_id:
        query = query.filter(database.MealServingLog.meal_id == meal_id)
    
    total_portions = query.scalar()
    return total_portions if total_portions is not None else 0

def get_ingredient_consumption_for_period(db: Session, product_id: int, start_date: datetime.datetime, end_date: datetime.datetime) -> float:
    total_consumed = 0.0
    # Har bir berilgan ovqat uchun logni va uning retseptini olamiz
    logs_with_recipes = db.query(database.MealServingLog, database.MealIngredient).\
        join(database.Meal, database.MealServingLog.meal_id == database.Meal.id).\
        join(database.MealIngredient, database.Meal.id == database.MealIngredient.meal_id).\
        filter(database.MealIngredient.product_id == product_id).\
        filter(database.MealServingLog.serving_time >= start_date).\
        filter(database.MealServingLog.serving_time <= end_date).\
        all()
    
    for serving_log, ingredient_recipe in logs_with_recipes:
        # Har bir berishda qancha porsiya berilganini hisobga olamiz
        total_consumed += (ingredient_recipe.required_grams * serving_log.portions_served)
        
    return total_consumed
