# Bog'cha uchun Ovqatlar va Ombor Hisoboti Dasturi

Ushbu dasturiy ta'minot bog'cha oshxonasi faoliyatini avtomatlashtirish, mahsulotlar hisobini yuritish, taomlar retseptlarini boshqarish, ovqat berish jarayonini qayd etish va turli hisobotlarni generatsiya qilish uchun mo'ljallangan. Dastur BTEC Higher Nationals in Digital Technologies, Unit 4: Programming fani doirasida topshiriq sifatida ishlab chiqilgan.

## Texnologiyalar Steki

* **Backend:**
    * Python 3.10+
    * FastAPI
    * SQLAlchemy (ORM sifatida)
    * Uvicorn (ASGI server)
    * Pydantic (Ma'lumotlar validatsiyasi uchun)
    * Python-jose (JWT tokenlari uchun)
    * Passlib, Bcrypt (Parollarni xeshlash uchun)
    * APScheduler (Rejalashtirilgan vazifalar uchun, masalan, eski loglarni o'chirish)
* **Frontend:**
    * HTML5
    * CSS3 (Bootstrap 5 bilan)
    * Vanilla JavaScript (ES6+)
    * Chart.js (Grafiklar uchun)
* **Ma'lumotlar Bazasi:**
    * SQLite (Standart sozlama, ishlab chiqish uchun)
    * (Production uchun PostgreSQL tavsiya etiladi)
* **Versiyalarni Boshqarish:**
    * Git

## Asosiy Funksiyalar

* **Mahsulotlar Boshqaruvi:** Yangi mahsulot turlarini qo'shish, omborga mahsulot kirim qilish, qoldiqlarni kuzatish.
* **Taomlar Boshqaruvi:** Taomlar va ularning retseptlarini (ingredientlar va miqdorlari) yaratish va tahrirlash.
* **Ovqat Berish Tizimi:** Berilgan ovqat porsiyalarini qayd etish, ombordagi ingredientlarni avtomatik kamaytirish. Ingredient yetishmasligi haqida ogohlantirish.
* **Porsiya Hisoblash:** Mavjud mahsulotlar asosida har bir taomdan necha porsiya tayyorlash mumkinligini hisoblash.
* **Foydalanuvchilarni Boshqarish:** Tizim foydalanuvchilarini (admin, menejer, oshpaz) yaratish va boshqarish.
* **Rolga Asoslangan Kirish (RBAC):** Har bir foydalanuvchi rolidan kelib chiqib, dasturning ma'lum funksiyalariga kirish huquqi cheklangan.
* **Audit Loglash:** Tizimdagi muhim o'zgartirishlar (POST, PUT, DELETE) avtomatik tarzda loglanadi va admin tomonidan ko'rilishi mumkin. Eski loglar avtomatik o'chiriladi.
* **Hisobotlar va Vizualizatsiya:**
    * Ingredientlar sarfi grafigi.
    * Oylik tayyorlangan va potensial porsiyalar haqida hisobot.
    * Berilgan taomlar tarixi.
* **Ogohlantirishlar:**
    * Mahsulot miqdori kritik darajadan kamayganda.
    * Oylik hisobotda ehtimoliy suiiste'mol aniqlanganda.

## Talablar (Prerequisites)

* Python 3.10 yoki undan yuqori versiyasi o'rnatilgan bo'lishi.
* `pip` (Python paket menejeri) mavjud bo'lishi.
* (Ixtiyoriy) Git o'rnatilgan bo'lishi (agar repozitoriydan yuklab olinsa).
* Zamonaviy web-brauzer (Google Chrome, Firefox, Edge).

## O'rnatish va Ishga Tushirish

1.  **Loyihani Yuklab Olish/Klonlash:**
    ```bash
    git clone https://github.com/SanjarbekMatlabov/bogcha-crm.git
    cd app
    ```
    Agar ZIP arxivda bo'lsa, uni oching va loyiha papkasiga o'ting.

2.  **Virtual Muhit Yaratish va Aktivlashtirish (Tavsiya Etiladi):**
    Loyiha papkasida terminalni oching va quyidagi buyruqlarni bajaring:
    ```bash
    python -m venv venv
    ```
    Windows uchun:
    ```bash
    venv\Scripts\activate
    ```
    Linux/MacOS uchun:
    ```bash
    source venv/bin/activate
    ```

3.  **Backend Bog'liqliklarini O'rnatish:**
    Loyiha papkasida `requirements.txt` fayli mavjudligiga ishonch hosil qiling va quyidagi buyruqni bajaring:
    ```bash
    pip install -r requirements.txt
    ```
    Agar `requirements.txt` fayli bo'lmasa, asosiy paketlarni qo'lda o'rnatishingiz mumkin:
    ```bash
    pip install fastapi uvicorn[standard] sqlalchemy python-jose[cryptography] passlib[bcrypt] pydantic APScheduler Jinja2 python-multipart
    ```
    (*Eslatma: `python-jose[cryptography]` o'rniga ba'zan faqat `python-jose` va alohida `cryptography` o'rnatish kerak bo'lishi mumkin.*)

4.  **Ma'lumotlar Bazasini Sozlash:**
    Dastur birinchi marta ishga tushganda, `main.py` faylidagi `on_startup_event` SQLite ma'lumotlar bazasi faylini (`bogcha_app.db`) va kerakli jadvallarni (shu jumladan `audit_logs`) avtomatik yaratadi. Shuningdek, standart foydalanuvchilarni (admin, chef, manager) ham yaratadi.

5.  **Backend Serverini Ishga Tushirish:**
    Loyiha ildiz papkasida (qayerda `main.py` joylashgan bo'lsa) terminalda quyidagi buyruqni bajaring:
    ```bash
    uvicorn main:app --reload
    ```
    Server odatda `http://127.0.0.1:8000` manzilida ishga tushadi. `--reload` bayrog'i kodga o'zgartirish kiritilganda serverni avtomatik qayta ishga tushiradi (ishlab chiqish uchun qulay).

6.  **Frontendga Kirish:**
    * Web-brauzeringizni oching.
    * Dastlab tizimga kirish uchun `http://127.0.0.1:8000/login.html` manziliga o'ting.
    * Muvaffaqiyatli autentifikatsiyadan so'ng, siz avtomatik ravishda asosiy panelga (`index.html` yoki `/`) yo'naltirilishingiz kerak.

## Standart Foydalanuvchi Ma'lumotlari

Dastur birinchi marta ishga tushganda quyidagi standart foydalanuvchilar yaratiladi (agar ular bazada mavjud bo'lmasa):

* **Admin:**
    * Username: `admin`
    * Password: `adminpassword`
* **Oshpaz (Chef):**
    * Username: `chef`
    * Password: `chefpassword`
* **Menejer (Manager):**
    * Username: `manager`
    * Password: `managerpassword`

**Xavfsizlik uchun ushbu parollarni birinchi kirishdan keyin o'zgartirish tavsiya etiladi!** (Hozirgi dasturda foydalanuvchi o'z parolini o'zgartirish funksiyasi qo'shilmagan, lekin admin boshqa foydalanuvchilarning parolini o'zgartira olishi kerak).

## API Dokumentatsiyasi

FastAPI avtomatik tarzda interaktiv API dokumentatsiyasini yaratadi. Unga quyidagi manzillar orqali kirishingiz mumkin (server ishlayotgan paytda):

* Swagger UI: `http://127.0.0.1:8000/docs`
* ReDoc: `http://127.0.0.1:8000/redoc`

