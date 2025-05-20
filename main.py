from fastapi import FastAPI, Depends, HTTPException, status, Body, Query, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Annotated, Optional
import datetime

# Modullarni to'g'ri import qilish (papkangiz strukturasiga qarab o'zgartiring)
# Agar app papkasi PYTHONPATH da bo'lsa:
# from app import crud, schemas, security, utils, database
# from app.database import engine, get_db, create_db_and_tables, UserRole
# Agar barcha fayllar bitta app papkasida bo'lsa:
import crud, schemas, security, utils, database
from database import engine, get_db, create_db_and_tables, UserRole


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Bog'cha Ovqatlar va Ombor Hisoboti Dasturi Rev.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Ishlab chiqish uchun. Productionda aniq domenlarni ko'rsating.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Startup event ---
@app.on_event("startup")
def on_startup_event(): # Nomini o'zgartirdim, on_startup FastAPI ning o'zida bo'lishi mumkin
    print("MAIN.PY: Startup event boshlandi...")
    create_db_and_tables()
    db = next(get_db())
    try:
        # Admin
        if not crud.get_user_by_username(db, username="admin"):
            crud.create_user(db, schemas.UserCreate(username="admin", password="adminpassword", role=UserRole.admin))
            print("Admin user created.")
        # Chef
        if not crud.get_user_by_username(db, username="chef"):
            crud.create_user(db, schemas.UserCreate(username="chef", password="chefpassword", role=UserRole.chef))
            print("Chef user created.")
        # Manager
        if not crud.get_user_by_username(db, username="manager"):
            crud.create_user(db, schemas.UserCreate(username="manager", password="managerpassword", role=UserRole.manager))
            print("Manager user created.")
    finally:
        db.close()
    print("MAIN.PY: Startup event tugadi.")

class CommonQueryParams:
    def __init__(self, skip: int = 0, limit: int = 100):
        self.skip = skip
        self.limit = limit

# --- Routers ---
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["User Management"])
products_router = APIRouter(prefix="/products", tags=["Product Management"])
meals_router = APIRouter(prefix="/meals", tags=["Meal Management"])
serving_router = APIRouter(prefix="/serve", tags=["Meal Serving System"]) # Prefixni o'zgartirdim
portions_router = APIRouter(prefix="/portions", tags=["Portion Calculation"])
reports_router = APIRouter(prefix="/reports", tags=["Reports & Visualization"])
alerts_router = APIRouter(prefix="/alerts", tags=["Alerts"])


# --- Authentication Endpoints ---
@auth_router.post("/token", response_model=schemas.Token)
async def login_for_access_token_route( # Nomini o'zgartirdim
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_username(db, username=form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    
    access_token_expires = datetime.timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.username, "role": user.role.value}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- User Management Endpoints ---
@users_router.post("/", response_model=schemas.UserSchema, status_code=status.HTTP_201_CREATED)
def create_user_route( # Nomini o'zgartirdim
    user: schemas.UserCreate, 
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_admin_user)
):
    return crud.create_user(db=db, user=user) # crud.create_user xatolikni o'zi handle qiladi (agar username mavjud bo'lsa)

@users_router.get("/", response_model=List[schemas.UserSchema])
def read_users_route(
    commons: Annotated[CommonQueryParams, Depends()],
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_admin_user)
):
    return crud.get_users(db, skip=commons.skip, limit=commons.limit)

@users_router.get("/me", response_model=schemas.UserSchema)
async def read_users_me_route(
    current_user: Annotated[database.User, Depends(security.get_current_active_user)]
):
    return current_user

@users_router.get("/{user_id}", response_model=schemas.UserSchema)
def read_user_route(
    user_id: int, 
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_admin_user)
):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user

@users_router.put("/{user_id}", response_model=schemas.UserSchema)
def update_user_route(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_admin_user)
):
    # crud.update_user ichida xatolik va topilmagan holatlar handle qilinadi
    updated_user = crud.update_user(db, user_id=user_id, user_update=user_update)
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or update failed")
    return updated_user


@users_router.delete("/{user_id}", response_model=schemas.UserSchema)
def delete_user_route(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_admin_user)
):
    if current_user.id == user_id:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin users cannot delete themselves.")
    deleted_user = crud.delete_user(db, user_id=user_id)
    if deleted_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return deleted_user

