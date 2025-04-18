from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, login_required, logout_user, current_user
from models import database as db, User
import re
import time
from functools import wraps
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import render_template, request, redirect, url_for, flash
from models import User, db
from datetime import datetime, timedelta
import os
import logging
import traceback

# إنشاء قاموس لتتبع محاولات تسجيل الدخول
login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 300  # 5 دقائق

def validate_password_strength(password):
    """
    التحقق من قوة كلمة المرور
    - طول 8 أحرف على الأقل
    - يحتوي على حرف كبير وصغير
    - يحتوي على رقم
    - يحتوي على رمز خاص
    """
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'\d', password):
        return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True

def rate_limit_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        email = request.form.get('email')
        client_ip = request.remote_addr

        # مفتاح فريد للمستخدم والعنوان IP
        key = f"{email}_{client_ip}"

        # التحقق من عدد محاولات تسجيل الدخول
        if key in login_attempts:
            attempts, last_attempt_time = login_attempts[key]
            
            # التحقق من وجود حظر
            if attempts >= MAX_LOGIN_ATTEMPTS:
                # التحقق مما إذا كانت فترة الحظر لم تنته بعد
                if time.time() - last_attempt_time < LOCKOUT_DURATION:
                    flash('تم حظر تسجيل الدخول مؤقتًا. حاول مرة أخرى لاحقًا', 'error')
                    return redirect(url_for('auth.login'))
                else:
                    # إعادة تعيين محاولات تسجيل الدخول بعد انتهاء فترة الحظر
                    login_attempts[key] = (0, 0)

        return f(*args, **kwargs)
    return decorated_function

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
@rate_limit_login
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # التحقق من صحة البيانات
        if not email or not password:
            flash('يرجى إدخال البريد الإلكتروني وكلمة المرور', 'error')
            return redirect(url_for('auth.login'))
        
        # التحقق من تنسيق البريد الإلكتروني
        if not User.validate_email(email):
            flash('البريد الإلكتروني غير صالح', 'error')
            return redirect(url_for('auth.login'))
        
        user = User.query.filter_by(email=email).first()
        
        # التحقق من عدم وجود المستخدم
        if not user:
            return redirect(url_for('auth.signup', email=email))
        
        # التحقق من وجود المستخدم وصحة كلمة المرور
        if user and user.check_password(password):
            # التحقق من حالة الحساب
            if user.is_active == False:
                flash('الحساب معطل. يرجى التواصل مع الدعم', 'warning')
                return redirect(url_for('auth.login'))
            
            # تسجيل وقت آخر دخول
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # تسجيل الدخول
            login_user(user)
            
            # مسح محاولات تسجيل الدخول الفاشلة
            client_ip = request.remote_addr
            key = f"{email}_{client_ip}"
            if key in login_attempts:
                del login_attempts[key]
            # توجيه المستخدم إلى لوحة التحكم
            
            return redirect(url_for('dashboard'))
        
        else:
            # معالجة محاولات تسجيل الدخول الفاشلة
            client_ip = request.remote_addr
            key = f"{email}_{client_ip}"
            
            # تتبع محاولات تسجيل الدخول
            if key in login_attempts:
                attempts, last_attempt_time = login_attempts[key]
                
                # زيادة عدد المحاولات
                login_attempts[key] = (attempts + 1, time.time())
                
                # التحقق من تجاوز الحد الأقصى للمحاولات
                if attempts + 1 >= MAX_LOGIN_ATTEMPTS:
                    # حظر المستخدم مؤقتًا
                    flash(f'تم حظر تسجيل الدخول لمدة {LOCKOUT_DURATION // 60} دقائق بسبب عدة محاولات فاشلة', 'danger')
                    
                    # اختياري: تسجيل محاولة الاختراق
                    logging.warning(f"محاولات دخول متعددة فاشلة للبريد: {email} من IP: {client_ip}")
            else:
                # إنشاء سجل المحاولات الأول
                login_attempts[key] = (1, time.time())
            
            # رسالة خطأ موحدة
            flash('البريد الإلكتروني أو كلمة المرور غير صحيحة', 'error')
            return redirect(url_for('auth.login'))
    
    return render_template('login.html')

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        
        # التحقق من صحة البيانات
        if not email or not password or not full_name:
            flash('يرجى ملء جميع الحقول المطلوبة', 'error')
            return redirect(url_for('auth.signup'))
        
        # التحقق من صحة البريد الإلكتروني
        if not User.validate_email(email):
            flash('البريد الإلكتروني غير صالح', 'error')
            return redirect(url_for('auth.signup'))
        
        # التحقق من وجود البريد الإلكتروني مسبقًا
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('البريد الإلكتروني مستخدم بالفعل', 'error')
            return redirect(url_for('auth.signup'))
        
        # التحقق من قوة كلمة المرور
        if not validate_password_strength(password):
            flash('كلمة المرور ضعيفة. يجب أن تحتوي على 8 أحرف على الأقل، وحروف كبيرة وصغيرة، وأرقام، ورموز خاصة', 'error')
            return redirect(url_for('auth.signup'))
        
        new_user = User(
            email=email,
            full_name=full_name
        )
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            logging.info(f'User registered successfully: {email}')
            flash('تم إنشاء الحساب بنجاح. يرجى تسجيل الدخول', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            logging.error(f'Error registering user {email}: {str(e)}')
            flash('حدث خطأ أثناء إنشاء الحساب. يرجى المحاولة مرة أخرى', 'error')
            return redirect(url_for('auth.signup'))
    
    return render_template('signup.html')

@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            # إنشاء رمز إعادة التعيين
            reset_token = secrets.token_urlsafe(32)
            user.reset_token = reset_token
            user.reset_token_expiration = datetime.utcnow() + timedelta(hours=1)
            
            try:
                # إرسال بريد إلكتروني
                if send_password_reset_email(user.email, reset_token):
                    db.session.commit()
                    flash('تم إرسال رابط إعادة تعيين كلمة المرور إلى بريدك الإلكتروني', 'success')
                    return redirect(url_for('auth.login'))
            except Exception as e:
                db.session.rollback()
                flash('حدث خطأ أثناء إرسال البريد الإلكتروني', 'danger')
        else:
            flash('البريد الإلكتروني غير مسجل', 'danger')
    
    return render_template('forgot-password.html')

def send_password_reset_email(email, reset_token):
    # إعداد تفاصيل البريد الإلكتروني
    sender_email = os.environ.get('EMAIL_SENDER')
    sender_password = os.environ.get('EMAIL_PASSWORD', '').replace(' ', '')
    
    # طباعة المتغيرات للتصحيح
    print(f"Sending reset email - Sender: {sender_email}")
    logging.info(f"محاولة إرسال بريد إلكتروني من {sender_email}")
    
    # التحقق من وجود معلومات البريد الإلكتروني
    if not sender_email or not sender_password:
        logging.error("لم يتم تعيين معلومات البريد الإلكتروني")
        flash('خطأ: يرجى تكوين إعدادات البريد الإلكتروني أولاً.', 'danger')
        return False

    try:
        # إنشاء رسالة البريد الإلكتروني
        message = MIMEMultipart()
        message['From'] = sender_email
        message['To'] = email
        message['Subject'] = 'إعادة تعيين كلمة المرور'
        
        # إنشاء رابط إعادة التعيين
        reset_url = url_for('auth.reset_password', token=reset_token, _external=True)
        
        # نص الرسالة
        body = f"""
        مرحبًا،

        لقد تلقينا طلبًا لإعادة تعيين كلمة المرور لحسابك.
        
        إذا كنت قد طلبت إعادة تعيين كلمة المرور، يرجى النقر على الرابط التالي:
        {reset_url}

        ملاحظات مهمة:
        - سيكون هذا الرابط صالحًا لمدة ساعة واحدة فقط
        - إذا لم تطلب إعادة تعيين كلمة المرور، يرجى تجاهل هذا البريد

        مع أطيب التحيات،
        فريق دعم التطبيق
        """
        
        # إضافة نص الرسالة
        message.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # إرسال البريد الإلكتروني
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            try:
                server.login(sender_email, sender_password)
                server.send_message(message)
                logging.info(f"تم إرسال بريد إعادة التعيين بنجاح إلى {email}")
                flash('تم إرسال رابط إعادة تعيين كلمة المرور إلى بريدك الإلكتروني', 'success')
                return True
            except smtplib.SMTPAuthenticationError as auth_error:
                error_message = str(auth_error)
                logging.error(f"فشل المصادقة SMTP: {error_message}")
                flash(f"""
                خطأ في المصادقة. يرجى التأكد من:
                1. استخدام كلمة مرور التطبيق الصحيحة
                2. تفعيل المصادقة الثنائية
                3. إنشاء كلمة مرور تطبيق جديدة
                """, 'danger')
            except Exception as e:
                logging.error(f"خطأ في إرسال البريد: {str(e)}")
                flash('حدث خطأ أثناء إرسال البريد الإلكتروني', 'danger')
        
        return False
    except Exception as e:
        logging.error(f"خطأ في إرسال البريد: {str(e)}")
        flash('حدث خطأ أثناء إرسال البريد الإلكتروني', 'danger')
        return False

@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or user.reset_token_expiration < datetime.utcnow():
        flash('رابط إعادة التعيين غير صالح أو منتهي الصلاحية', 'danger')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('كلمتا المرور غير متطابقتين', 'danger')
            return render_template('reset-password.html', token=token)
        
        # التحقق من قوة كلمة المرور
        if len(new_password) < 12:
            flash('يجب أن تكون كلمة المرور 12 حرفًا على الأقل', 'danger')
            return render_template('reset-password.html', token=token)
        
        # تحديث كلمة المرور
        user.set_password(new_password)
        user.reset_token = None
        user.reset_token_expiration = None
        
        try:
            db.session.commit()
            flash('تم إعادة تعيين كلمة المرور بنجاح', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('حدث خطأ أثناء إعادة تعيين كلمة المرور', 'danger')
    
    return render_template('reset-password.html', token=token)

# استيراد نظام إدارة المفاتيح
from key_manager import KeyManager

# إضافة دالة جديدة لإدارة المفاتيح
def manage_sensitive_keys(master_password):
    """
    إدارة المفاتيح الحساسة بشكل آمن
    
    Args:
        master_password (str): كلمة المرور الرئيسية للتشفير
    """
    try:
        # إنشاء مجلد .keys إذا لم يكن موجودًا
        os.makedirs('.keys', exist_ok=True)
        
        # تشفير مفتاح API
        api_key = os.getenv('GEMINI_API_KEY')
        if api_key:
            encrypted_key = KeyManager.encrypt_key(api_key, master_password)
            KeyManager.save_encrypted_key('google_api_key', encrypted_key)
            logging.info("تم تشفير المفتاح بنجاح")
        else:
            logging.warning("لم يتم العثور على مفتاح API للتشفير")
    except Exception as e:
        logging.error(f"خطأ في تشفير المفتاح: {e}")
        logging.error(traceback.format_exc())

def retrieve_sensitive_key(key_name, master_password):
    """
    استرجاع مفتاح مشفر
    
    Args:
        key_name (str): اسم المفتاح
        master_password (str): كلمة المرور الرئيسية لفك التشفير
    
    Returns:
        str: المفتاح المفك
    """
    try:
        encrypted_key = KeyManager.load_encrypted_key(key_name)
        return KeyManager.decrypt_key(encrypted_key, master_password)
    except Exception as e:
        logging.error(f"خطأ في استرجاع المفتاح: {e}")
        return None

# التأكد من أن هذا السطر موجود في نهاية الملف
__all__ = ['auth', 'manage_sensitive_keys', 'retrieve_sensitive_key']