from sqlalchemy import inspect
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import re
from sqlalchemy import inspect
from datetime import datetime, timedelta
import logging

# إعداد التسجيل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# إنشاء كائن SQLAlchemy بشكل صريح مع إعدادات متقدمة
db = SQLAlchemy(
    session_options={
        'autocommit': False,  # منع الالتزام التلقائي
        'autoflush': False,   # التحكم اليدوي في حفظ التغييرات
        'expire_on_commit': False  # الاحتفاظ بالكائنات بعد الالتزام
    }
)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # معرفات التسجيل
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    facebook_id = db.Column(db.String(100), unique=True, nullable=True)
    
    # معلومات إضافية
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=True)
    medical_history = db.Column(db.Text, nullable=True)
    
    # حقول إعادة تعيين كلمة المرور
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expiration = db.Column(db.DateTime, nullable=True)
    
    # طرق التحقق والتسجيل
    def set_password(self, password):
        """تعيين كلمة المرور المشفرة"""
        if password:
            self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """التحقق من صحة كلمة المرور"""
        return self.password_hash and check_password_hash(self.password_hash, password)
    
    @staticmethod
    def validate_email(email):
        """التحقق من صحة البريد الإلكتروني"""
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return False
        
        # منع بعض أنماط البريد الإلكتروني الشائعة
        blocked_domains = ['example.com', 'test.com']
        domain = email.split('@')[1]
        if domain.lower() in blocked_domains:
            return False
        
        return True

class Doctor(db.Model):
    __tablename__ = 'doctors'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    specialty = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    address = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    keywords = db.Column(db.Text, nullable=True)
    work_days = db.Column(db.String(100), nullable=True)
    work_hours = db.Column(db.String(100), nullable=True)
    consultation_fee = db.Column(db.Float, nullable=True)
    
    # الفاصل الزمني بين المواعيد (بالدقائق)
    appointment_interval = db.Column(db.Integer, default=30, nullable=False)
    
    # الحد الأقصى للمواعيد اليومية
    max_daily_appointments = db.Column(db.Integer, default=10, nullable=False)
    
    # العلاقات مع المواعيد
    appointments = db.relationship('Appointment', 
                                   back_populates='doctor', 
                                   cascade='all, delete-orphan',
                                   overlaps="booked_doctor")
    
    def __repr__(self):
        return f'<Doctor {self.name} - {self.specialty}>'