# --- Product Management Endpoints ---
@products_router.post("/type", response_model=schemas.Product, status_code=status.HTTP_201_CREATED)
def create_new_product_type_route( # Yangi mahsulot TURINI yaratish
    product_in: schemas.ProductCreate,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    try:
        return crud.create_product_type(db=db, product_in=product_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@products_router.post("/{product_id}/receive_stock", response_model=schemas.ProductDelivery, status_code=status.HTTP_201_CREATED)
def receive_product_stock_route( # Mavjud mahsulotga miqdor qo'shish
    product_id: int,
    delivery_in: schemas.ProductDeliveryCreate, # product_id bu yerda bo'lmasligi kerak, chunki URL da bor
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    # delivery_in.product_id ni URL dagi product_id bilan almashtirish yoki tekshirish
    if delivery_in.product_id != product_id:
        # Agar validatsiya uchun ProductDeliveryCreate da product_id qoldirilsa, uni tekshirish kerak.
        # Yoki ProductDeliveryCreate schemasidan product_id ni olib tashlab, uni faqat URL dan olish.
        # Keling, ProductDeliveryCreate da product_id qolsin va uni tekshiraylik.
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product ID in path and body do not match.")

    try:
        # product_id URL dan olingani uchun delivery_in dan emas, to'g'ridan-to'g'ri beramiz
        # crud.create_product_delivery ga product_id ni alohida berishimiz mumkin
        # yoki delivery_in ni o'zgartirishimiz kerak.
        # Yaxshisi, crud.create_product_delivery ichida delivery_in.product_id ni ishlatsin.
        return crud.create_product_delivery(db=db, delivery_in=delivery_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@products_router.get("/", response_model=List[schemas.Product])
def read_products_route(
    commons: Annotated[CommonQueryParams, Depends()],
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_authenticated_user)
):
    return crud.get_products(db, skip=commons.skip, limit=commons.limit)

@products_router.get("/{product_id}", response_model=schemas.Product)
def read_product_route(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_authenticated_user)
):
    db_product = crud.get_product(db, product_id=product_id)
    if db_product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return db_product

@products_router.put("/{product_id}/update_info", response_model=schemas.Product) # Faqat nomini o'zgartirish uchun
def update_product_info_route(
    product_id: int,
    product_update: schemas.ProductUpdate, # Bu schema faqat 'name' ni o'z ichiga olishi kerak
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    try:
        updated_product = crud.update_product_name(db, product_id=product_id, product_update=product_update)
        if updated_product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return updated_product
    except ValueError as e: # Agar yangi nom band bo'lsa
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@products_router.delete("/{product_id}", response_model=schemas.Product)
def delete_product_route(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    try:
        deleted_product = crud.delete_product(db, product_id=product_id)
        if deleted_product is None: # Agar crud.delete_product xatoliksiz None qaytarsa (bu holat bo'lmasligi kerak)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
        return deleted_product
    except ValueError as e: # Mahsulot retseptda ishlatilayotgan bo'lsa
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@products_router.get("/{product_id}/deliveries", response_model=List[schemas.ProductDelivery])
def read_product_deliveries_route(
    product_id: int,
    commons: Annotated[CommonQueryParams, Depends()],
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    # Mahsulot mavjudligini tekshirish
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {product_id} not found.")
    return crud.get_product_deliveries(db, product_id=product_id, skip=commons.skip, limit=commons.limit)


# --- Meal Management Endpoints ---
@meals_router.post("/", response_model=schemas.Meal, status_code=status.HTTP_201_CREATED)
def create_meal_route(
    meal: schemas.MealCreate,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    try:
        return crud.create_meal(db=db, meal=meal)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@meals_router.get("/", response_model=List[schemas.Meal])
def read_meals_route(
    commons: Annotated[CommonQueryParams, Depends()],
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_authenticated_user)
):
    return crud.get_meals(db, skip=commons.skip, limit=commons.limit)

@meals_router.get("/{meal_id}", response_model=schemas.Meal)
def read_meal_route(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_authenticated_user)
):
    db_meal = crud.get_meal(db, meal_id=meal_id)
    if db_meal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found")
    return db_meal

@meals_router.put("/{meal_id}", response_model=schemas.Meal)
def update_meal_route(
    meal_id: int,
    meal_update: schemas.MealUpdate, # schemas.py da MealUpdate name va ingredients ni Optional qilib oladi
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    try:
        updated_meal = crud.update_meal(db, meal_id=meal_id, meal_update=meal_update)
        if updated_meal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found")
        return updated_meal
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@meals_router.delete("/{meal_id}", response_model=schemas.Meal)
def delete_meal_route(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    deleted_meal = crud.delete_meal(db, meal_id=meal_id)
    if deleted_meal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found")
    return deleted_meal

# --- Meal Serving System ---
@serving_router.post("/{meal_id}", response_model=schemas.MealServingLogSchema) # Path o'zgardi, /serve endi prefix
def serve_meal_route(
    meal_id: int,
    serve_request: schemas.ServeMealRequest, # So'rov tanasidan porsiya sonini olish
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_chef_user)
):
    success, message, log_entry = utils.serve_meal_action(
        db, 
        meal_id=meal_id, 
        user_id=current_user.id, 
        portions_to_serve=serve_request.portions_to_serve # Porsiya sonini uzatish
    )
    if not success or not log_entry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return log_entry

# --- Portion Calculation ---
@portions_router.get("/{meal_id}/calculate", response_model=schemas.PortionCalculationResponse)
def calculate_portions_for_meal_route(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_authenticated_user)
):
    meal = crud.get_meal(db, meal_id)
    if not meal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Meal with ID {meal_id} not found.")
    portions = utils.calculate_portions_for_meal(db, meal_id=meal_id)
    return schemas.PortionCalculationResponse(meal_id=meal.id, meal_name=meal.name, calculable_portions=portions)

@portions_router.get("/all/all/calculate", response_model=List[schemas.PortionCalculationResponse]) # /all/all -> /all
def calculate_portions_for_all_meals_route(
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_authenticated_user)
):
    return utils.calculate_portions_for_all_meals(db)

# --- Reports and Visualization Data Endpoints ---
@reports_router.get("/ingredient_consumption", response_model=List[schemas.DailyConsumptionDataPoint]) # Javob modelini aniqlashtirdim
def ingredient_consumption_report_route(
    product_id: int,
    start_date: datetime.date = Query(...),
    end_date: datetime.date = Query(...),
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    # ... (mavjud kod) ...
    consumption_data_list = utils.get_ingredient_consumption_data(db, product_id, start_date, end_date)
    # Bu yerda utils.get_ingredient_consumption_data List[Dict] qaytaradi.
    # Agar schemas.IngredientConsumption qaytarish kerak bo'lsa, konvertatsiya qilish kerak.
    # Hozircha List[Dict] qoldiramiz, chunki schemas.IngredientConsumption bitta mahsulot uchun,
    # lekin utils.get_ingredient_consumption_data kunlik sarfni qaytaradi.
    # Yaxshisi, schemas.IngredientConsumption ni o'zgartirish yoki javobni List[dict] qoldirish.
    # Hozircha, utils.get_ingredient_consumption_data ni List[schemas.IngredientConsumptionDataPoint] kabi qaytaradigan qilish kerak.
    # Yoki schemas.IngredientConsumption ni List[ConsumptionDataPoint] ni o'z ichiga oladigan qilish kerak.
    # Keling, schemas.IngredientConsumption ni List[dict] ga moslaymiz yoki javobni List[dict] qoldiramiz.
    # schemas.py da IngredientConsumption ni o'zgartirdim:
    # class IngredientConsumptionDataPoint(BaseModel):
    #     date: str
    #     consumed_grams: float
    # class IngredientConsumptionReport(BaseModel):
    #     product_name: str
    #     consumption_series: List[IngredientConsumptionDataPoint]
    # Lekin hozirgi utils.get_ingredient_consumption_data to'g'ridan-to'g'ri List[Dict] qaytaradi, Chart.js uchun qulay.
    # Response modelini List[Dict] ga o'zgartiramiz.
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {product_id} not found.")

    return utils.get_ingredient_consumption_data(db, product_id, start_date, end_date)


@reports_router.get("/product_delivery_history/{product_id}", response_model=List[schemas.ProductDelivery]) # product_id ni path ga o'tkazdim
def product_delivery_history_route(
    product_id: int,
    commons: Annotated[CommonQueryParams, Depends()], # Pagination qo'shish mumkin
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {product_id} not found.")
    return crud.get_product_deliveries(db, product_id=product_id, skip=commons.skip, limit=commons.limit)


@reports_router.get("/monthly_summary", response_model=schemas.MonthlyReportSchema)
def monthly_summary_report_route(
    year: int = Query(..., ge=2020),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    return utils.generate_monthly_report_data(db, year, month)

@reports_router.get("/meal_serving_logs", response_model=List[schemas.MealServingLogSchema])
def get_all_meal_serving_logs_route(
    commons: Annotated[CommonQueryParams, Depends()],
    user_id: Optional[int] = Query(None),
    meal_id: Optional[int] = Query(None),
    start_date_str: Optional[str] = Query(None, alias="startDate"), # Frontend dan keladigan nomga moslash
    end_date_str: Optional[str] = Query(None, alias="endDate"),
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    start_date = None
    if start_date_str:
        try: start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError: raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")
    end_date = None
    if end_date_str:
        try: end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
        except ValueError: raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")
    if start_date and end_date and start_date > end_date:
         raise HTTPException(status_code=400, detail="Start date cannot be after end date.")
    return crud.get_meal_serving_logs(db, skip=commons.skip, limit=commons.limit, user_id=user_id, meal_id=meal_id, start_date=start_date, end_date=end_date)

# --- Alerts Endpoints ---
@alerts_router.get("/low_stock", response_model=List[schemas.LowStockAlert])
def low_stock_alerts_route(
    minimum_threshold: Optional[int] = Query(utils.MINIMUM_STOCK_THRESHOLD_DEFAULT_GRAMS, ge=0),
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    return utils.check_low_stock_alerts(db, minimum_threshold_grams=minimum_threshold)
@alerts_router.get("/potential_abuse", 
                   response_model=Optional[schemas.PotentialAbuseAlert],
                   # Swagger uchun namunaviy javoblarni yaxshilash mumkin:
                   responses={
                       200: {
                           "description": "Potential abuse alert data or null if no abuse detected.",
                           "content": {
                               "application/json": {
                                   "examples": {
                                       "alert_found": {
                                           "summary": "Abuse Detected",
                                           "value": { # schemas.PotentialAbuseAlert namunasi
                                                "month": "2023-05",
                                                "prepared_portions": 1000,
                                                "potential_portions_at_month_end": 500,
                                                "difference_percentage": 33.33,
                                                "message": "Potential resource misuse..."
                                           }
                                       },
                                       "no_alert": {
                                           "summary": "No Abuse Detected",
                                           "value": None # Yoki {} agar frontend shuni kutsa, lekin None yaxshiroq
                                       }
                                   }
                               }
                           }
                       }
                   })
def potential_abuse_alert_route(
    year: int = Query(..., description="Tekshirish uchun yil", ge=2020),
    month: int = Query(..., description="Tekshirish uchun oy", ge=1, le=12),
    threshold: float = Query(15.0, description="Suiiste'molni aniqlash uchun chegara foizi", ge=0, le=100),
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    alert_data = utils.get_potential_abuse_alert(db, year, month, threshold_percentage=threshold)
    
    if not alert_data:
        # Agar utils.get_potential_abuse_alert None qaytarsa, endpoint ham None qaytaradi.
        # FastAPI buni to'g'ri JSON null ga aylantiradi (yoki HTTP 204 No Content, agar hech nima qaytarmasangiz).
        # Aniqroq bo'lishi uchun JSONResponse(content=None) dan foydalanish mumkin.
        return None # Yoki return JSONResponse(content=None, status_code=200)
        # Yoki hech nima qaytarmaslik, FastAPI o'zi hal qiladi:
        # return 
        # Lekin None qaytarish Optional response modeliga eng mos keladi.

    return alert_data
# --- Routers ni asosiy app ga qo'shish ---
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(products_router)
app.include_router(meals_router)
app.include_router(serving_router)
app.include_router(portions_router)
app.include_router(reports_router)
app.include_router(alerts_router)

if __name__ == "__main__":
    import uvicorn
    print("MAIN.PY: Uvicorn ishga tushirilmoqda http://127.0.0.1:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) # `app.main:app` o'rniga `main:app` agar shu faylni ishga tushirsangiz