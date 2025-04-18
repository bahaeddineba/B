# key_manager.py
import os
import base64
import secrets
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class KeyManager:
    @staticmethod
    def generate_salt():
        """توليد ملح عشوائي آمن."""
        return secrets.token_bytes(16)

    @staticmethod
    def derive_key(password: str, salt: bytes) -> bytes:
        """
        استخراج مفتاح تشفير آمن من كلمة المرور.
        
        المعاملات:
            password (str): كلمة المرور الرئيسية
            salt (bytes): الملح التشفيري
        
        الإرجاع:
            bytes: مفتاح التشفير المستخرج
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    @staticmethod
    def encrypt_key(key: str, master_password: str) -> dict:
        """
        تشفير مفتاح حساس باستخدام كلمة المرور الرئيسية.
        
        المعاملات:
            key (str): المفتاح المراد تشفيره
            master_password (str): كلمة المرور الرئيسية للتشفير
        
        الإرجاع:
            dict: تفاصيل المفتاح المشفر مع الملح والقيمة المشفرة
        """
        salt = KeyManager.generate_salt()
        derived_key = KeyManager.derive_key(master_password, salt)
        f = Fernet(derived_key)
        encrypted_key = f.encrypt(key.encode())
        
        return {
            'salt': base64.urlsafe_b64encode(salt).decode(),
            'encrypted_key': base64.urlsafe_b64encode(encrypted_key).decode()
        }

    @staticmethod
    def decrypt_key(encrypted_data: dict, master_password: str) -> str:
        """
        فك تشفير مفتاح مشفر مسبقًا.
        
        المعاملات:
            encrypted_data (dict): قاموس يحتوي على الملح والمفتاح المشفر
            master_password (str): كلمة المرور الرئيسية لفك التشفير
        
        الإرجاع:
            str: المفتاح المفك
        """
        salt = base64.urlsafe_b64decode(encrypted_data['salt'])
        encrypted_key = base64.urlsafe_b64decode(encrypted_data['encrypted_key'])
        
        derived_key = KeyManager.derive_key(master_password, salt)
        f = Fernet(derived_key)
        
        return f.decrypt(encrypted_key).decode()

    @staticmethod
    def save_encrypted_key(key_name: str, encrypted_data: dict, storage_path: str = '.keys'):
        """
        حفظ المفتاح المشفر في موقع تخزين آمن.
        
        المعاملات:
            key_name (str): اسم المفتاح
            encrypted_data (dict): بيانات المفتاح المشفر
            storage_path (str, optional): المسار لتخزين المفاتيح المشفرة
        """
        os.makedirs(storage_path, exist_ok=True)
        with open(os.path.join(storage_path, f'{key_name}.key'), 'w') as f:
            f.write(f"{encrypted_data['salt']}\n{encrypted_data['encrypted_key']}")

    @staticmethod
    def load_encrypted_key(key_name: str, storage_path: str = '.keys') -> dict:
        """
        تحميل مفتاح مشفر من التخزين الآمن.
        
        المعاملات:
            key_name (str): اسم المفتاح
            storage_path (str, optional): المسار للمفاتيح المخزنة
        
        الإرجاع:
            dict: بيانات المفتاح المشفر
        """
        with open(os.path.join(storage_path, f'{key_name}.key'), 'r') as f:
            salt, encrypted_key = f.read().strip().split('\n')
        
        return {
            'salt': salt,
            'encrypted_key': encrypted_key
        }