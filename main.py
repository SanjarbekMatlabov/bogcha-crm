from fastapi import FastAPI, Depends, HTTPException, status, Body, Query, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Annotated, Optional,Tuple 
import datetime
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
import json
import datetime
import crud, schemas, security, utils, database
from database import engine, get_db, create_db_and_tables, UserRole
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import html
scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
def run_scheduled_log_deletion():
    print(f"SCHEDULER: Eski audit loglarini o'chirish vazifasi ishga tushdi - {datetime.datetime.now(scheduler.timezone)}")
    db: Optional[Session] = None
    try:
        db = next(database.get_db()) 
        deleted_count = crud.delete_old_audit_logs(db, days_to_keep=30) 
    except Exception as e:
        print(f"SCHEDULER: Eski loglarni o'chirishda xatolik yuz berdi: {e}")
    finally:
        if db:
            db.close()
app = FastAPI(title="Bog'cha Ovqatlar va Ombor Hisoboti Dasturi Rev.2")
def mask_sensitive_data(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    
    sensitive_keys = ["password", "token", "access_token", "refresh_token", "secret", "credentials", "new_password", "current_password"]
    
    cleaned_data = {}
    for key, value in data.items():
        if key.lower() in sensitive_keys:
            cleaned_data[key] = "***MASKED***"
        elif isinstance(value, dict):
            cleaned_data[key] = mask_sensitive_data(value)
        elif isinstance(value, list):
            cleaned_data[key] = [mask_sensitive_data(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned_data[key] = value
    return cleaned_data
# def get_resource_info_from_path(path: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
#     parts = path.strip("/").split("/")
#     if not parts: return None, None, None
#     main_entity_key = parts[0].lower()
#     res_type_map = {"users": "Foydalanuvchi", "products": "Mahsulot", "meals": "Taom", "serve": "Taom Berish", "auth": "Autentifikatsiya"}
#     res_type = res_type_map.get(main_entity_key)
#     res_id = None
#     sub_action = None
#     if len(parts) > 1:
#         if parts[1].isdigit():
#             res_id = parts[1]
#             if len(parts) > 2: sub_action = parts[2]
#         else: # Masalan /products/type
#             sub_action = parts[1]
#             if main_entity_key == "products" and sub_action == "type": res_type = "Mahsulot turi"

#     return res_type, res_id, sub_action
def get_resource_type_from_path(path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Endpoint yo'lidan resurs turi, IDsi va potentsial sub-resursini ajratib oladi.
    Qaytaradi: (asosiy_resurs_nomi, resurs_id, sub_resurs_yoki_amal)
    Masalan:
    "/users/123" -> ("Foydalanuvchi", "123", None)
    "/products/type" -> ("Mahsulot turi", None, "type")
    "/products/45/receive_stock" -> ("Mahsulot", "45", "receive_stock")
    """
    parts = path.strip("/").split("/")
    if not parts:
        return None, None, None

    main_entity_key = parts[0].lower()
    resource_type_display: Optional[str] = None
    resource_id_from_path: Optional[str] = None
    sub_action_or_type: Optional[str] = None

    type_map = {
        "users": "Foydalanuvchi",
        "products": "Mahsulot",
        "meals": "Taom",
        "serve": "Taom berish amali", 
        "auth": "Autentifikatsiya",
        "audit-logs": "Audit Log"
       
    }
    resource_type_display = type_map.get(main_entity_key)

    if len(parts) > 1:
        if parts[1].isdigit():
            resource_id_from_path = parts[1]
            if len(parts) > 2:
                sub_action_or_type = parts[2]
        else:
            sub_action_or_type = parts[1]
    
    if main_entity_key == "products" and sub_action_or_type == "type":
        resource_type_display = "Mahsulot turi"

    return resource_type_display, resource_id_from_path, sub_action_or_type

def get_resource_info_from_path(path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    parts = path.strip("/").split("/")
    if not parts or not parts[0]: 
        return None, None, None
    main_entity_key = parts[0].lower()
    res_type_map = {
        "users": "Foydalanuvchi", "products": "Mahsulot", "meals": "Taom", 
        "serve": "Taom Berish", "auth": "Autentifikatsiya"
    }
    res_type_display = res_type_map.get(main_entity_key)
    res_id_from_path: Optional[str] = None
    sub_action_or_type: Optional[str] = None

    if len(parts) > 1:
        if parts[1].isdigit():
            res_id_from_path = parts[1]
            if len(parts) > 2:
                sub_action_or_type = parts[2] 
        else:
            sub_action_or_type = parts[1]
    
    if main_entity_key == "products" and sub_action_or_type == "type":
        res_type_display = "Mahsulot turi"
    elif main_entity_key == "serve" and res_id_from_path: 
        res_type_display = "Taom" 

    return res_type_display, res_id_from_path, sub_action_or_type


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        current_method = request.method.upper()
        current_path = str(request.url.path)

        if current_method in ["GET", "OPTIONS"]:
            return await call_next(request)

        req_body_bytes = await request.body()
        
        username_for_log: Optional[str] = "anonymous"
        if hasattr(request.state, "user") and request.state.user:
            username_for_log = getattr(request.state.user, "username", "state_user_no_username")
        else:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]
                extracted_username = security.decode_username_from_token(token) 
                if extracted_username and extracted_username not in ["expired_token", "invalid_token"]:
                    username_for_log = extracted_username
                elif extracted_username:
                     username_for_log = extracted_username
        
        # --- Resurs haqida ma'lumot olish ---
        fetched_resource_name: Optional[str] = None 
        path_resource_type, path_resource_id, path_sub_action = get_resource_info_from_path(current_path)

        if path_resource_id and path_resource_type:
            db_for_prefetch: Optional[Session] = None
            try:
                db_for_prefetch = next(database.get_db())
                if path_resource_type == "Foydalanuvchi":
                    fetched_resource_name = crud.get_user_name_for_log(db_for_prefetch, int(path_resource_id))
                elif path_resource_type == "Mahsulot":
                    fetched_resource_name = crud.get_product_name_for_log(db_for_prefetch, int(path_resource_id))
                elif path_resource_type == "Taom": 
                    fetched_resource_name = crud.get_meal_name_for_log(db_for_prefetch, int(path_resource_id))
                
                if fetched_resource_name:
                     print(f"AUDIT_MIDDLEWARE: Operatsiyadan oldin resurs nomi olindi: '{fetched_resource_name}'")
                else:
                     print(f"AUDIT_MIDDLEWARE: Resurs (ID: {path_resource_id}, Turi: {path_resource_type}) uchun nom topilmadi.")

            except ValueError:
                 print(f"AUDIT_MIDDLEWARE: Prefetch uchun yaroqsiz resurs IDsi: {path_resource_id}")
            except Exception as e_prefetch:
                print(f"AUDIT_MIDDLEWARE: Log uchun resurs nomini oldindan olishda xatolik: {e_prefetch}")
            finally:
                if db_for_prefetch: db_for_prefetch.close()
        
        created_item_name_from_body: Optional[str] = None
        if current_method == "POST" and req_body_bytes:
            try:
                if "application/json" in request.headers.get("content-type", "").lower():
                    body_json = json.loads(req_body_bytes.decode('utf-8'))
                    created_item_name_from_body = body_json.get("name") or body_json.get("username")
            except Exception: pass

        cloned_request_scope = dict(request.scope)
        async def receive(): return {"type": "http.request", "body": req_body_bytes, "more_body": False}
        request_for_endpoint = Request(cloned_request_scope, receive=receive, send=request._send)

        response: Optional[Response] = None
        status_code_for_log: int = 500 
        exception_details_str: Optional[str] = None
        final_log_details: str = ""
        should_write_log = True

        try:
            response = await call_next(request_for_endpoint)
            status_code_for_log = response.status_code
            if current_path == "/auth/token" and current_method == "POST" and (200 <= status_code_for_log < 300):
                should_write_log = False
        except Exception as e:
            exception_details_str = f"{type(e).__name__}: {str(e)}"
            if hasattr(e, "status_code"): status_code_for_log = e.status_code
        
        if should_write_log:
            user_display = f"Foydalanuvchi '{html.escape(username_for_log)}'" if username_for_log and username_for_log != "anonymous" else "Noma'lum foydalanuvchi"
            
            action_verb = ""
            target_object_display = "" 
            operation_successful = (200 <= status_code_for_log < 300) and not exception_details_str

            method_verb_map_success = {"POST": "qo'shdi", "PUT": "tahrirladi", "PATCH": "qisman tahrirladi", "DELETE": "o'chirdi"}
            method_verb_map_attempt = {"POST": "qo'shishga urindi", "PUT": "tahrirlashga urindi", "PATCH": "qisman tahrirlashga urindi", "DELETE": "o'chirishga urindi"}
            
            action_verb = method_verb_map_success.get(current_method) if operation_successful else method_verb_map_attempt.get(current_method)
            if not action_verb: action_verb = f"{current_method} amalini " + ("bajardi" if operation_successful else "bajarishga urindi")

            if current_method == "POST":
                object_name_to_log = created_item_name_from_body or "noma'lum obyekt"
                res_type_to_log = path_resource_type or "noma'lum turdagi"
                
                if path_resource_type == "Mahsulot" and path_sub_action == "receive_stock":
                    target_object_display = f"'{html.escape(fetched_resource_name or f'ID: {path_resource_id}')}' mahsulotiga yangi kirim"
                elif path_resource_type == "Taom" and current_path.startswith("/serve/"): 
                    target_object_display = f"'{html.escape(fetched_resource_name or f'ID: {path_resource_id}')}' taomini berish"
                    if req_body_bytes:
                        try:
                            body_json = json.loads(req_body_bytes.decode('utf-8'))
                            portions = body_json.get("portions_to_serve")
                            if portions: target_object_display += f" ({portions} porsiya)"
                        except: pass
                elif path_resource_type:
                    target_object_display = f"yangi '{html.escape(object_name_to_log)}' nomli {res_type_to_log.lower()}ni"
                else:
                    target_object_display = f"{html.escape(current_path)} manziliga ma'lumot"
            
            elif current_method in ["PUT", "PATCH", "DELETE"]:
                target_object_display = f"'{html.escape(fetched_resource_name)}'" if fetched_resource_name else \
                                      f"{(path_resource_type.lower() if path_resource_type else 'obyekt')} (ID: {path_resource_id or 'N/A'})"
                if path_resource_type == "Mahsulot" and path_sub_action == "update_info":
                     target_object_display += " nomini" 
            else: 
                target_object_display = f"{html.escape(current_path)} manzilidagi resursni"

            final_log_details = f"{user_display} {target_object_display} {action_verb}."

            if not operation_successful:
                final_log_details += f" Natija: Xatolik."
                if exception_details_str:
                     final_log_details += f" Tafsilot: {html.escape(exception_details_str[:100])}"
            
            db_session_for_log_save: Optional[Session] = None
            try:
                db_session_for_log_save = next(database.get_db())
                log_entry_data = schemas.AuditLogCreate(
                    username=username_for_log,
                    method=request.method,
                    endpoint_path=current_path,
                    client_host=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    details=final_log_details.strip()
                )
                crud.create_audit_log(db=db_session_for_log_save, log_entry=log_entry_data)
            except Exception as log_exc:
                print(f"CRITICAL: Audit logni yozishda xatolik: {log_exc}"); import traceback; traceback.print_exc()
            finally:
                if db_session_for_log_save: db_session_for_log_save.close()
        
        if response is None: 
             return JSONResponse(status_code=status_code_for_log, content={"detail": exception_details_str or "Middleware error"})
        return response
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditLogMiddleware)


# --- Startup event ---
@app.on_event("startup")
def on_startup_event(): 
    create_db_and_tables()
    db = next(get_db())
    try:
        # Admin
        if not crud.get_user_by_username(db, username="admin"):
            crud.create_user(db, schemas.UserCreate(username="admin", password="adminpassword", role=UserRole.admin))
        # Chef
        if not crud.get_user_by_username(db, username="chef"):
            crud.create_user(db, schemas.UserCreate(username="chef", password="chefpassword", role=UserRole.chef))
        # Manager
        if not crud.get_user_by_username(db, username="manager"):
            crud.create_user(db, schemas.UserCreate(username="manager", password="managerpassword", role=UserRole.manager))
    finally:
        db.close()
    try:
        scheduler.add_job(
            run_scheduled_log_deletion, 
            CronTrigger(hour=2, minute=30, timezone="Asia/Tashkent"),
            id="delete_old_logs_job", 
            replace_existing=True 
        )
        if not scheduler.running:
            scheduler.start()
    except Exception as e_scheduler:
        print(f"MAIN.PY (Startup): Scheduler'ni sozlashda xatolik: {e_scheduler}")
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
serving_router = APIRouter(prefix="/serve", tags=["Meal Serving System"]) 
portions_router = APIRouter(prefix="/portions", tags=["Portion Calculation"])
reports_router = APIRouter(prefix="/reports", tags=["Reports & Visualization"])
alerts_router = APIRouter(prefix="/alerts", tags=["Alerts"])


# --- Authentication Endpoints ---
@auth_router.post("/token", response_model=schemas.Token)
async def login_for_access_token_route( 
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
def create_user_route( 
    user: schemas.UserCreate, 
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_admin_user)
):
    return crud.create_user(db=db, user=user) 

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
def create_new_product_type_route( 
    product_in: schemas.ProductCreate,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    try:
        return crud.create_product_type(db=db, product_in=product_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@products_router.post("/{product_id}/receive_stock", response_model=schemas.ProductDelivery, status_code=status.HTTP_201_CREATED)
def receive_product_stock_route( 
    product_id: int,
    delivery_in: schemas.ProductDeliveryCreate, 
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    if delivery_in.product_id != product_id:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product ID in path and body do not match.")
    try:
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

@products_router.put("/{product_id}/update_info", response_model=schemas.Product) 
def update_product_info_route(
    product_id: int,
    product_update: schemas.ProductUpdate, 
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    try:
        updated_product = crud.update_product_name(db, product_id=product_id, product_update=product_update)
        if updated_product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return updated_product
    except ValueError as e: 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@products_router.delete("/{product_id}", response_model=schemas.Product)
def delete_product_route(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    try:
        deleted_product = crud.delete_product(db, product_id=product_id)
        if deleted_product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
        return deleted_product
    except ValueError as e:
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
    meal_update: schemas.MealUpdate, 
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
@serving_router.post("/{meal_id}", response_model=schemas.MealServingLogSchema)
def serve_meal_route(
    meal_id: int,
    serve_request: schemas.ServeMealRequest,
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_chef_user)
):
    success, message, log_entry = utils.serve_meal_action(
        db, 
        meal_id=meal_id, 
        user_id=current_user.id, 
        portions_to_serve=serve_request.portions_to_serve 
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

@portions_router.get("/all/all/calculate", response_model=List[schemas.PortionCalculationResponse])
def calculate_portions_for_all_meals_route(
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_authenticated_user)
):
    return utils.calculate_portions_for_all_meals(db)

# --- Reports and Visualization Data Endpoints ---
@reports_router.get("/ingredient_consumption", response_model=List[schemas.DailyConsumptionDataPoint]) 
def ingredient_consumption_report_route(
    product_id: int,
    start_date: datetime.date = Query(...),
    end_date: datetime.date = Query(...),
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user)
):
    consumption_data_list = utils.get_ingredient_consumption_data(db, product_id, start_date, end_date)
    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {product_id} not found.")

    return utils.get_ingredient_consumption_data(db, product_id, start_date, end_date)
audit_logs_router = APIRouter(prefix="/audit-logs", tags=["Audit Logs Management"])

@audit_logs_router.get("/", response_model=List[schemas.AuditLogSchema], dependencies=[Depends(security.get_current_admin_user)])
async def read_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500), 
    user_id: Optional[int] = Query(None),
    username: Optional[str] = Query(None, min_length=1, max_length=100),
    method: Optional[str] = Query(None, min_length=1, max_length=10),
    endpoint_path_contains: Optional[str] = Query(None, min_length=1),
    status_code: Optional[int] = Query(None),
    start_date: Optional[datetime.datetime] = Query(None),
    end_date: Optional[datetime.datetime] = Query(None),
    db: Session = Depends(get_db)
):
    logs = crud.get_audit_logs(
        db, 
        skip=skip, 
        limit=limit,
        user_id=user_id,
        username_contains=username,
        method=method,
        endpoint_path_contains=endpoint_path_contains,
        status_code=status_code,
        start_date=start_date,
        end_date=end_date
    )
    return logs

@reports_router.get("/product_delivery_history/{product_id}", response_model=List[schemas.ProductDelivery]) # product_id ni path ga o'tkazdim
def product_delivery_history_route(
    product_id: int,
    commons: Annotated[CommonQueryParams, Depends()],
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
    start_date_str: Optional[str] = Query(None, alias="startDate"), 
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
                   responses={
                       200: {
                           "description": "Potential abuse alert data or null if no abuse detected.",
                           "content": {
                               "application/json": {
                                   "examples": {
                                       "alert_found": {
                                           "summary": "Abuse Detected",
                                           "value": { 
                                                "month": "2023-05",
                                                "prepared_portions": 1000,
                                                "potential_portions_at_month_end": 500,
                                                "difference_percentage": 33.33,
                                                "message": "Potential resource misuse..."
                                           }
                                       },
                                       "no_alert": {
                                           "summary": "No Abuse Detected",
                                           "value": None
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
        return None 

    return alert_data
@reports_router.get("/deliveries/all", response_model=List[schemas.ProductDelivery])
async def read_all_product_deliveries(
    commons: Annotated[CommonQueryParams, Depends()],
    db: Session = Depends(get_db),
    current_user: database.User = Depends(security.get_current_manager_user) 
):
    deliveries = crud.get_product_deliveries(
        db, 
        product_id=None, 
        skip=commons.skip, 
        limit=commons.limit
    )
    return deliveries
# --- Routers ni asosiy app ga qo'shish ---
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(products_router)
app.include_router(meals_router)
app.include_router(serving_router)
app.include_router(portions_router)
app.include_router(reports_router)
app.include_router(alerts_router)
app.include_router(audit_logs_router)

if __name__ == "__main__":
    import uvicorn
    print("MAIN.PY: Uvicorn ishga tushirilmoqda http://127.0.0.1:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)