from sqlalchemy.orm import Session,selectinload
from sqlalchemy import func, extract
import database, schemas, security
import datetime
from typing import List, Optional
from sqlalchemy import select

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

def get_product_deliveries(
    db: Session, 
    product_id: Optional[int] = None, 
    start_date: Optional[datetime.datetime] = None,
    end_date: Optional[datetime.datetime] = None,
    skip: int = 0, 
    limit: int = 100
) -> List[database.ProductDelivery]: # Bu database.ProductDelivery qaytaradi
    
    query = db.query(database.ProductDelivery).options(
        selectinload(database.ProductDelivery.product) # Bu Product obyektini yuklaydi
    )

    if product_id is not None:
        query = query.filter(database.ProductDelivery.product_id == product_id)
    if start_date:
        query = query.filter(database.ProductDelivery.delivery_date >= start_date)
    if end_date:
        if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query = query.filter(database.ProductDelivery.delivery_date <= end_date)
    
    return query.order_by(database.ProductDelivery.delivery_date.desc()).offset(skip).limit(limit).all()


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
def create_audit_log(db: Session, log_entry: schemas.AuditLogCreate) -> database.AuditLog:
    try:
        db_log = database.AuditLog(
            username=log_entry.username,
            method=log_entry.method,
            endpoint_path=log_entry.endpoint_path,
            client_host=log_entry.client_host,
            user_agent=log_entry.user_agent,
            details=log_entry.details,
            timestamp=datetime.datetime.utcnow() 
        )
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log
    except Exception as e:
        print(f"CRUD_AUDIT_LOG: Error creating ultra-simplified audit log: {e}")
        db.rollback()
        raise

def get_audit_logs(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    user_id: Optional[int] = None,
    username_contains: Optional[str] = None,
    method: Optional[str] = None,
    endpoint_path_contains: Optional[str] = None,
    status_code: Optional[int] = None,
    start_date: Optional[datetime.datetime] = None,
    end_date: Optional[datetime.datetime] = None
) -> List[database.AuditLog]:
    query = db.query(database.AuditLog)

    if user_id is not None:
        query = query.filter(database.AuditLog.user_id == user_id)
    if username_contains:
        query = query.filter(database.AuditLog.username.ilike(f"%{username_contains}%"))
    if method:
        query = query.filter(database.AuditLog.method == method.upper())
    if endpoint_path_contains:
        query = query.filter(database.AuditLog.endpoint_path.ilike(f"%{endpoint_path_contains}%"))
    if status_code is not None:
        query = query.filter(database.AuditLog.status_code == status_code)
    if start_date:
        query = query.filter(database.AuditLog.timestamp >= start_date)
    if end_date:
        # Agar end_date faqat sana bo'lsa, kun oxirigacha olish uchun
        if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query = query.filter(database.AuditLog.timestamp <= end_date)
    
    return query.order_by(database.AuditLog.timestamp.desc()).offset(skip).limit(limit).all()

def get_user_preview_for_log(db: Session, user_id: int) -> Optional[str]:
    # stmt = select(database.User.username).where(database.User.id == user_id) # Eski usul (1.x)
    stmt = select(database.User.username).filter_by(id=user_id) # Yangi usul (2.0)
    username = db.execute(stmt).scalar_one_or_none()
    return f"Foydalanuvchi '{username}' (ID: {user_id})" if username else f"Foydalanuvchi (ID: {user_id})"

def get_product_preview_for_log(db: Session, product_id: int) -> Optional[str]:
    # stmt = select(database.Product.name).where(database.Product.id == product_id) # Eski usul
    stmt = select(database.Product.name).filter_by(id=product_id) # Yangi usul
    product_name = db.execute(stmt).scalar_one_or_none()
    return f"Mahsulot '{product_name}' (ID: {product_id})" if product_name else f"Mahsulot (ID: {product_id})"

def get_meal_preview_for_log(db: Session, meal_id: int) -> Optional[str]:
    # stmt = select(database.Meal.name).where(database.Meal.id == meal_id) # Eski usul
    stmt = select(database.Meal.name).filter_by(id=meal_id) # Yangi usul
    meal_name = db.execute(stmt).scalar_one_or_none()
    return f"Taom '{meal_name}' (ID: {meal_id})" if meal_name else f"Taom (ID: {meal_id})"
def get_user_name_for_log(db: Session, user_id: int) -> Optional[str]:
    """Berilgan user_id bo'yicha foydalanuvchi nomini qaytaradi."""
    stmt = select(database.User.username).filter_by(id=user_id)
    return db.execute(stmt).scalar_one_or_none()

def get_product_name_for_log(db: Session, product_id: int) -> Optional[str]:
    """Berilgan product_id bo'yicha mahsulot nomini qaytaradi."""
    stmt = select(database.Product.name).filter_by(id=product_id)
    return db.execute(stmt).scalar_one_or_none()

def get_meal_name_for_log(db: Session, meal_id: int) -> Optional[str]:
    """Berilgan meal_id bo'yicha taom nomini qaytaradi."""
    stmt = select(database.Meal.name).filter_by(id=meal_id)
    return db.execute(stmt).scalar_one_or_none()

def delete_old_audit_logs(db: Session, days_to_keep: int = 30) -> int:
    """
    Belgilangan 'days_to_keep' dan eski bo'lgan audit loglarini o'chiradi.
    O'chirilgan yozuvlar sonini qaytaradi.
    """
    if days_to_keep <= 0:
        return 0
    

    cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days_to_keep)
    
    try:
        num_deleted_rows = db.query(database.AuditLog).filter(database.AuditLog.timestamp < cutoff_date).delete(synchronize_session=False)
        db.commit()
        return num_deleted_rows
    except Exception as e:
        db.rollback()
        return 0