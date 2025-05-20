from sqlalchemy.orm import Session
import database, crud, schemas # Yoki app.database va h.k.
from typing import List, Dict, Tuple, Optional
import datetime

MINIMUM_STOCK_THRESHOLD_DEFAULT_GRAMS = 500

def calculate_portions_for_meal(db: Session, meal_id: int) -> int:
    meal = crud.get_meal(db, meal_id)
    if not meal or not meal.ingredients:
        return 0
    min_portions = float('inf')
    for ingredient_recipe in meal.ingredients:
        product = crud.get_product(db, ingredient_recipe.product_id)
        if not product or product.quantity_grams <= 0 or ingredient_recipe.required_grams <= 0:
            return 0
        portions_for_this_ingredient = product.quantity_grams // ingredient_recipe.required_grams
        min_portions = min(min_portions, portions_for_this_ingredient)
    return int(min_portions) if min_portions != float('inf') else 0

def calculate_portions_for_all_meals(db: Session) -> List[schemas.PortionCalculationResponse]:
    all_meals = crud.get_meals(db, limit=1000)
    response = []
    for meal in all_meals:
        portions = calculate_portions_for_meal(db, meal.id)
        response.append(schemas.PortionCalculationResponse(
            meal_id=meal.id,
            meal_name=meal.name,
            calculable_portions=portions
        ))
    return response

def serve_meal_action(db: Session, meal_id: int, user_id: int, portions_to_serve: int) -> Tuple[bool, str, Optional[database.MealServingLog]]:
    """Ovqat berish: ko'p porsiya uchun ingredientlarni ayrish va log yozish."""
    if portions_to_serve <= 0:
        return False, "Portions to serve must be greater than zero.", None

    meal = crud.get_meal(db, meal_id)
    if not meal:
        return False, f"Meal with ID {meal_id} not found.", None
    if not meal.ingredients:
        return False, f"Meal '{meal.name}' has no ingredients defined.", None

    # Kerakli ingredientlar miqdorini hisoblash va zaxirani tekshirish
    required_ingredients_total = {}
    for ing_recipe in meal.ingredients:
        total_needed_for_ingredient = ing_recipe.required_grams * portions_to_serve
        product = crud.get_product(db, ing_recipe.product_id)
        if not product:
            return False, f"Product '{ing_recipe.product.name if ing_recipe.product else 'ID: '+str(ing_recipe.product_id)}' for meal '{meal.name}' not found in stock.", None
        if product.quantity_grams < total_needed_for_ingredient:
            return False, f"Not enough '{product.name}' for {portions_to_serve} portions of '{meal.name}'. Required: {total_needed_for_ingredient}g, Available: {product.quantity_grams}g.", None
        required_ingredients_total[product.id] = total_needed_for_ingredient

    # Agar hamma narsa yetarli bo'lsa, ingredientlarni ayrish
    for product_id, amount_to_deduct in required_ingredients_total.items():
        product_to_update = crud.get_product(db, product_id) # Qayta olish
        if product_to_update: # Xavfsizlik uchun yana tekshirish
            product_to_update.quantity_grams -= amount_to_deduct
            if product_to_update.quantity_grams < 0: # Bu holat yuz bermasligi kerak
                db.rollback()
                return False, f"Critical error: Product '{product_to_update.name}' stock went negative. Transaction rolled back.", None
            db.add(product_to_update)

    # Ovqat berish logini yozish
    try:
        log_entry = crud.create_meal_serving_log(db, meal_id=meal.id, user_id=user_id, portions_served=portions_to_serve)
        db.commit() # CRUD ichida commit bor, lekin bu yerda ham bo'lishi mumkin agar crud da bo'lmasa
        db.refresh(log_entry)
        # Mahsulotlarni ham refresh qilish
        for product_id in required_ingredients_total.keys():
             product_refreshed = crud.get_product(db, product_id)
             if product_refreshed: db.refresh(product_refreshed)

    except Exception as e:
        db.rollback()
        return False, f"Error during serving meal and logging: {str(e)}", None
        
    return True, f"{portions_to_serve} portions of meal '{meal.name}' served successfully. Ingredients deducted.", log_entry


