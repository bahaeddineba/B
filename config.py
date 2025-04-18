# config.py
import os
from dotenv import load_dotenv

# تحميل المتغيرات البيئية من .env
load_dotenv(dotenv_path='ai.env', override=True)

class Config:
    # إعدادات التطبيق العامة
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24)
    DEBUG = False
    TESTING = False

    # إعدادات قاعدة البيانات
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///medical_assistant.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # إعدادات البريد الإلكتروني
    EMAIL_SENDER = os.environ.get('EMAIL_SENDER')
    EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')

    # مفاتيح API
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # إعدادات الأمان
    SSL_REDIRECT = True
    MASTER_PASSWORD_HASH = os.environ.get('MASTER_PASSWORD_HASH')

    # إعدادات إعادة تعيين كلمة المرور
    PASSWORD_RESET_SALT = os.environ.get('PASSWORD_RESET_SALT') or os.urandom(16)
    PASSWORD_RESET_EXPIRATION = 3600  # رابط إعادة التعيين صالح لمدة ساعة واحدة

class DevelopmentConfig(Config):
    DEBUG = True
    SSL_REDIRECT = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

# اختيار التكوين المناسب
def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    if env == 'production':
        return ProductionConfig
    elif env == 'testing':
        return TestingConfig
    else:
        return DevelopmentConfig