class Appointment(db.Model):
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    
    # معلومات المريض
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    patient_name = db.Column(db.String(100), nullable=False)
    patient_phone = db.Column(db.String(20), nullable=False)
    
    # معلومات الطبيب
    doctor_name = db.Column(db.String(100), nullable=False)
    specialty = db.Column(db.String(100), nullable=False)
    
    # تفاصيل الموعد
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    reason = db.Column(db.Text, nullable=True)
    
    # حالة الموعد
    status = db.Column(db.String(20), default='مؤكد', nullable=False)
    
    # علاقات
    patient = db.relationship('User', backref=db.backref('appointments', lazy=True))
    doctor = db.relationship('Doctor', 
                              back_populates='appointments', 
                              overlaps="booked_doctor")
    
    def __repr__(self):
        return f'<Appointment {self.patient_name} with {self.doctor_name} on {self.date} at {self.time}>'

    @classmethod
    def advanced_conflict_check(cls, doctor_name, date, time, buffer_minutes=30):
        """
        تحقق متقدم من تعارض المواعيد مع هامش زمني
        """
        start_time = (datetime.combine(date, time) - timedelta(minutes=buffer_minutes)).time()
        end_time = (datetime.combine(date, time) + timedelta(minutes=buffer_minutes)).time()
        
        conflicting_appointments = cls.query.filter(
            cls.doctor_name == doctor_name,
            cls.date == date,
            cls.time.between(start_time, end_time)
        ).all()
        
        return conflicting_appointments
    
    
    @classmethod
    def validate_appointment(cls, doctor, patient, date, time):
        """
        التحقق الشامل من صحة الموعد
        """
        checks = [
            # التحقق من توفر الطبيب
        cls.is_doctor_available(doctor, date, time),
        
        # التحقق من عدم وجود تعارضات
            cls.check_appointment_conflict(doctor.name, date, time),
            
            # التحقق من جدول عمل الطبيب
            cls.is_within_working_hours(doctor, time)
        ]
        
        return all(checks)
    @classmethod
    def validate_appointment_constraints(cls, doctor, patient, date, time):
        """
        التحقق الشامل من قيود المواعيد
        - منع الحجز المكرر خلال 24 ساعة
        - التحقق من جدول عمل الطبيب
        - التأكد من عدم وجود تعارضات زمنية
        """
        # التحقق من المواعيد السابقة خلال 24 ساعة
        current_datetime = datetime.combine(date, time)
        recent_appointments = cls.query.filter(
            cls.doctor_name == doctor.name,
            cls.patient_phone == patient.phone,
            cls.date.between(
                (current_datetime - timedelta(hours=24)).date(), 
                (current_datetime + timedelta(hours=24)).date()
            )
        ).all()
    
        if recent_appointments:
            last_appointment = max(recent_appointments, key=lambda x: datetime.combine(x.date, x.time))
            time_since_last_appointment = current_datetime - datetime.combine(last_appointment.date, last_appointment.time)
            
            if abs(time_since_last_appointment.total_seconds()) < 24 * 3600:  # Less than 24 hours
                logger.warning(f"Appointment conflict for patient {patient.phone} with doctor {doctor.name}. Last appointment was {last_appointment}")
                return False
    
        # التحقق من جدول عمل الطبيب
        work_days = doctor.work_days.split(',')
        if date.strftime('%A') not in work_days:
            return False
    
        # التحقق من ساعات العمل
        work_hours = doctor.work_hours.split('-')
        start_time = datetime.strptime(work_hours[0], '%H:%M').time()
        end_time = datetime.strptime(work_hours[1], '%H:%M').time()
    
        if not (start_time <= time <= end_time):
            return False
    
        return True
    
    @classmethod
    def delete_old_appointments(cls):
        """
        حذف المواعيد التي مر عليها يوم كامل
        """
        try:
            # حساب التاريخ السابق
            yesterday = datetime.now().date() - timedelta(days=1)
            
            # البحث عن المواعيد القديمة
            old_appointments = cls.query.filter(
                cls.date < yesterday
            ).all()
            
            # عدد المواعيد القديمة
            appointments_count = len(old_appointments)
            
            # حذف المواعيد
            for appointment in old_appointments:
                db.session.delete(appointment)
            
            # حفظ التغييرات
            db.session.commit()
            
            # تسجيل عملية الحذف
            logger.info(f"تم حذف {appointments_count} موعد قديم")
            
            return appointments_count
        
        except Exception as e:
            # التعامل مع الأخطاء المحتملة
            logger.error(f"خطأ في حذف المواعيد القديمة: {e}")
            db.session.rollback()
            return 0

class AppointmentModification(db.Model):
    __tablename__ = 'appointment_modifications'
    
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    old_date = db.Column(db.Date, nullable=False)
    old_time = db.Column(db.Time, nullable=False)
    new_date = db.Column(db.Date, nullable=False)
    new_time = db.Column(db.Time, nullable=False)
    reason = db.Column(db.Text, nullable=True)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

class AppointmentCancellation(db.Model):
    __tablename__ = 'appointment_cancellations'
    
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    doctor_name = db.Column(db.String(100), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    cancelled_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# دالة لترحيل قاعدة البيانات
def migrate_db(app):
    """إنشاء جداول قاعدة البيانات"""
    with app.app_context():
        # استيراد SQLAlchemy
        from sqlalchemy import Column, String
        from sqlalchemy.exc import OperationalError
        
        try:
            # محاولة إضافة العمود المفقود
            inspector = inspect(db.engine)
            columns = inspector.get_columns('users')
            column_names = [column['name'] for column in columns]
            
            # إذا لم يكن العمود موجودًا، أضفه
            if 'phone' not in column_names:
                with db.engine.connect() as connection:
                    connection.execute('ALTER TABLE users ADD COLUMN phone VARCHAR(20)')
                
                db.session.commit()
                print("تمت إضافة عمود الهاتف بنجاح")
        
        except Exception as e:
            print(f"حدث خطأ أثناء الترحيل: {e}")
# تصدير كائنات محددة بشكل صريح
database = db
