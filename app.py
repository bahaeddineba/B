import os
import secrets
import logging
import traceback
import tempfile
import hashlib
from flask import Flask, render_template, request, jsonify, url_for, flash, redirect
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_sslify import SSLify
from flask_mail import Mail, Message
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import google.generativeai as genai
from gtts import gTTS
import pygame
from config import Config
from models import database as db, User, Doctor, migrate_db, Appointment, AppointmentModification, AppointmentCancellation
from auth import manage_sensitive_keys, retrieve_sensitive_key, auth as auth_blueprint
from datetime import datetime, timedelta, date as dt
load_dotenv(dotenv_path='ai.env', override=True)
print("EMAIL_SENDER:", os.environ.get('EMAIL_SENDER'))
print("EMAIL_PASSWORD:", '*' * len(os.environ.get('EMAIL_PASSWORD', '')) if os.environ.get('EMAIL_PASSWORD') else 'غير موجود')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='medical_assistant.log'
)
app = Flask(__name__)
sslify = SSLify(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medical_assistant.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.urandom(24)
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)
app.register_blueprint(auth_blueprint)
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_SENDER')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_SENDER')
app.config['MAIL_DEBUG'] = True
app.config['MAIL_SUPPRESS_SEND'] = False


mail = Mail(app)

def test_email_connection():
    try:
        with mail.connect() as conn:
            logging.info("اتصال SMTP ناجح")
            return True
    except Exception as e:
        logging.error(f"خطأ في اتصال SMTP: {e}")
        return False

def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=Config.PASSWORD_RESET_SALT)
def verify_reset_token(token, max_age=3600):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt=Config.PASSWORD_RESET_SALT, max_age=max_age)
        return email
    except (SignatureExpired, BadSignature):
        return None