def check_low_stock_alerts(db: Session, minimum_threshold_grams: int = MINIMUM_STOCK_THRESHOLD_DEFAULT_GRAMS) -> List[schemas.LowStockAlert]:
    low_stock_products = db.query(database.Product).filter(database.Product.quantity_grams < minimum_threshold_grams).all()
    alerts = []
    for product in low_stock_products:
        alerts.append(schemas.LowStockAlert(
            product_id=product.id,
            product_name=product.name,
            current_quantity_grams=product.quantity_grams,
            message=f"'{product.name}' miqdori kam ({product.quantity_grams}g). Minimum: {minimum_threshold_grams}g."
        ))
    return alerts

def generate_monthly_report_data(db: Session, year: int, month: int) -> schemas.MonthlyReportSchema:
    total_prepared_portions = crud.get_total_prepared_portions_for_month(db, year, month)
    
    current_potential_portions_list = calculate_portions_for_all_meals(db)
    total_potential_portions_at_month_end = sum(item.calculable_portions for item in current_potential_portions_list)

    difference_percentage = 0.0
    theoretical_total_available = total_prepared_portions + total_potential_portions_at_month_end
    if theoretical_total_available > 0:
        difference_percentage = (total_potential_portions_at_month_end / theoretical_total_available) * 100
    
    potential_abuse_signal = difference_percentage > 15.0

    return schemas.MonthlyReportSchema(
        month=f"{year}-{str(month).zfill(2)}",
        total_prepared_portions=total_prepared_portions,
        average_potential_portions=total_potential_portions_at_month_end,
        difference_percentage=round(difference_percentage, 2),
        potential_abuse_signal=potential_abuse_signal
    )

def get_potential_abuse_alert(db: Session, year: int, month: int, threshold_percentage: float = 15.0) -> Optional[schemas.PotentialAbuseAlert]:
    report_data = generate_monthly_report_data(db, year, month)
    if report_data.potential_abuse_signal and report_data.difference_percentage > threshold_percentage:
        return schemas.PotentialAbuseAlert(
            month=report_data.month,
            prepared_portions=report_data.total_prepared_portions,
            potential_portions_at_month_end=report_data.average_potential_portions,
            difference_percentage=report_data.difference_percentage,
            message=(f"Potential resource misuse in {report_data.month}. "
                     f"Unused potential: {report_data.difference_percentage:.2f}% (Threshold: {threshold_percentage}%)")
        )
    return None

def get_ingredient_consumption_data(db: Session, product_id: int, start_date: datetime.date, end_date: datetime.date) -> List[Dict[str, any]]:
    consumption_data = []
    current_date = start_date
    _end_datetime = datetime.datetime.combine(end_date, datetime.datetime.max.time())

    while current_date <= end_date:
        day_start = datetime.datetime.combine(current_date, datetime.datetime.min.time())
        day_end = datetime.datetime.combine(current_date, datetime.datetime.max.time())
        
        # Bu yerda get_ingredient_consumption_for_period ni kunlik chaqirish mumkin
        # Yoki to'g'ridan-to'g'ri shu yerda hisoblash.
        # Hozirgi crud.get_ingredient_consumption_for_period davr uchun jami qaytaradi.
        # Uni kunlikka moslashtirish kerak yoki shu yerda logikani yozish kerak.
        # Keling, soddalashtirilgan logikani shu yerda yozamiz:
        
        logs_for_day_with_recipes = db.query(database.MealServingLog, database.MealIngredient).\
            join(database.Meal, database.MealServingLog.meal_id == database.Meal.id).\
            join(database.MealIngredient, database.Meal.id == database.MealIngredient.meal_id).\
            filter(database.MealIngredient.product_id == product_id).\
            filter(database.MealServingLog.serving_time >= day_start).\
            filter(database.MealServingLog.serving_time <= day_end).\
            all()

        daily_consumption = 0.0
        for serving_log, ingredient_recipe in logs_for_day_with_recipes:
            daily_consumption += (ingredient_recipe.required_grams * serving_log.portions_served)
        
        consumption_data.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "consumed_grams": daily_consumption
        })
        current_date += datetime.timedelta(days=1)
    return consumption_data

def get_product_delivery_history(db: Session, product_id: int) -> List[schemas.ProductDelivery]:
    """Mahsulotning barcha yetkazib berish tarixini qaytaradi."""
    deliveries = crud.get_product_deliveries(db, product_id=product_id, limit=1000) # Barcha yozuvlar
    return deliveries # Bu schemas.ProductDelivery listini qaytaradi