def send_reset_email(user_email):
    try:
        user = User.query.filter_by(email=user_email).first()
        if not user:
            return False
        reset_token = generate_reset_token(user_email)
        reset_url = url_for('auth.reset_password', token=reset_token, _external=True)
        msg = Message(
            'إعادة تعيين كلمة المرور',
            sender=Config.EMAIL_SENDER,
            recipients=[user_email]
        )
        msg.body = f'''
        لقد طلبت إعادة تعيين كلمة المرور للحساب الخاص بك.
        يرجى النقر على الرابط التالي أو نسخه في المتصفح:
        {reset_url}

        إذا لم تطلب إعادة تعيين كلمة المرور، يرجى تجاهل هذا البريد.

        سيكون هذا الرابط صالحًا لمدة ساعة واحدة فقط.

        مع تحيات
        فريق +الشفاء
        '''
        mail.send(msg)
        return True
    except Exception as e:
        logging.error(f"خطأ في إرسال بريد إعادة التعيين: {e}")
        return False
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        if send_reset_email(email):
            flash('تم إرسال رابط إعادة تعيين كلمة المرور إلى بريدك الإلكتروني', 'success')
        else:
            flash('لم يتم العثور على بريد إلكتروني مرتبط بحساب', 'danger')
        
        return redirect(url_for('auth.login'))
    
    return render_template('forgot-password.html')
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    email = verify_reset_token(token)
    if not email:
        flash('رابط إعادة التعيين غير صالح أو منتهي الصلاحية', 'danger')
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if new_password != confirm_password:
            flash('كلمتا المرور غير متطابقتين', 'danger')
            return render_template('reset_password.html', token=token)
        user = User.query.filter_by(email=email).first()
        user.set_password(new_password)
        db.session.commit()
        flash('تم تغيير كلمة المرور بنجاح', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('reset_password.html', token=token)










import threading
import time
from datetime import datetime, timedelta
import queue

class APIKeyRotator:
    def __init__(self, api_keys):
        self.api_keys = api_keys
        self.key_status = {
            key: {
                'last_used': datetime.now(), 
                'exhausted': False, 
                'exhaustion_time': None
            } for key in api_keys
        }
        self.current_key_index = 0
        self.lock = threading.Lock()
        
        self.key_queue = queue.Queue()
        for key in api_keys:
            self.key_queue.put(key)
        
        self.rotation_thread = threading.Thread(target=self._rotate_keys, daemon=True)
        self.monitoring_thread = threading.Thread(target=self._monitor_keys, daemon=True)
        
        self.rotation_thread.start()
        self.monitoring_thread.start()

    def _rotate_keys(self):
        while True:
            time.sleep(60)
            with self.lock:
                if not self.key_queue.empty():
                    current_key = self.key_queue.get()
                    self.key_queue.put(current_key)
                    logging.info(f"تم تدوير المفاتيح. المفتاح الحالي: {current_key[:10]}...")

    def _monitor_keys(self):
        while True:
            time.sleep(30)
            current_time = datetime.now()
            
            with self.lock:
                for key, status in self.key_status.items():
                    if (status['exhausted'] and 
                        status['exhaustion_time'] and 
                        (current_time - status['exhaustion_time']) > timedelta(hours=1)):
                        status['exhausted'] = False
                        status['exhaustion_time'] = None
                        logging.info(f"تم إعادة تنشيط المفتاح: {key[:10]}...")

    def get_next_valid_key(self):
        with self.lock:
            for _ in range(len(self.api_keys)):
                if not self.key_queue.empty():
                    key = self.key_queue.get()
                    self.key_queue.put(key)
                    
                    if not self.key_status[key]['exhausted']:
                        self.key_status[key]['last_used'] = datetime.now()
                        return key
            
            return None

    def mark_key_exhausted(self, key):
        with self.lock:
            if key in self.key_status:
                self.key_status[key]['exhausted'] = True
                self.key_status[key]['exhaustion_time'] = datetime.now()
                logging.warning(f"تم وضع المفتاح كمستنفد: {key[:10]}...")

def initialize_ai():
    try:
        load_dotenv(dotenv_path='ai.env', override=True)
        
        api_keys = [
            os.environ.get(f'GOOGLE_API_KEY_{i}') 
            for i in range(1, 17)
        ]
        
        valid_keys = [key for key in api_keys if key and key.strip()]
        
        if not valid_keys:
            logging.error("لم يتم العثور على مفاتيح API للذكاء الاصطناعي في ai.env")
            return None
        
        key_rotator = APIKeyRotator(valid_keys)
        
        for _ in range(len(valid_keys)):
            try:
                api_key = key_rotator.get_next_valid_key()
                
                if not api_key:
                    logging.error("لا توجد مفاتيح صالحة")
                    return None
                
                genai.configure(api_key=api_key)
                
                available_models = genai.list_models()
                logging.info(f"تم استخدام المفتاح: {api_key[:10]}...")
                
                possible_models = [
                    'gemini-pro', 'models/gemini-pro',
                    'gemini-1.0-pro', 'models/gemini-1.0-pro',
                    'models/gemini-1.5-pro', 'models/gemini-1.5-pro-latest',
                    'models/gemini-1.5-flash', 'models/gemini-1.5-flash-latest',
                    'models/gemini-2.0-flash', 'models/gemini-2.0-pro-exp'
                ]
                
                model_names = [model.name for model in available_models]
                selected_model = next((model for model in possible_models if model in model_names), None)
                
                if selected_model:
                    logging.info(f"تم اختيار النموذج: {selected_model}")
                    return genai.GenerativeModel(selected_model)
            
            except Exception as key_error:
                key_rotator.mark_key_exhausted(api_key)
                logging.warning(f"فشل المفتاح: {api_key[:10]}... - {key_error}")
                continue
        
        logging.error("فشل جميع المفاتيح")
        return None
    
    except Exception as e:
        logging.error(f"خطأ في تهيئة الذكاء الاصطناعي: {e}")
        logging.error(traceback.format_exc())
        return None
    
def safe_initialize_ai():
    try:
        os.makedirs('.keys', exist_ok=True)
        
        model = initialize_ai()
        if model is None:
            fallback_key = os.getenv('FALLBACK_API_KEY')
            if fallback_key:
                logging.warning("محاولة استخدام المفتاح الاحتياطي")
                genai.configure(api_key=fallback_key)
                model = genai.GenerativeModel('gemini-pro')
        
        return model
    except Exception as e:
        logging.critical(f"فشل نهائي في تهيئة الذكاء الاصطناعي: {e}")
        logging.critical(traceback.format_exc())
        return None
model = safe_initialize_ai()
if model is None:
    logging.error("لا يمكن تهيئة المساعد الذكي بأي طريقة")
    
@app.route('/text-to-speech', methods=['POST'])
def text_to_speech_route():
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "نص فارغ"}), 400
        audio_path = text_to_speech(text)
        
        if audio_path:
            return jsonify({
                "status": "success",
                "audio_path": url_for('static', filename=f'audio/{os.path.basename(audio_path)}')
            }), 200
        else:
            return jsonify({"error": "فشل في إنشاء الصوت"}), 500
    
    except Exception as e:
        logging.error(f"خطأ في مسار تحويل النص للصوت: {e}")
        return jsonify({"error": "حدث خطأ غير متوقع"}), 500

def text_to_speech(text):
    try:
        if not text or not text.strip():
            logging.warning("محاولة تحويل نص فارغ إلى كلام")
            return None
        
        os.makedirs(tempfile.gettempdir(), exist_ok=True)
        audio_file = os.path.join(tempfile.gettempdir(), f'speech_output_{hashlib.md5(text.encode()).hexdigest()}.mp3')
        tts = gTTS(text=text, lang='ar', slow=False)
        tts.save(audio_file)
        pygame.mixer.quit()
        pygame.mixer.init()
        try:
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            start_time = pygame.time.get_ticks()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
                pygame.event.pump()
                if pygame.time.get_ticks() - start_time > 30000:
                    logging.warning("تم إيقاف تشغيل الصوت بسبب تجاوز المهلة الزمنية")
                    pygame.mixer.music.stop()
                    break
            pygame.mixer.music.unload()
        
        except pygame.error as sound_error:
            logging.error(f"خطأ في تشغيل الصوت: {sound_error}")
            return None
        
        return audio_file
    
    except Exception as e:
        logging.error(f"خطأ في تحويل النص إلى كلام: {e}")
        logging.error(traceback.format_exc())
        return None
def stop_audio():
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            logging.info("تم إيقاف تشغيل الصوت بنجاح")
            return True
        else:
            logging.warning("محرك الصوت غير مهيأ")
            return False
    except Exception as e:
        logging.error(f"خطأ في إيقاف الصوت: {e}")
        return False

@app.route('/stop_audio', methods=['POST'])
def stop_audio_route():
    """
    مسار ويب لإيقاف تشغيل الصوت
    """
    result = stop_audio()
    return jsonify({"success": result})

@app.route('/get_doctors')
def get_doctors():
    doctors = [
        {
            "name": "مخبر الامل",
            "specialty": "التحاليل الطبية",
            "address": "(Cité Bahmid) شارع سي الحواس  ",
            "phone": "06.69.00.48.29",
            "latitude": 31.962927,
            "longitude": 5.329314,
            "keywords": [ "التحاليل الطبية","الامل","مخبر الامل","تحاليل"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "[07:00-15:00]"]
        },
        {
            "name": "د.هشام قدة",
            "specialty": "طب القلب و الشرايين",
            "address": "شارع 1954/11/01 الشرفة المخادمة",
            "phone": "06.55.77.42.18",
            "latitude": 31.946738,
            "longitude":5.324664,
            "keywords": ["القلب","طب الشرايين","طب القلب ","طبيب قلب","هشام ڤدة"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس","[07:00-19:00]"]
        },
        
        {
            "name": "د.العلوي امين",
            "specialty": "جراحة العضام والمفاصل ",
            "address": "(Cité Bahmid) شارع سي الحواس  ",
            "phone": "06.63.28.51.14",
            "latitude":31.9629653,
            "longitude":5.329034,
            "keywords": ["العلوي","طبيب العضام","جراحة المفاصل","جراحة العضام"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس","[08:00-16:00]"]
        },
        
        {
            "name": "د. بن مونة زينب",
            "specialty": "اخصائية في امراض النساء والتوليد",
            "address": "حي الشرفة (مقابل مسجد الهدى)",
            "phone": "06.57.80.77.00",
            "latitude":31.947835,
            "longitude":5.321555,
            "keywords": ["الولادة","ولادة","اخصائية توليد", "اخصائية نساء","طبيبة توليد","طبيبة نساء"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس","[08:00-16:30]"]
        },
        
        
        
        {
            "name":"د.بوناصر عبد القادر",
            "specialty": "اخصائي امراض وجراحة الكلى المثانة والبروستاتة",
            "address": "حي باحميد",
            "phone": "07.72.24.84.54",
            "latitude":31.962681,
            "longitude":5.328595,
            "keywords": ["عقم الرجال","البروستاتا","البروستاتة","المثانة","جراحة الكلى","طبيب كلى"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس","[08:30-13:30]"]
        },
        
    ]
    return jsonify(doctors)

@app.route('/search_doctors', methods=['GET', 'POST'])
def search_doctors():
    if request.method == 'POST':
        data = request.get_json()
        query = data.get('query', '').strip().lower() if data else ''
    else:
        query = request.args.get('query', '').strip().lower()
    
    if not query:
        return jsonify({"error": "يرجى إدخال كلمة بحث"}), 400
    
    doctors = [
        {
            "name": "مخبر الامل",
            "specialty": "التحاليل الطبية",
            "address": "(Cité Bahmid) شارع سي الحواس  ",
            "phone": "06.69.00.48.29",
            "latitude": 31.962927,
            "longitude": 5.329314,
            "keywords": [ "التحاليل الطبية","الامل","مخبر الامل","تحاليل"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "[07:00-15:00]"]
        },
        {
            "name": "د.هشام قدة",
            "specialty": "طب القلب و الشرايين",
            "address": "شارع 1954/11/01 الشرفة المخادمة",
            "phone": "06.55.77.42.18",
            "latitude": 31.946738,
            "longitude":5.324664,
            "keywords": ["القلب","طب الشرايين","طب القلب ","طبيب قلب","هشام ڤدة"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس","[07:00-19:00]"]
        },
        
        {
            "name": "د.العلوي امين",
            "specialty": "جراحة العضام والمفاصل ",
            "address": "(Cité Bahmid) شارع سي الحواس  ",
            "phone": "06.63.28.51.14",
            "latitude":31.9629653,
            "longitude":5.329034,
            "keywords": ["العلوي","طبيب العضام","جراحة المفاصل","جراحة العضام"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس","[08:00-16:00]"]
        },
        
        
        
        {
            "name": "د. بن مونة زينب",
            "specialty": "اخصائية في امراض النساء والتوليد",
            "address": "حي الشرفة (مقابل مسجد الهدى)",
            "phone": "06.57.80.77.00",
            "latitude":31.947835,
            "longitude":5.321555,
            "keywords": ["الولادة","ولادة","اخصائية توليد", "اخصائية نساء","طبيبة توليد","طبيبة نساء"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس","[08:00-16:30]"]
        },
        
        
        
        {
            "name":"د.بوناصر عبد القادر",
            "specialty": "اخصائي امراض وجراحة الكلى المثانة والبروستاتة",
            "address": "حي باحميد",
            "phone": "07.72.24.84.54",
            "latitude":31.962681,
            "longitude":5.328595,
            "keywords": ["عقم الرجال","البروستاتا","البروستاتة","المثانة","جراحة الكلى","طبيب كلى"],
            "work_days": ["السبت","الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس","[08:30-13:30]"]
        },
    ]
    results = []
    
    for doctor in doctors:
        if query in doctor['address'].lower() or \
           query in doctor['name'].lower() or \
           query in doctor['specialty'].lower():
            results.append(doctor)
        elif any(keyword in query for keyword in doctor.get('keywords', [])):
            results.append(doctor)
    
    return jsonify(results)



@app.route('/chat', methods=['POST'])
def chat():
    if not model:
        return jsonify({
            'error': 'لم يتم تكوين الذكاء الاصطناعي بشكل صحيح'
        }), 500
    data = request.json
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({
            'error': 'الرسالة فارغة'
        }), 400
    try:
        prompt = f"""
        أنت مساعد طبي ذكي مختص بتقديم استشارات أولية.
        قم بتحليل الأعراض التالية بدقة:
        {user_message}

        يرجى تقديم:
        1. :تحليل محتمل للأعراض
        2. :نصائح أولية للعلاج
        3. :أدوية مقترحة (مع الجرعات)
        4. :مستوى الخطورة و متى يجب زيارة الطبيب
        5. :تحذيرات أو مخاطر محتملة
        كن دقيقًا وحذرًا.
        هذا التطبيق مصمم كمساعد استشاري فقط ولا يحل محل الرعاية الطبية المهنية ( قم بعرض هذه الرسالة فقط دون اي اضافات اخرى احرص على عرضها في اخر الرسالة )
        """
        response = model.generate_content(prompt)
        ai_response = response.text
    except Exception as e:
        logging.error(f"خطأ في توليد الرد: {traceback.format_exc()}")
        return jsonify({
            'error': f'حدث خطأ أثناء معالجة الطلب: {str(e)}'
        }), 500
    return jsonify({
        'response': ai_response
    }), 200

@app.route('/update_location', methods=['POST'])
def update_location():
    data = request.get_json()
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy')
    with open('medical_assistant.log', 'a') as log_file:
        log_file.write(f"Location Update: Latitude {latitude}, Longitude {longitude}, Accuracy {accuracy} meters\n")

    return jsonify({"status": "success"}), 200

def send_doctor_notification(appointment):
    """
    إرسال إشعار متعدد القنوات للطبيب مع واجهة محسنة
    """
    try:
        doctor = Doctor.query.filter_by(
            name=appointment.doctor_name, 
            specialty=appointment.specialty
        ).first()
        
        if not doctor:
            logging.warning(f"لم يتم العثور على الطبيب: {appointment.doctor_name}")
            return False
        
        if not doctor.email:
            logging.warning(f"لا يوجد بريد إلكتروني للطبيب {doctor.name}")
            return False

        msg = Message(
            'موعد جديد 🩺 - الشفاء +',
            sender=app.config['MAIL_USERNAME'],
            recipients=[doctor.email]
        )
        
        msg.html = f"""
        <html dir="rtl">
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="background-color: white; border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: #2c3e50; text-align: center; border-bottom: 2px solid #3498db; padding-bottom: 10px;">🩺 إشعار موعد جديد</h2>
                
                <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                    <h3 style="color: #2980b9; margin-bottom: 10px;">تفاصيل الموعد</h3>
                    <table style="width: 100%; direction: rtl;">
                        <tr style="margin-bottom: 10px;">
                            <td style="font-weight: bold; width: 40%; color: #34495e;">اسم المريض:</td>
                            <td style="color: #2c3e50;">{appointment.patient_name}</td>
                        </tr>
                        <tr style="margin-bottom: 10px;">
                            <td style="font-weight: bold; color: #34495e;">رقم الهاتف:</td>
                            <td style="color: #2c3e50;">{appointment.patient_phone}</td>
                        </tr>
                        <tr style="margin-bottom: 10px;">
                            <td style="font-weight: bold; color: #34495e;">التاريخ:</td>
                            <td style="color: #2c3e50;">{appointment.date}</td>
                        </tr>
                        <tr style="margin-bottom: 10px;">
                            <td style="font-weight: bold; color: #34495e;">الوقت:</td>
                            <td style="color: #2c3e50;">{appointment.time}</td>
                        </tr>
                        <tr style="margin-bottom: 10px;">
                            <td style="font-weight: bold; color: #34495e;">سبب الزيارة:</td>
                            <td style="color: #2c3e50;">{appointment.reason or 'غير محدد'}</td>
                        </tr>
                    </table>
                </div>
                
                <div style="background-color: #ecf0f1; padding: 15px; border-radius: 5px; text-align: center; margin-top: 15px;">
                    <p style="margin: 0; color: #7f8c8d; line-height: 1.6;">
                        يرجى التأكد من جاهزيتك للموعد. 
                        <br>
                        يمكنك تأكيد أو إعادة جدولة الموعد من خلال لوحة التحكم الخاصة بك.
                    </p>
                </div>
                
                <div style="text-align: center; margin-top: 20px; font-size: 12px; color: #bdc3c7;">
                    © 2025 الشفاء + - جميع الحقوق محفوظة
                </div>
            </div>
        </body>
        </html>
        """
        
        mail.send(msg)
        logging.info(f"تم إرسال إشعار بريد إلكتروني للطبيب {doctor.name}")
        
        return True
    
    except Exception as e:
        logging.error(f"خطأ في إرسال الإشعار: {e}")
        return False

def send_sms(phone_number, message):
    """
    دالة وهمية لإرسال رسائل SMS
    في المستقبل، يمكن استبدالها بخدمة SMS حقيقية
    """
    try:
        logging.info(f"محاولة إرسال SMS إلى {phone_number}: {message}")
        
        
        return True
    except Exception as e:
        logging.error(f"خطأ في إرسال SMS: {e}")
        return False

def send_doctor_appointment_notification(doctor, appointment):
    """
    إرسال إشعار للطبيب عند حجز موعد جديد
    
    :param doctor: كائن الطبيب
    :param appointment: كائن الموعد
    """
    try:
        if not doctor.email and not doctor.phone:
            logging.warning(f"لا توجد معلومات اتصال للطبيب {doctor.name}")
            return False

        notification_message = f"""
        إشعار موعد جديد
        
        الطبيب العزيز: {doctor.name}
        
        تم حجز موعد جديد في عيادتك:
        
        التاريخ: {appointment.date.strftime('%Y-%m-%d')}
        الوقت: {appointment.time.strftime('%H:%M')}
        اسم المريض: {appointment.patient_name}
        
        يرجى مراجعة التفاصيل والتأكيد.
        """

        if doctor.email:
            try:
                msg = Message(
                    'موعد جديد في العيادة',
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[doctor.email]
                )
                msg.body = notification_message
            except Exception as email_error:
                logging.error(f"خطأ في إرسال البريد الإلكتروني للطبيب: {email_error}")

        if doctor.phone:
            try:
                send_sms(
                    to_phone=doctor.phone,
                    message=notification_message
                )
            except Exception as sms_error:
                logging.error(f"خطأ في إرسال الرسالة النصية للطبيب: {sms_error}")

        return True

    except Exception as e:
        logging.error(f"خطأ في إرسال إشعار للطبيب: {e}")
        return False

@app.route('/book-appointment', methods=['POST'])
def book_appointment():
    try:
        import re
        from datetime import datetime, date as dt, timedelta

        data = request.get_json()
        validation_result = validate_booking_data(data)
        if validation_result[0] == 'error':
            return jsonify(validation_result[1]), 400

        doctor_name = data.get('doctorName')
        specialty = data.get('specialty')
        date = data.get('date')
        time = data.get('time')
        patient_name = data.get('patientName')
        patient_phone = data.get('patientPhone')
        appointment_reason = data.get('appointmentReason', 'لا يوجد')

        doctor = Doctor.query.filter_by(name=doctor_name, specialty=specialty).first()
        if not doctor:
            return jsonify({
                'status': 'error',
                'message': 'الطبيب غير موجود',
                'suggestions': [
                    'تأكد من صحة اسم الطبيب',
                    'تأكد من التخصص الصحيح'
                ],
                'similar_doctors': find_similar_doctors(doctor_name, specialty),
                'available_doctors': get_available_doctors(specialty)
            }), 404

        try:
            appointment_date = datetime.strptime(date, '%Y-%m-%d').date()
            appointment_time = datetime.strptime(time, '%H:%M').time()
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': 'تنسيق التاريخ أو الوقت غير صحيح',
                'details': [
                    'يجب إدخال التاريخ بتنسيق YYYY-MM-DD',
                    'يجب إدخال الوقت بتنسيق HH:MM'
                ]
            }), 400

        date_validation_result = validate_appointment_date(appointment_date)
        if date_validation_result[0] == 'error':
            return jsonify(date_validation_result[1]), 400

        availability_result = check_doctor_availability(doctor, appointment_date, appointment_time)
        if not availability_result[0]:
            return jsonify({
                'status': 'error',
                'message': 'الطبيب غير متاح',
                'details': availability_result[1],
                'doctor_details': {
                    'work_days': doctor.work_days,
                    'work_hours': doctor.work_hours or 'غير محدد'
                }
            }), 400

        conflict_result = check_appointment_conflicts(doctor, appointment_date, appointment_time)
        if conflict_result[0] == 'error':
            return jsonify(conflict_result[1]), 400

        daily_appointments_result = check_daily_appointments_limit(doctor, appointment_date)
        if daily_appointments_result[0] == 'error':
            return jsonify(daily_appointments_result[1]), 400

        patient_constraint_result = check_patient_booking_constraints(
            patient_name, 
            patient_phone, 
            doctor_name, 
            appointment_date
        )
        if patient_constraint_result[0] == 'error':
            return jsonify(patient_constraint_result[1]), 400

        new_appointment = Appointment(
            patient_name=patient_name,
            patient_phone=patient_phone,
            doctor_id=doctor.id,  
            doctor_name=doctor_name,
            specialty=specialty,
            date=appointment_date,
            time=appointment_time,
            reason=appointment_reason,
            status='مؤكد'
        )
        
        db.session.add(new_appointment)
        db.session.commit()
        try:
            send_doctor_notification(new_appointment)
        except Exception as notification_error:
            logging.error(f"فشل إرسال الإشعار للطبيب: {notification_error}")
        return jsonify({
            'status': 'success',
            'message': 'تم حجز الموعد بنجاح',
            'appointment_details': {
                'doctor': doctor_name,
                'specialty': specialty,
                'date': date,
                'time': time,
                'patient_name': patient_name,
                'reason': appointment_reason
            },
            'next_steps': [
                'سيتم إرسال تأكيد عبر الهاتف',
                'يمكنك تعديل أو إلغاء الموعد قبل 24 ساعة'
            ]
        }), 201

    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ في حجز الموعد: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'حدث خطأ غير متوقع',
            'suggestion': 'يرجى المحاولة مرة أخرى أو التواصل مع خدمة العملاء'
        }), 500

def validate_booking_data(data):
    """التحقق من صحة بيانات الحجز"""
    errors = []
    required_fields = [
        ('doctorName', 'اسم الطبيب'),
        ('specialty', 'التخصص'),
        ('date', 'التاريخ'),
        ('time', 'الوقت'),
        ('patientName', 'اسم المريض'),
        ('patientPhone', 'رقم الهاتف')
    ]
    
    for field, message in required_fields:
        if not data.get(field):
            errors.append(f'{message} مطلوب')
    
    if data.get('patientPhone'):
        phone = data['patientPhone']
        if not (isinstance(phone, str) and 
                len(phone) == 10 and 
                phone.startswith(('05', '06', '07')) and 
                phone.isdigit()):
            errors.append('رقم الهاتف الجزائري غير صالح')
    
    return ('error', {
        'status': 'error', 
        'message': 'هناك مشاكل في البيانات المدخلة',
        'details': errors,
        'suggestions': [
            'تأكد من إدخال جميع البيانات المطلوبة',
            'تحقق من صحة رقم الهاتف (10 أرقام يبدأ بـ 05 أو 06 أو 07)'
        ]
    }) if errors else ('success', None)

def validate_appointment_date(appointment_date, max_booking_days=15):
    """التحقق من صحة تاريخ الموعد"""
    today = dt.today()
    max_future_date = today + timedelta(days=max_booking_days)

    if appointment_date < today:
        return 'error', {
            'status': 'error', 
            'message': 'لا يمكن حجز موعد في الماضي',
            'suggestions': [
                'اختر تاريخًا في المستقبل',
                'تأكد من صحة التاريخ المدخل'
            ]
        }

    if appointment_date > max_future_date:
        return 'error', {
            'status': 'error',
            'message': f'لا يمكن حجز موعد بعد {max_booking_days} يومًا',
            'details': [
                f'التاريخ المسموح به من {today} إلى {max_future_date}',
                'يرجى اختيار تاريخ أقرب'
            ],
            'available_date_range': {
                'start': today.strftime('%Y-%m-%d'),
                'end': max_future_date.strftime('%Y-%m-%d')
            }
        }
    
    return 'success', None

def check_doctor_availability(doctor, appointment_date, appointment_time):
    """التحقق من توفر الطبيب في التاريخ والوقت المحدد"""
    day_name_mapping = {
        'Saturday': 'السبت', 'Sunday': 'الأحد', 
        'Monday': 'الاثنين', 'Tuesday': 'الثلاثاء',
        'Wednesday': 'الأربعاء', 'Thursday': 'الخميس',
        'Friday': 'الجمعة'
    }
    
    logging.info(f"التحقق من توفر الطبيب: {doctor.name}, التاريخ: {appointment_date}, الوقت: {appointment_time}")
    logging.info(f"أيام العمل للطبيب: {doctor.work_days}, ساعات العمل: {doctor.work_hours}")
    
    day_name = day_name_mapping[appointment_date.strftime('%A')]
    
    if '7/24' not in doctor.work_days and day_name not in doctor.work_days:
        logging.warning(f"الطبيب غير متاح في يوم {day_name}")
        return False, f'الطبيب غير متاح في يوم {day_name}'
    
    if doctor.work_hours:
        try:
            start_time, end_time = doctor.work_hours.split('-')
            start_hour, start_minute = map(int, start_time.split(':'))
            end_hour, end_minute = map(int, end_time.split(':'))
            
            if not (start_hour <= appointment_time.hour < end_hour):
                logging.warning(f"الموعد خارج ساعات العمل ({doctor.work_hours})")
                return False, f'الموعد خارج ساعات العمل المحددة ({doctor.work_hours})'
        except (ValueError, TypeError):
            logging.error(f"تنسيق ساعات العمل غير صحيح للطبيب {doctor.name}")
            return False, 'تنسيق ساعات العمل غير صحيح'
    
    logging.info(f"الطبيب {doctor.name} متاح في التاريخ والوقت المطلوب")
    return True, ''

def check_appointment_conflicts(doctor, appointment_date, appointment_time):
    """التحقق من تعارض المواعيد"""
    conflicting_appointments = Appointment.query.filter(
        Appointment.doctor_id == doctor.id,
        Appointment.date == appointment_date,
        Appointment.status != 'ملغى'
    ).all()

    interval = doctor.appointment_interval or 30

    for existing_appointment in conflicting_appointments:
        existing_datetime = datetime.combine(existing_appointment.date, existing_appointment.time)
        new_datetime = datetime.combine(appointment_date, appointment_time)
        
        if abs(existing_datetime - new_datetime) < timedelta(minutes=interval):
            return 'error', {
                'status': 'error', 
                'message': 'هذا الموعد متعارض مع موعد آخر',
                'details': [
                    f'يجب ترك مسافة {interval} دقيقة على الأقل بين المواعيد',
                    f'الموعد المتعارض في: {existing_datetime.strftime("%Y-%m-%d %H:%M")}'
                ]
            }
    
    return 'success', None

def check_daily_appointments_limit(doctor, appointment_date):
    """التحقق من الحد الأقصى للمواعيد اليومية"""
    daily_appointments = Appointment.query.filter(
        Appointment.doctor_id == doctor.id,
        Appointment.date == appointment_date,
        Appointment.status != 'ملغى'
    ).count()
    
    max_daily_appointments = doctor.max_daily_appointments or 10

    if daily_appointments >= max_daily_appointments:
        return 'error', {
            'status': 'error',
            'message': 'تم الوصول إلى الحد الأقصى للمواعيد اليومية',
            'details': [
                f'الحد الأقصى للمواعيد اليومية هو {max_daily_appointments}',
                'الرجاء اختيار تاريخ آخر'
            ]
        }
    
    return 'success', None

def check_patient_booking_constraints(patient_name, patient_phone, doctor_name, appointment_date):
    """التحقق من القيود الزمنية للمريض"""
    logging.info(f"فحص قيود الحجز: المريض {patient_name}, الطبيب {doctor_name}, التاريخ {appointment_date}")
    
    existing_appointments = Appointment.query.filter(
        ((Appointment.patient_name == patient_name) & 
         (Appointment.patient_phone == patient_phone) & 
         (Appointment.doctor_name == doctor_name)) | 
        ((
            (Appointment.patient_name == patient_name) | 
            (Appointment.patient_phone == patient_phone)
        ) & 
        (Appointment.doctor_name == doctor_name)),
        
        Appointment.status == 'مؤكد',
        Appointment.date <= appointment_date
    ).order_by(Appointment.date.desc()).limit(3).all()
    
    if existing_appointments:
        for appointment in existing_appointments:
            time_since_last_appointment = (appointment_date - appointment.date).total_seconds() / 3600
            
            if time_since_last_appointment < 24:
                logging.warning(f"رفض الحجز - موعد سابق في {appointment.date}, متبقي {int(24 - time_since_last_appointment)} ساعة")
                return 'error', {
                    'status': 'error',
                    'code': 'APPOINTMENT_FREQUENCY_LIMIT',
                    'message': 'لا يمكن حجز موعد جديد قبل مرور 24 ساعة من موعدك السابق',
                    'details': [
                        f'موعد سابق: {appointment.date}',
                        f'الطبيب: {doctor_name}',
                        f'متبقي: {int(24 - time_since_last_appointment)} ساعة للحجز المجدد',
                        'تم رفض الحجز لمنع الإساءة'
                    ],
                    'recommendations': [
                        'انتظر المدة المطلوبة قبل حجز موعد جديد',
                        'تواصل مع خدمة العملاء للمساعدة'
                    ]
                }
    
    return 'success', None

def get_available_doctors(specialty=None):
    """دالة مساعدة لإرجاع قائمة الأطباء المتاحين"""
    query = Doctor.query
    if specialty:
        query = query.filter_by(specialty=specialty)
    
    doctors = query.all()
    
    return [
        {
            'name': doctor.name,
            'specialty': doctor.specialty,
            'work_days': doctor.work_days,
            'work_hours': doctor.work_hours or 'غير محدد',
            'appointment_interval': doctor.appointment_interval or 30,
            'max_daily_appointments': doctor.max_daily_appointments or 10
        } for doctor in doctors
    ]

def find_similar_doctors(doctor_name, specialty):
    """البحث عن أطباء مشابهين"""
    similar_doctors = Doctor.query.filter(
        (Doctor.name.like(f'%{doctor_name}%')) & 
        (Doctor.specialty == specialty)
    ).limit(5).all()
    
    return [
        {
            'name': doctor.name,
            'specialty': doctor.specialty
        } for doctor in similar_doctors
    ]
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('auth.login'))

@app.route('/')
def index():
    return redirect(url_for('auth.login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('index.html', user=current_user)

def insert_doctors():
    """
    دالة لإدراج الأطباء في قاعدة البيانات
    """
    doctors_data = [
        {
            "name": "مخبر الامل",
            "specialty": "التحاليل الطبية",
            "email": "elamel.laboratoire@gmail.com",
            "phone": "06.69.00.48.29",
            "address": "(Cité Bahmid) شارع سي الحواس",
            "latitude": 31.962927,
            "longitude": 5.329314,
            "keywords": "التحاليل الطبية, الامل, مخبر الامل, تحاليل",
            "work_days": "السبت , الأحد , الاثنين , الثلاثاء , الأربعاء , الخميس",
            "work_hours": "07:00-15:00",
            "appointment_interval": 30,
            "max_daily_appointments": 25,
            "consultation_fee": 1500 
        },
        {
            "name": "د.هشام قدة",
            "specialty": "طب القلب و الشرايين",
            "email": "dr.guedda.hc@gmail.com",
            "phone": "06.55.77.42.18",
            "address": "شارع 1954/11/01 الشرفة المخادمة",
            "latitude": 31.946738,
            "longitude": 5.324664,
            "keywords": "القلب, طب الشرايين, طب القلب, طبيب قلب, هشام ڤدة",
            "work_days": "السبت , الأحد , الاثنين , الثلاثاء , الأربعاء , الخميس",
            "work_hours": "07:00-19:00",
            "appointment_interval": 45,
            "max_daily_appointments": 25,
            "consultation_fee": 5000
        },
        {
            "name": "د.العلوي امين",
            "specialty": "جراحة العضام والمفاصل ",
            "email": "laloui_amine@yahoo.fr",
            "phone": "06.63.28.51.14",
            "address": "(Cité Bahmid) شارع سي الحواس  ",
            "latitude":31.9629653,
            "longitude":5.329034,
            "keywords": "العلوي , طبيب العضام, جراحة المفاصل ,جراحة العضام",
            "work_days": "السبت , الأحد , الاثنين , الثلاثاء , الأربعاء , الخميس",
            "work_hours": "08:00-16:00",
            "appointment_interval": 30,
            "max_daily_appointments": 15,
            "consultation_fee": 5000
        },
        {
            "name": "د. بن مونة زينب",
            "specialty": "اخصائية في امراض النساء والتوليد",
            "email": "zinebbenmouna@gmail.com",
            "phone": "06.57.80.77.00",
            "address": "حي الشرفة (مقابل مسجد الهدى)",
            "latitude":31.947835,
            "longitude":5.321555,
            "keywords": "ولادة,اخصائية توليد,اخصائية نساء,طبيبة توليد, طبيبة نساء",
            "work_days": "السبت , الأحد , الاثنين , الثلاثاء , الأربعاء , الخميس",
            "work_hours": "08:00-16:30",
            "appointment_interval": 30,
            "max_daily_appointments": 20,
            "consultation_fee": 2000
        },
        {
            "name":"د.بوناصر عبد القادر",
            "specialty": "اخصائي امراض وجراحة الكلى المثانة والبروستاتة",
            "email": "urobounaceur@hotmail.com",
            "phone": "07.72.24.84.54",
            "address": "حي باحميد",
            "latitude":31.962681,
            "longitude":5.328595,
            "keywords": " البروستاتا, البروستاتة, المثانة, جراحة الكلى , طبيب كلى , عقم الرجال ",
            "work_days": "السبت , الأحد , الاثنين , الثلاثاء , الأربعاء , الخميس",
            "work_hours": "08:30-13:30",
            "appointment_interval": 15,
            "max_daily_appointments": 30,
            "consultation_fee": 2000
        },
        
        
        
    ]
    
    for doctor_info in doctors_data:
        existing_doctor = Doctor.query.filter_by(
            name=doctor_info['name'],
            specialty=doctor_info['specialty']
        ).first()
        
        if not existing_doctor:
            new_doctor = Doctor(
                name=doctor_info['name'],
                specialty=doctor_info['specialty'],
                email=doctor_info['email'],
                phone=doctor_info['phone'],
                address=doctor_info.get('address'),
                latitude=doctor_info.get('latitude'),
                longitude=doctor_info.get('longitude'),
                keywords=doctor_info.get('keywords'),
                work_days=doctor_info.get('work_days'),
                work_hours=doctor_info.get('work_hours'),
                consultation_fee=doctor_info.get('consultation_fee'),
                appointment_interval=doctor_info.get('appointment_interval', 30),
                max_daily_appointments=doctor_info.get('max_daily_appointments', 10)
            )
            
            db.session.add(new_doctor)
    
    try:
        db.session.commit()
        logging.info("تم إدراج الأطباء بنجاح")
        return True
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ في إدراج الأطباء: {e}")
        return False

def check_doctors_data():
    """
    دالة للتحقق من بيانات الأطباء المخزنة في قاعدة البيانات
    """
    try:
        doctors = Doctor.query.all()
        
        if not doctors:
            print("❌ لا توجد بيانات للأطباء في قاعدة البيانات")
            return False
        
        print(f"✅ تم العثور على {len(doctors)} طبيب")
        
        print("\n📋 تفاصيل الأطباء:")
        for doctor in doctors:
            print("-" * 50)
            print(f"الاسم: {doctor.name}")
            print(f"التخصص: {doctor.specialty}")
            print(f"البريد الإلكتروني: {doctor.email}")
            print(f"الهاتف: {doctor.phone}")
            print(f"أيام العمل: {doctor.work_days}")
            print(f"ساعات العمل: {doctor.work_hours}")
            print(f"فترة المواعيد: {doctor.appointment_interval} دقيقة")
            print(f"الحد الأقصى للمواعيد اليومية: {doctor.max_daily_appointments}")
        
        return True
    
    except Exception as e:
        print(f"❌ حدث خطأ أثناء التحقق من بيانات الأطباء: {e}")
        return False

def find_similar_doctors(name, specialty):
    """
    البحث عن أطباء مشابهين باستخدام البحث التقريبي
    """
    from sqlalchemy import func
    
    similar_doctors = Doctor.query.filter(
        func.lower(func.replace(Doctor.name, ' ', '')) == func.lower(func.replace(name, ' ', '')),
        func.lower(Doctor.specialty) == func.lower(specialty)
    ).all()
    
    if not similar_doctors:
        similar_doctors = Doctor.query.filter(
            func.lower(Doctor.name).like(f'%{name.lower()}%'),
            func.lower(Doctor.specialty).like(f'%{specialty.lower()}%')
        ).all()
    
    return [
        {
            'name': doctor.name,
            'specialty': doctor.specialty,
            'work_days': doctor.work_days,
            'work_hours': doctor.work_hours or 'غير محدد',
            'match_score': 1
        } for doctor in similar_doctors
    ]



if __name__ == '__main__':
    migrate_db(app)
    app.run(debug=True)
