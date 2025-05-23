from flask import Flask, request, jsonify, send_file, render_template, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import datetime
import hashlib
import uuid
import json
import shutil
import re
import ssl
from threading import Thread
import time
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads/firmwares'
app.config['DATA_FOLDER'] = 'data'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max upload

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DATA_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['DATA_FOLDER'], 'users'), exist_ok=True)
os.makedirs(os.path.join(app.config['DATA_FOLDER'], 'devices'), exist_ok=True)
os.makedirs(os.path.join(app.config['DATA_FOLDER'], 'firmwares'), exist_ok=True)

# 用户模型
class User(UserMixin):
    def __init__(self, id, username, password, company_name, email, phone, status='pending', 
                 created_at=None, updated_at=None, is_admin=False, visible_model_numbers=None):
        self.id = id
        self.username = username
        self.password = password
        self.company_name = company_name
        self.email = email
        self.phone = phone
        self.status = status
        
        if isinstance(created_at, str):
            try:
                self.created_at = datetime.datetime.fromisoformat(created_at)
            except ValueError:
                self.created_at = datetime.datetime.utcnow() 
        elif created_at is None:
            self.created_at = datetime.datetime.utcnow()
        else: 
            self.created_at = created_at

        if isinstance(updated_at, str):
            try:
                self.updated_at = datetime.datetime.fromisoformat(updated_at)
            except ValueError:
                self.updated_at = datetime.datetime.utcnow()
        elif updated_at is None:
            self.updated_at = datetime.datetime.utcnow()
        else: 
            self.updated_at = updated_at
            
        self.is_admin = is_admin
        self.visible_model_numbers = visible_model_numbers or []
        
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'password': self.password,
            'company_name': self.company_name,
            'email': self.email,
            'phone': self.phone,
            'status': self.status,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime.datetime) else self.created_at,
            'updated_at': self.updated_at.isoformat() if isinstance(self.updated_at, datetime.datetime) else self.updated_at,
            'is_admin': self.is_admin,
            'visible_model_numbers': self.visible_model_numbers
        }
    
    @classmethod
    def from_dict(cls, data):
        created_at_val = data.get('created_at')
        if isinstance(created_at_val, str):
            try:
                created_at_obj = datetime.datetime.fromisoformat(created_at_val)
            except ValueError: 
                created_at_obj = None 
        elif isinstance(created_at_val, datetime.datetime):
            created_at_obj = created_at_val
        else:
            created_at_obj = None

        updated_at_val = data.get('updated_at')
        if isinstance(updated_at_val, str):
            try:
                updated_at_obj = datetime.datetime.fromisoformat(updated_at_val)
            except ValueError:
                updated_at_obj = None
        elif isinstance(updated_at_val, datetime.datetime):
            updated_at_obj = updated_at_val
        else:
            updated_at_obj = None
            
        return cls(
            id=data['id'],
            username=data['username'],
            password=data['password'],
            company_name=data['company_name'],
            email=data['email'],
            phone=data['phone'],
            status=data['status'],
            created_at=created_at_obj,
            updated_at=updated_at_obj,
            is_admin=data['is_admin'],
            visible_model_numbers=data.get('visible_model_numbers', [])
        )
    
    @classmethod
    def get(cls, user_id):
        user_file = os.path.join(app.config['DATA_FOLDER'], 'users', f"{user_id}.json")
        if os.path.exists(user_file):
            with open(user_file, 'r') as f:
                return cls.from_dict(json.load(f))
        return None
    
    @classmethod
    def get_by_username(cls, username):
        users_dir = os.path.join(app.config['DATA_FOLDER'], 'users')
        for filename in os.listdir(users_dir):
            if filename.endswith('.json'):
                with open(os.path.join(users_dir, filename), 'r') as f:
                    data = json.load(f)
                    if data['username'] == username:
                        return cls.from_dict(data)
        return None
    
    @classmethod
    def get_all(cls):
        users = []
        users_dir = os.path.join(app.config['DATA_FOLDER'], 'users')
        for filename in os.listdir(users_dir):
            if filename.endswith('.json'):
                with open(os.path.join(users_dir, filename), 'r') as f:
                    users.append(cls.from_dict(json.load(f)))
        return users
    
    def save(self):
        self.updated_at = datetime.datetime.utcnow()
        user_file = os.path.join(app.config['DATA_FOLDER'], 'users', f"{self.id}.json")
        with open(user_file, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def get_devices(self):
        devices = []
        devices_dir = os.path.join(app.config['DATA_FOLDER'], 'devices')
        for filename in os.listdir(devices_dir):
            if filename.endswith('.json'):
                with open(os.path.join(devices_dir, filename), 'r') as f:
                    data = json.load(f)
                    if data['user_id'] == self.id:
                        devices.append(Device.from_dict(data))
        return devices
    
    def get_firmwares(self):
        firmwares = []
        firmwares_dir = os.path.join(app.config['DATA_FOLDER'], 'firmwares')
        for filename in os.listdir(firmwares_dir):
            if filename.endswith('.json'):
                with open(os.path.join(firmwares_dir, filename), 'r') as f:
                    data = json.load(f)
                    if data['user_id'] == self.id:
                        firmwares.append(Firmware.from_dict(data))
        return firmwares

# 设备模型
class Device:
    def __init__(self, id, model_number, model_name, description, user_id, 
                 created_at=None, updated_at=None):
        self.id = id
        self.model_number = model_number
        self.model_name = model_name
        self.description = description
        self.user_id = user_id
        
        if isinstance(created_at, str):
            try:
                self.created_at = datetime.datetime.fromisoformat(created_at)
            except ValueError:
                self.created_at = datetime.datetime.utcnow()
        elif created_at is None:
            self.created_at = datetime.datetime.utcnow()
        else:
            self.created_at = created_at

        if isinstance(updated_at, str):
            try:
                self.updated_at = datetime.datetime.fromisoformat(updated_at)
            except ValueError:
                self.updated_at = datetime.datetime.utcnow()
        elif updated_at is None:
            self.updated_at = datetime.datetime.utcnow()
        else:
            self.updated_at = updated_at
    
    def to_dict(self):
        return {
            'id': self.id,
            'model_number': self.model_number,
            'model_name': self.model_name,
            'description': self.description,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime.datetime) else self.created_at,
            'updated_at': self.updated_at.isoformat() if isinstance(self.updated_at, datetime.datetime) else self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data):
        created_at_val = data.get('created_at')
        if isinstance(created_at_val, str):
            try:
                created_at_obj = datetime.datetime.fromisoformat(created_at_val)
            except ValueError: created_at_obj = None
        elif isinstance(created_at_val, datetime.datetime): created_at_obj = created_at_val
        else: created_at_obj = None

        updated_at_val = data.get('updated_at')
        if isinstance(updated_at_val, str):
            try:
                updated_at_obj = datetime.datetime.fromisoformat(updated_at_val)
            except ValueError: updated_at_obj = None
        elif isinstance(updated_at_val, datetime.datetime): updated_at_obj = updated_at_val
        else: updated_at_obj = None
            
        return cls(
            id=data['id'],
            model_number=data['model_number'],
            model_name=data['model_name'],
            description=data['description'],
            user_id=data['user_id'],
            created_at=created_at_obj,
            updated_at=updated_at_obj
        )
    
    @classmethod
    def get(cls, device_id):
        device_file = os.path.join(app.config['DATA_FOLDER'], 'devices', f"{device_id}.json")
        if os.path.exists(device_file):
            with open(device_file, 'r') as f:
                return cls.from_dict(json.load(f))
        return None
    
    @classmethod
    def get_by_model_number(cls, model_number, user_id=None):
        devices_dir = os.path.join(app.config['DATA_FOLDER'], 'devices')
        for filename in os.listdir(devices_dir):
            if filename.endswith('.json'):
                with open(os.path.join(devices_dir, filename), 'r') as f:
                    data = json.load(f)
                    if data['model_number'] == model_number:
                        if user_id is None or data['user_id'] == user_id:
                            return cls.from_dict(data)
        return None
    
    @classmethod
    def get_all(cls, user_id=None):
        devices = []
        devices_dir = os.path.join(app.config['DATA_FOLDER'], 'devices')
        for filename in os.listdir(devices_dir):
            if filename.endswith('.json'):
                with open(os.path.join(devices_dir, filename), 'r') as f:
                    data = json.load(f)
                    if user_id is None or data['user_id'] == user_id:
                        devices.append(cls.from_dict(data))
        return devices
    
    def save(self):
        self.updated_at = datetime.datetime.utcnow()
        device_file = os.path.join(app.config['DATA_FOLDER'], 'devices', f"{self.id}.json")
        with open(device_file, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def get_firmwares(self):
        firmwares = []
        firmwares_dir = os.path.join(app.config['DATA_FOLDER'], 'firmwares')
        for filename in os.listdir(firmwares_dir):
            if filename.endswith('.json'):
                with open(os.path.join(firmwares_dir, filename), 'r') as f:
                    data = json.load(f)
                    if data['device_id'] == self.id:
                        firmwares.append(Firmware.from_dict(data))
        return firmwares

# 固件模型
class Firmware:
    def __init__(self, id, version, device_id, file_path, file_size, crc_checksum, 
                 description, is_wifi_firmware, is_device_firmware, status, user_id, 
                 created_at=None, compatible_versions=None):
        self.id = id
        self.version = version
        self.device_id = device_id
        self.file_path = file_path
        self.file_size = file_size
        self.crc_checksum = crc_checksum
        self.description = description
        self.is_wifi_firmware = is_wifi_firmware
        self.is_device_firmware = is_device_firmware
        self.status = status
        self.user_id = user_id
        
        if isinstance(created_at, str):
            try:
                self.created_at = datetime.datetime.fromisoformat(created_at)
            except ValueError:
                self.created_at = datetime.datetime.utcnow()
        elif created_at is None:
            self.created_at = datetime.datetime.utcnow()
        else:
            self.created_at = created_at
            
        self.compatible_versions = compatible_versions or []
    
    def to_dict(self):
        return {
            'id': self.id,
            'version': self.version,
            'device_id': self.device_id,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'crc_checksum': self.crc_checksum,
            'description': self.description,
            'is_wifi_firmware': self.is_wifi_firmware,
            'is_device_firmware': self.is_device_firmware,
            'status': self.status,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime.datetime) else self.created_at,
            'compatible_versions': self.compatible_versions
        }
    
    @classmethod
    def from_dict(cls, data):
        created_at_val = data.get('created_at')
        if isinstance(created_at_val, str):
            try:
                created_at_obj = datetime.datetime.fromisoformat(created_at_val)
            except ValueError: created_at_obj = None
        elif isinstance(created_at_val, datetime.datetime): created_at_obj = created_at_val
        else: created_at_obj = None
            
        return cls(
            id=data['id'],
            version=data['version'],
            device_id=data['device_id'],
            file_path=data['file_path'],
            file_size=data['file_size'],
            crc_checksum=data['crc_checksum'],
            description=data['description'],
            is_wifi_firmware=data['is_wifi_firmware'],
            is_device_firmware=data['is_device_firmware'],
            status=data['status'],
            user_id=data['user_id'],
            created_at=created_at_obj,
            compatible_versions=data.get('compatible_versions', [])
        )
    
    @classmethod
    def get(cls, firmware_id):
        firmware_file = os.path.join(app.config['DATA_FOLDER'], 'firmwares', f"{firmware_id}.json")
        if os.path.exists(firmware_file):
            with open(firmware_file, 'r') as f:
                return cls.from_dict(json.load(f))
        return None
    
    @classmethod
    def get_all(cls, device_id=None, user_id=None):
        firmwares = []
        firmwares_dir = os.path.join(app.config['DATA_FOLDER'], 'firmwares')
        for filename in os.listdir(firmwares_dir):
            if filename.endswith('.json'):
                with open(os.path.join(firmwares_dir, filename), 'r') as f:
                    data = json.load(f)
                    if (device_id is None or data['device_id'] == device_id) and \
                       (user_id is None or data['user_id'] == user_id):
                        firmwares.append(cls.from_dict(data))
        return firmwares
    
    @classmethod
    def find_compatible(cls, device_id, current_version, is_wifi, is_device, getlatest=False):
        firmwares = []
        firmwares_dir = os.path.join(app.config['DATA_FOLDER'], 'firmwares')
        for filename in os.listdir(firmwares_dir):
            if filename.endswith('.json'):
                with open(os.path.join(firmwares_dir, filename), 'r') as f:
                    data = json.load(f)
                    if data['device_id'] == device_id and \
                       data['is_wifi_firmware'] == is_wifi and \
                       data['is_device_firmware'] == is_device and \
                       data['status'] == 'active' and \
                       current_version in data.get('compatible_versions', []) or getlatest:
                        
                        firmwares.append(cls.from_dict(data))
        
        # 按创建时间排序，返回最新的
        if firmwares:
            return sorted(firmwares, key=lambda x: x.created_at, reverse=True)[0]
        return None
    
    def save(self):
        firmware_file = os.path.join(app.config['DATA_FOLDER'], 'firmwares', f"{self.id}.json")
        with open(firmware_file, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

# 生成唯一ID
def generate_id():
    return str(uuid.uuid4())

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# 计算文件CRC16校验和 (修改为匹配特定C++实现的逻辑)

# 从C++代码复制的查找表
auchCRCHi = (
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81,
    0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0,
    0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01,
    0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81,
    0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0,
    0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01,
    0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81,
    0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0,
    0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01,
    0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81,
    0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0,
    0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01,
    0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
    0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81,
    0x40
)

auchCRCLo = (
    0x00, 0xC0, 0xC1, 0x01, 0xC3, 0x03, 0x02, 0xC2, 0xC6, 0x06, 0x07, 0xC7, 0x05, 0xC5, 0xC4,
    0x04, 0xCC, 0x0C, 0x0D, 0xCD, 0x0F, 0xCF, 0xCE, 0x0E, 0x0A, 0xCA, 0xCB, 0x0B, 0xC9, 0x09,
    0x08, 0xC8, 0xD8, 0x18, 0x19, 0xD9, 0x1B, 0xDB, 0xDA, 0x1A, 0x1E, 0xDE, 0xDF, 0x1F, 0xDD,
    0x1D, 0x1C, 0xDC, 0x14, 0xD4, 0xD5, 0x15, 0xD7, 0x17, 0x16, 0xD6, 0xD2, 0x12, 0x13, 0xD3,
    0x11, 0xD1, 0xD0, 0x10, 0xF0, 0x30, 0x31, 0xF1, 0x33, 0xF3, 0xF2, 0x32, 0x36, 0xF6, 0xF7,
    0x37, 0xF5, 0x35, 0x34, 0xF4, 0x3C, 0xFC, 0xFD, 0x3D, 0xFF, 0x3F, 0x3E, 0xFE, 0xFA, 0x3A,
    0x3B, 0xFB, 0x39, 0xF9, 0xF8, 0x38, 0x28, 0xE8, 0xE9, 0x29, 0xEB, 0x2B, 0x2A, 0xEA, 0xEE,
    0x2E, 0x2F, 0xEF, 0x2D, 0xED, 0xEC, 0x2C, 0xE4, 0x24, 0x25, 0xE5, 0x27, 0xE7, 0xE6, 0x26,
    0x22, 0xE2, 0xE3, 0x23, 0xE1, 0x21, 0x20, 0xE0, 0xA0, 0x60, 0x61, 0xA1, 0x63, 0xA3, 0xA2,
    0x62, 0x66, 0xA6, 0xA7, 0x67, 0xA5, 0x65, 0x64, 0xA4, 0x6C, 0xAC, 0xAD, 0x6D, 0xAF, 0x6F,
    0x6E, 0xAE, 0xAA, 0x6A, 0x6B, 0xAB, 0x69, 0xA9, 0xA8, 0x68, 0x78, 0xB8, 0xB9, 0x79, 0xBB,
    0x7B, 0x7A, 0xBA, 0xBE, 0x7E, 0x7F, 0xBF, 0x7D, 0xBD, 0xBC, 0x7C, 0xB4, 0x74, 0x75, 0xB5,
    0x77, 0xB7, 0xB6, 0x76, 0x72, 0xB2, 0xB3, 0x73, 0xB1, 0x71, 0x70, 0xB0, 0x50, 0x90, 0x91,
    0x51, 0x93, 0x53, 0x52, 0x92, 0x96, 0x56, 0x57, 0x97, 0x55, 0x95, 0x94, 0x54, 0x9C, 0x5C,
    0x5D, 0x9D, 0x5F, 0x9F, 0x9E, 0x5E, 0x5A, 0x9A, 0x9B, 0x5B, 0x99, 0x59, 0x58, 0x98, 0x88,
    0x48, 0x49, 0x89, 0x4B, 0x8B, 0x8A, 0x4A, 0x4E, 0x8E, 0x8F, 0x4F, 0x8D, 0x4D, 0x4C, 0x8C,
    0x44, 0x84, 0x85, 0x45, 0x87, 0x47, 0x46, 0x86, 0x82, 0x42, 0x43, 0x83, 0x41, 0x81, 0x80,
    0x40
)

def calculate_crc_modbus(file_path):
    uchCRCHi = 0xFF # 初始化 CRC 高位
    uchCRCLo = 0xFF # 初始化 CRC 低位

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            for byte in chunk:
                # 模拟 C++ 中的 Updata 逻辑
                uindex = uchCRCHi ^ byte
                new_uchCRCHi = uchCRCLo ^ auchCRCHi[uindex]
                new_uchCRCLo = auchCRCLo[uindex]
                uchCRCHi = new_uchCRCHi
                uchCRCLo = new_uchCRCLo

    # 模拟 C++ 中的 Get 逻辑
    crc = uchCRCLo + (uchCRCHi << 8)
    return crc

# 添加模板全局函数
@app.template_global()
def get_device(device_id):
    return Device.get(device_id)

@app.template_global()
def get_user(user_id):
    return User.get(user_id)

# 路由: 首页
@app.route('/')
def index():
    return render_template('index.html')

# 路由: 用户注册
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        company_name = request.form.get('company_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        
        user_exists = User.get_by_username(username)
        if user_exists:
            flash('用户名已存在')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        new_user = User(
            id=generate_id(),
            username=username,
            password=hashed_password,
            company_name=company_name,
            email=email,
            phone=phone
        )
        
        new_user.save()
        
        flash('注册成功，请等待管理员审核')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# 路由: 用户登录
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.get_by_username(username)
        
        if not user or not check_password_hash(user.password, password):
            flash('用户名或密码错误')
            return redirect(url_for('login'))
        
        if user.status != 'approved' and not user.is_admin:
            flash('您的账户尚未获得批准')
            return redirect(url_for('login'))
        
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('login.html')

# 路由: 用户登出
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# 路由: 用户控制面板
@app.route('/dashboard')
@login_required
def dashboard():
    devices_to_display = []
    all_system_devices = Device.get_all() 
    if current_user.is_admin:
        devices_to_display = all_system_devices
    else:
        user_visible_models = current_user.visible_model_numbers
        if user_visible_models: 
            devices_to_display = [d for d in all_system_devices if d.model_number in user_visible_models]
    return render_template('dashboard.html', devices=devices_to_display)

# 路由: 设备管理
@app.route('/devices', methods=['GET'])
@login_required
def list_devices():
    devices_to_display = []
    all_system_devices = Device.get_all()
    if current_user.is_admin:
        devices_to_display = all_system_devices
    else:
        user_visible_models = current_user.visible_model_numbers
        if user_visible_models:
            devices_to_display = [d for d in all_system_devices if d.model_number in user_visible_models]
            
    return render_template('devices.html', devices=devices_to_display)

# 路由: 添加设备
@app.route('/devices/add', methods=['GET', 'POST'])
@login_required
def add_device():
    if not current_user.is_admin:
        flash('您没有权限执行此操作。')
        return redirect(url_for('list_devices'))

    if request.method == 'POST':
        model_number = request.form.get('model_number')
        model_name = request.form.get('model_name')
        description = request.form.get('description')
        
        device_exists = Device.get_by_model_number(model_number, user_id=current_user.id)
        if device_exists:
            flash('该型号已存在')
            return redirect(url_for('add_device'))
        
        new_device = Device(
            id=generate_id(),
            model_number=model_number,
            model_name=model_name,
            description=description,
            user_id=current_user.id
        )
        
        new_device.save()
        
        flash('设备添加成功')
        return redirect(url_for('list_devices'))
    
    return render_template('add_device.html')

# 路由: 固件管理
@app.route('/firmwares', methods=['GET'])
@login_required
def list_firmwares():
    device_id_param = request.args.get('device_id')
    target_device_instance = None
    firmwares_to_display = []
    
    all_system_devices = Device.get_all() 

    if device_id_param:
        target_device_instance = next((d for d in all_system_devices if d.id == device_id_param), None)
        if not target_device_instance:
            flash('设备未找到。')
            return redirect(url_for('list_devices'))

        is_authorized = False
        if current_user.is_admin:
            is_authorized = True
        elif target_device_instance.model_number in current_user.visible_model_numbers:
            is_authorized = True

        if not is_authorized:
            flash('您无权查看此设备的固件。')
            return redirect(url_for('list_devices'))
        
        firmwares_to_display = Firmware.get_all(device_id=device_id_param)
        return render_template('firmwares.html', firmwares=firmwares_to_display, device=target_device_instance)
    else:
        # Listing all firmwares across all visible devices for a user, or all for admin
        if current_user.is_admin:
            authorized_devices_instances = all_system_devices
            firmwares_to_display = Firmware.get_all() 
            devices_map = {dev.id: dev for dev in authorized_devices_instances}
            return render_template('firmwares.html', firmwares=firmwares_to_display, all_devices_map=devices_map, view_all=True)
        else: 
            user_visible_models = current_user.visible_model_numbers
            if not user_visible_models:
                flash('您当前没有被授权访问任何设备的固件。')
                return render_template('firmwares.html', firmwares=[], device=None, view_all=True)

            authorized_devices_instances = [d for d in all_system_devices if d.model_number in user_visible_models]
            
            if not authorized_devices_instances:
                 flash('没有找到您有权限访问的设备型号的固件。')
                 return render_template('firmwares.html', firmwares=[], device=None, view_all=True)

            authorized_device_ids = [d.id for d in authorized_devices_instances]
            for dev_id in authorized_device_ids:
                firmwares_for_device = Firmware.get_all(device_id=dev_id)
                firmwares_to_display.extend(firmwares_for_device)
            
            devices_map = {dev.id: dev for dev in authorized_devices_instances}
            return render_template('firmwares.html', firmwares=firmwares_to_display, visible_devices_map=devices_map, view_all=True)

# 验证版本格式是否符合 x.x.x
def validate_version_format(version):
    return version.isdigit()

def validate_wifiversion_format(version):
    pattern = r'^\d+\.\d+\.\d+$'
    return re.match(pattern, version) is not None

# 路由: 上传固件
@app.route('/firmwares/upload', methods=['GET', 'POST'])
@login_required
def upload_firmware():
    devices_for_form = []
    all_system_devices = Device.get_all()
    if current_user.is_admin:
        devices_for_form = all_system_devices
    else:
        user_visible_models = current_user.visible_model_numbers
        if user_visible_models:
            devices_for_form = [d for d in all_system_devices if d.model_number in user_visible_models]

    if request.method == 'POST':
        device_id = request.form.get('device_id')
        version = request.form.get('version')
        description = request.form.get('description')
        firmware_type = request.form.get('firmware_type')
        compatible_versions_selected = request.form.getlist('compatible_versions')
        manual_compatible_version_input = request.form.get('manual_compatible_version', '').strip()
        
        # 验证版本格式
        if not validate_version_format(version):
            flash('版本格式必须为 x.x.x（如 1.0.0）')
            return redirect(request.url)
        
        # 验证选中兼容版本格式
        for cv in compatible_versions_selected:
            if not validate_version_format(cv):
                flash(f'选中的兼容版本 {cv} 格式不正确')
                return redirect(request.url)
        
        # 处理手动输入的兼容版本 (如果提供了)
        manual_versions = []
        if manual_compatible_version_input:
            # Split by semicolon and remove empty strings
            potential_versions = [v.strip() for v in manual_compatible_version_input.split(';') if v.strip()]
            for mv in potential_versions:
                if not validate_version_format(mv):
                    flash(f'手动输入的兼容版本 {mv} 格式不正确，必须为 x.x.x')
                    return redirect(request.url)
                manual_versions.append(mv)
        
        if 'firmware_file' not in request.files:
            flash('没有选择文件')
            return render_template('upload_firmware.html', devices=devices_for_form)
        
        file_from_request = request.files['firmware_file']
        if file_from_request.filename == '':
            flash('没有选择文件')
            return render_template('upload_firmware.html', devices=devices_for_form)
        
        # 检查设备是否存在 and user authorization
        target_device_instance = next((d for d in all_system_devices if d.id == device_id), None)
        
        if not target_device_instance:
            flash('选择的设备不存在。')
            return render_template('upload_firmware.html', devices=devices_for_form)

        is_authorized_for_device_model = False
        if current_user.is_admin:
            is_authorized_for_device_model = True
        elif target_device_instance.model_number in current_user.visible_model_numbers:
            is_authorized_for_device_model = True

        if not is_authorized_for_device_model:
            flash('您无权为此设备的型号上传固件。')
            return render_template('upload_firmware.html', devices=devices_for_form)
        
        # 检查版本是否已存在
        is_wifi = firmware_type == 'wifi'
        is_device = firmware_type == 'device'
        
        # 检查是否已存在相同版本的固件
        existing_firmwares = Firmware.get_all(device_id=device_id)
        for firmware in existing_firmwares:
            if firmware.version == version and firmware.is_wifi_firmware == is_wifi and firmware.is_device_firmware == is_device:
                flash('该版本固件已存在')
                return redirect(url_for('upload_firmware'))
        
        # 验证兼容版本是否存在于该设备的固件中 (只验证选中的)
        # 注意: 我们不再验证手动输入的版本是否已存在, 允许手动输入任何格式正确的版本
        valid_compatible_versions = []
        for cv in compatible_versions_selected:
            for ef in existing_firmwares:
                if ef.version == cv and ef.is_wifi_firmware == is_wifi and ef.is_device_firmware == is_device:
                    if cv not in valid_compatible_versions: # Ensure uniqueness from selection
                         valid_compatible_versions.append(cv)
                    break # Found this version, move to next selected one
        
        # 添加手动输入的有效兼容版本 (如果提供了且不在列表中)
        # Combine selected and manual versions, ensuring uniqueness
        combined_compatible_versions = list(set(valid_compatible_versions + manual_versions))
        
        # 保存文件
        filename = secure_filename(f"{target_device_instance.model_number}_{firmware_type}_{version}_{uuid.uuid4()}.bin")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        file_from_request.save(file_path)
        
        # 计算CRC校验和
        crc = calculate_crc_modbus(file_path)
        
        # 创建固件记录
        new_firmware = Firmware(
            id=generate_id(),
            version=version,
            device_id=device_id,
            file_path=file_path,
            file_size=os.path.getsize(file_path),
            crc_checksum=crc,
            description=description,
            is_wifi_firmware=is_wifi,
            is_device_firmware=is_device,
            status='active',
            user_id=current_user.id,
            compatible_versions=combined_compatible_versions
        )
        
        new_firmware.save()
        app.logger.info(f"User {current_user.username} uploaded firmware {version} for device {target_device_instance.model_number} ({device_id})")
        
        flash('固件上传成功')
        return redirect(url_for('list_firmwares', device_id=device_id))
    
    # GET request
    if not devices_for_form and not current_user.is_admin:
        flash("您当前没有被授权管理任何设备的固件，无法上传。")
    return render_template('upload_firmware.html', devices=devices_for_form)

# API: 固件查询
@app.route('/firmware/check', methods=['POST'])
def check_firmware():
    print("check_firmware")
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    print(data)
    
    model_number = data.get('device_model')
    device_version = data.get('device_version')
    wifi_version = data.get('wifi_version')
    
    if not model_number or not device_version or not wifi_version:
        print("Missing required fields")
        return jsonify({'error': 'Missing required fields'}), 400
    
    # 验证版本格式
    if not validate_version_format(device_version):
        print("Invalid device version format, must be x.x.x")
        return jsonify({'error': 'Invalid device version format, must be x.x.x'}), 400
    
    if not validate_wifiversion_format(wifi_version):
        print("Invalid WiFi version format, must be x.x.x")
        return jsonify({'error': 'Invalid WiFi version format, must be x.x.x'}), 400
    
    # 查找设备
    device = Device.get_by_model_number(model_number)
    if not device:
        print("Device not found")
        return jsonify({'error': 'Device not found'}), 404
    
    # 构建响应
    response = {
        "status": "success",
        "message": "Firmware check completed",
        "device": None,
        "wifi": None
    }
    
    # 检查设备固件更新
    device_firmware = Firmware.find_compatible(
        device_id=device.id,
        current_version=device_version,
        is_wifi=False,
        is_device=True
    )
    
    if device_firmware:
        base_url = request.host.split(':')[0]  # 获取主机地址，去掉可能存在的端口
        download_url = f"http://{base_url}:3000/firmware/download/{device_firmware.id}"
        response["device"] = {
            "current_version": device_version,
            "latest_version": device_firmware.version,
            "upgradable": True,
            "download_url": download_url,
            "crc16": device_firmware.crc_checksum,
            "notes": device_firmware.description
        }
    else:
        response["device"] = {
            "current_version": device_version,
            "latest_version": device_version,
            "upgradable": False,
            "download_url": None,
            "crc16": None,
            "notes": None
        }
    
    # 检查WiFi固件更新
    wifi_device = Device.get_by_model_number('wifi')    
    if not wifi_device:
        return jsonify({'error': 'WiFi device not found'}), 404
    
    wifi_firmware = Firmware.find_compatible(
        device_id=wifi_device.id,
        current_version=wifi_version,
        is_wifi=True,
        is_device=False
        # getlatest=True
    )
    
    if wifi_firmware:
        base_url = request.host.split(':')[0]  # 获取主机地址，去掉可能存在的端口
        download_url = f"http://{base_url}:3000/firmware/download/{wifi_firmware.id}"
        response["wifi"] = {
            "current_version": wifi_version,
            "latest_version": wifi_firmware.version,
            "upgradable": True,
            "download_url": download_url,
            "crc16": wifi_firmware.crc_checksum,
            "notes": wifi_firmware.description
        }
    else:
        response["wifi"] = {
            "current_version": wifi_version,
            "latest_version": wifi_version,
            "upgradable": False,
            "download_url": None,
            "crc16": None,
            "notes": None
        }
    
    print(response)
    return jsonify(response)

# API: 固件下载
@app.route('/firmware/download/<firmware_id>', methods=['GET'])
def download_firmware(firmware_id):
    firmware = Firmware.get(firmware_id)
    if not firmware:
        return jsonify({'error': 'Firmware not found'}), 404
    
    # 添加下载日志
    print(f"Firmware download started: ID={firmware_id}, Version={firmware.version}, Size={firmware.file_size} bytes")
    
    # 获取设备信息用于日志
    device = Device.get(firmware.device_id)
    device_info = f"{device.model_number} ({device.model_name})" if device else "Unknown device"
    
    print(f"Download details: Device={device_info}, File={os.path.basename(firmware.file_path)}")
    
    # 确保文件存在并获取实际文件大小
    if not os.path.exists(firmware.file_path):
        print(f"Error: Firmware file not found at {firmware.file_path}")
        return jsonify({'error': 'Firmware file not found'}), 404
    
    actual_file_size = os.path.getsize(firmware.file_path)
    if actual_file_size != firmware.file_size:
        print(f"Warning: Stored file size ({firmware.file_size}) differs from actual file size ({actual_file_size})")
        # 更新固件记录中的文件大小
        firmware.file_size = actual_file_size
        firmware.save()
    
    print(f"Confirmed file size: {actual_file_size} bytes")
    
    # 创建一个生成器函数来流式传输文件并跟踪进度
    def generate_file():
        file_size = actual_file_size
        bytes_sent = 0
        chunk_size = 2048  # 8KB chunks
        last_percent = -1  # 设为-1确保第一次读取时会打印0%
        
        with open(firmware.file_path, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                    
                bytes_sent += len(data)
                percent = int((bytes_sent / file_size) * 100) if file_size > 0 else 100
                
                # 每1%打印一次进度
                if percent != last_percent:
                    print(f"Direct download progress: {percent}% ({bytes_sent}/{file_size} bytes)")
                    last_percent = percent
                    
                yield data
                time.sleep(0.03)
    
    # 使用流式响应
    filename = os.path.basename(firmware.file_path)
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Type': 'application/octet-stream',
        'Content-Length': str(actual_file_size),  # 添加Content-Length头
        'Connection': 'keep-alive',
        'keep-alive': 'timeout=5, max=1000'
    }
    
    return app.response_class(
        generate_file(),
        headers=headers,
        direct_passthrough=True
    )

# 新增: 固件分块下载API
@app.route('/api/firmware/download/chunk/<firmware_id>', methods=['GET'])
def download_firmware_chunk(firmware_id):
    firmware = Firmware.get(firmware_id)
    if not firmware:
        return jsonify({'error': 'Firmware not found'}), 404
    
    # 获取分块参数
    chunk_size = request.args.get('chunk_size', type=int, default=1024)
    chunk_index = request.args.get('chunk_index', type=int, default=0)
    client_progress = request.args.get('client_progress', type=float, default=0)
    
    # 验证参数
    if chunk_size <= 0 or chunk_index < 0:
        return jsonify({'error': 'Invalid chunk parameters'}), 400
    
    # 打开文件并读取指定块
    try:
        with open(firmware.file_path, 'rb') as f:
            f.seek(chunk_index * chunk_size)
            chunk_data = f.read(chunk_size)
            
            if not chunk_data:  # 如果没有数据，说明已经超出文件范围
                return jsonify({'error': 'Chunk index out of range'}), 400
            
            # 计算总块数
            total_chunks = (firmware.file_size + chunk_size - 1) // chunk_size
            
            # 使用客户端报告的进度，如果有的话
            progress_percent = client_progress if client_progress > 0 else min(100, round((chunk_index + 1) / total_chunks * 100, 2))
            
            # 打印下载进度日志
            if chunk_index == 0:
                # 首次请求，打印开始下载信息
                device = Device.get(firmware.device_id)
                device_info = f"{device.model_number} ({device.model_name})" if device else "Unknown device"
                print(f"Chunked download started: ID={firmware_id}, Version={firmware.version}, Device={device_info}")
                print(f"Total file size: {firmware.file_size} bytes, Total chunks: {total_chunks}")
            
            # 每5%打印一次进度，或者是第一个和最后一个块
            if chunk_index == 0 or chunk_index == total_chunks - 1 or int(progress_percent) % 5 == 0:
                bytes_downloaded = min(firmware.file_size, (chunk_index + 1) * chunk_size)
                print(f"Download progress: {progress_percent}% ({bytes_downloaded}/{firmware.file_size} bytes, chunk {chunk_index+1}/{total_chunks})")
            
            # 返回分块数据和元数据
            response = {
                'chunk_index': chunk_index,
                'total_chunks': total_chunks,
                'chunk_size': len(chunk_data),
                'data': chunk_data.hex(),  # 将二进制数据转换为十六进制字符串
                'progress': progress_percent,
                'file_size': firmware.file_size,
                'bytes_downloaded': min(firmware.file_size, (chunk_index + 1) * chunk_size)
            }
            
            return jsonify(response)
    except Exception as e:
        print(f"Error in chunk download: {str(e)}")
        return jsonify({'error': f'Error reading firmware file: {str(e)}'}), 500

# 新增: 固件版本列表API
@app.route('/firmware/versions/<string:model_number>', methods=['GET'])
def list_firmware_versions(model_number):
    firmware_type = request.args.get('firmware_type', 'device')
    
    # 查找设备
    device = Device.get_by_model_number(model_number)
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    
    # 确定固件类型
    is_wifi = firmware_type == 'wifi'
    is_device = firmware_type == 'device'
    
    # 查询所有活跃的固件版本
    firmwares = Firmware.get_all(device_id=device.id, user_id=device.user_id)
    
    # 构建版本列表
    versions = []
    for firmware in firmwares:
        # 获取兼容版本列表
        compatible_versions = [c.compatible_version for c in firmware.compatible_versions]
        
        versions.append({
            'version': firmware.version,
            'compatible_versions': compatible_versions,
            'release_date': firmware.created_at,
            'size': firmware.file_size,
            'crc': firmware.crc_checksum,
            'description': firmware.description
        })
    
    return jsonify({
        'model_number': model_number,
        'firmware_type': firmware_type,
        'versions': versions
    })

# 新增: 固件验证API
@app.route('/firmware/verify/<int:firmware_id>', methods=['POST'])
def verify_firmware(firmware_id):
    firmware = Firmware.get(firmware_id)
    if not firmware:
        return jsonify({'error': 'Firmware not found'}), 404
    
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    client_crc = data.get('crc')
    if not client_crc:
        return jsonify({'error': 'Missing CRC checksum'}), 400
    
    # 验证CRC校验和
    if client_crc.lower() == firmware.crc_checksum.lower():
        return jsonify({
            'verified': True,
            'message': 'Firmware verification successful'
        })
    else:
        return jsonify({
            'verified': False,
            'message': 'Firmware verification failed',
            'expected_crc': firmware.crc_checksum
        })

# 新增: 设备注册API
@app.route('/api/device/register', methods=['POST'])
def register_device():
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    model_number = data.get('model_number')
    serial_number = data.get('serial_number')
    firmware_version = data.get('firmware_version')
    
    if not model_number or not serial_number:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # 验证固件版本格式（如果提供）
    if firmware_version and not validate_version_format(firmware_version):
        return jsonify({'error': 'Invalid firmware version format, must be x.x.x'}), 400
    
    # 查找设备型号
    device_model = Device.get_by_model_number(model_number)
    if not device_model:
        return jsonify({'error': 'Device model not found'}), 404
    
    # 这里可以添加设备实例的注册逻辑
    # 例如，可以创建一个DeviceInstance表来跟踪单个设备
    
    return jsonify({
        'registered': True,
        'device_id': f"{model_number}_{serial_number}",
        'message': 'Device registered successfully'
    })

# 新增: 设备状态上报API
@app.route('/api/device/status', methods=['POST'])
def update_device_status():
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    model_number = data.get('model_number')
    serial_number = data.get('serial_number')
    status = data.get('status')
    
    if not model_number or not serial_number or not status:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # 这里可以添加设备状态更新逻辑
    # 例如，可以更新DeviceInstance表中的状态字段
    
    return jsonify({
        'updated': True,
        'message': 'Device status updated successfully'
    })

# 管理员路由: 用户审核
@app.route('/admin/users', methods=['GET'])
@login_required
def admin_users():
    # 检查管理员权限
    if not current_user.is_admin:
        flash('您没有管理员权限')
        return redirect(url_for('dashboard'))
        
    users = User.get_all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/<user_id>/approve', methods=['POST'])
@login_required
def approve_user(user_id):
    # 检查管理员权限
    if not current_user.is_admin:
        flash('您没有管理员权限')
        return redirect(url_for('dashboard'))
        
    user = User.get(user_id)
    if not user:
        flash('用户不存在')
        return redirect(url_for('admin_users'))
    
    user.status = 'approved'
    user.save()
    flash(f'用户 {user.username} 已批准')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<user_id>/reject', methods=['POST'])
@login_required
def reject_user(user_id):
    # 检查管理员权限
    if not current_user.is_admin:
        flash('您没有管理员权限')
        return redirect(url_for('dashboard'))
        
    user = User.get(user_id)
    if not user:
        flash('用户不存在')
        return redirect(url_for('admin_users'))
    
    user.status = 'rejected'
    user.save()
    flash(f'用户 {user.username} 已拒绝')
    app.logger.info(f"User {user.username} 已拒绝")
    return redirect(url_for('admin_users'))

# Admin Route: Assign/Manage visible devices for a user
@app.route('/admin/user/<user_id>/assign_devices', methods=['GET', 'POST'])
@login_required
def admin_assign_devices(user_id):
    if not current_user.is_admin:
        flash('您没有管理员权限。')
        return redirect(url_for('dashboard'))

    target_user = User.get(user_id)
    if not target_user:
        flash('用户不存在。')
        return redirect(url_for('admin_users'))

    if target_user.is_admin: 
        flash('不能为此管理员账户分配设备型号权限，管理员默认拥有所有权限。')
        return redirect(url_for('admin_users'))

    all_devices_in_system = Device.get_all()
    unique_model_numbers = sorted(list(set(d.model_number for d in all_devices_in_system)))

    if request.method == 'POST':
        selected_model_numbers = request.form.getlist('model_numbers')
        target_user.visible_model_numbers = selected_model_numbers
        target_user.save()
        flash(f"已更新用户 {target_user.username} 的可见设备型号列表。")
        app.logger.info(f"Admin {current_user.username} updated visible device models for user {target_user.username} to: {selected_model_numbers}")
        return redirect(url_for('admin_users'))

    return render_template('admin_assign_devices.html', 
                           target_user=target_user, 
                           all_model_numbers=unique_model_numbers,
                           assigned_model_numbers=target_user.visible_model_numbers)

# 路由: 删除设备
@app.route('/devices/delete/<device_id>', methods=['POST'])
@login_required
def delete_device(device_id):
    if not current_user.is_admin:
        flash('您没有权限执行此操作。')
        return redirect(url_for('list_devices'))

    device = Device.get(device_id)
    
    if not device: 
        flash('设备不存在')
        return redirect(url_for('list_devices'))
    
    # 获取设备的所有固件
    firmwares = Firmware.get_all(device_id=device_id)
    
    # 删除所有固件文件
    for firmware in firmwares:
        # 删除固件二进制文件
        if os.path.exists(firmware.file_path):
            os.remove(firmware.file_path)
        
        # 删除固件JSON文件
        firmware_file = os.path.join(app.config['DATA_FOLDER'], 'firmwares', f"{firmware.id}.json")
        if os.path.exists(firmware_file):
            os.remove(firmware_file)
    
    # 删除设备JSON文件
    device_file = os.path.join(app.config['DATA_FOLDER'], 'devices', f"{device_id}.json")
    if os.path.exists(device_file):
        os.remove(device_file)

    flash('设备及其所有固件已成功删除。')
    return redirect(url_for('list_devices'))

# API: 获取设备的现有固件版本
@app.route('/api/device/<device_id>/versions', methods=['GET'])
@login_required
def get_device_versions(device_id):
    target_device_instance = Device.get(device_id)
    if not target_device_instance:
        return jsonify({'error': 'Device not found or access denied'}), 404
    
    is_authorized = False
    if current_user.is_admin:
        is_authorized = True
    elif target_device_instance.model_number in current_user.visible_model_numbers:
        is_authorized = True

    if not is_authorized:
        app.logger.warning(f"User {current_user.id} unauthorized API attempt for device versions: {device_id} (model: {target_device_instance.model_number})")
        return jsonify({'error': 'Access denied to this device model versions'}), 403

    # 获取固件类型参数
    firmware_type = request.args.get('firmware_type', 'device')
    is_wifi = firmware_type == 'wifi'
    is_device = firmware_type == 'device'
    
    # 获取设备的所有固件
    all_firmwares = Firmware.get_all(device_id=device_id)
    
    # 过滤出指定类型的固件
    firmwares = [f for f in all_firmwares if f.is_wifi_firmware == is_wifi and f.is_device_firmware == is_device]
    
    # 构建版本列表
    versions = []
    for firmware in firmwares:
        versions.append({
            'version': firmware.version,
            'created_at': firmware.created_at,
            'status': firmware.status
        })
    
    # 按创建时间排序，最新的在前
    versions.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({
        'device_id': device_id,
        'firmware_type': firmware_type,
        'versions': versions
    })

# 路由: 删除固件
@app.route('/firmwares/delete/<firmware_id>', methods=['POST'])
@login_required
def delete_firmware(firmware_id):
    firmware_to_delete = Firmware.get(firmware_id)
    
    if not firmware_to_delete:
        flash('固件不存在')
        app.logger.warning(f"Attempt to delete non-existent firmware with ID: {firmware_id} by user {current_user.id}")
        return redirect(url_for('list_firmwares'))
    
    device_of_firmware = Device.get(firmware_to_delete.device_id)
    if not device_of_firmware: 
        flash('固件关联的设备不存在。')
        app.logger.error(f"Firmware {firmware_id} links to non-existent device {firmware_to_delete.device_id}. Deletion by {current_user.id}")
        return redirect(url_for('list_firmwares'))

    can_delete = False
    if current_user.is_admin:
        can_delete = True
    else:
        is_authorized_for_model = device_of_firmware.model_number in current_user.visible_model_numbers
        is_firmware_owner = firmware_to_delete.user_id == current_user.id
        if is_authorized_for_model and is_firmware_owner:
            can_delete = True

    if not can_delete:
        flash('您没有权限删除此固件。')
        app.logger.warning(f"User {current_user.id} unauthorized attempt to delete firmware {firmware_id} (device: {device_of_firmware.id}, model: {device_of_firmware.model_number}, owner: {firmware_to_delete.user_id})")
        device_id_for_redirect = request.args.get('device_id', firmware_to_delete.device_id)
        return redirect(url_for('list_firmwares', device_id=device_id_for_redirect) if device_id_for_redirect else url_for('list_firmwares'))

    # Proceed with deletion
    original_file_path = firmware_to_delete.file_path 
    if os.path.exists(firmware_to_delete.file_path):
        try:
            os.remove(firmware_to_delete.file_path)
            app.logger.info(f"Deleted firmware file: {firmware_to_delete.file_path}")
        except OSError as e:
            app.logger.error(f"Error deleting firmware file {firmware_to_delete.file_path}: {e}")
            flash(f'删除固件文件失败: {e}')
    
    # 删除固件JSON文件
    firmware_json_file_path = os.path.join(app.config['DATA_FOLDER'], 'firmwares', f"{firmware_to_delete.id}.json")
    if os.path.exists(firmware_json_file_path):
        try:
            os.remove(firmware_json_file_path)
            app.logger.info(f"Deleted firmware metadata file: {firmware_json_file_path}")
        except OSError as e:
            app.logger.error(f"Error deleting firmware metadata file {firmware_json_file_path}: {e}")
            flash(f'删除固件元数据文件失败: {e}')
    
    flash('固件已成功删除')
    app.logger.info(f"Firmware {firmware_id} (path {original_file_path}, version {firmware_to_delete.version}) deleted successfully by user {current_user.id}")
    
    # 如果是从设备固件列表页面删除，则返回到该页面
    device_id = request.args.get('device_id')
    if device_id:
        return redirect(url_for('list_firmwares', device_id=device_id))
    else:
        return redirect(url_for('list_firmwares'))

if __name__ == '__main__':
    # Setup logging
    log_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    
    # File Handler
    log_file = os.path.join(app.config['DATA_FOLDER'], 'app.log')
    file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024*5, backupCount=5)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)
    
    # Console Handler (for Flask's default logger, and optionally our app logger)
    # Flask's default logger already logs to console when debug=True.
    # If you want more control or to log app-specific messages to console even when debug=False:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.DEBUG) # Or logging.INFO for less verbosity

    # Add handlers to Flask app logger
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler) # Add if you want app.logger messages on console too
    app.logger.setLevel(logging.INFO) # Set root level for app.logger

    # Werkzeug logger (handles request logs) can also be configured if needed
    # By default, it logs to stderr. You can get its logger and add handlers:
    # werkzeug_logger = logging.getLogger('werkzeug')
    # werkzeug_logger.addHandler(file_handler)
    # werkzeug_logger.setLevel(logging.INFO)

    app.logger.info("Application startup")

    # 创建管理员账户（如果不存在）
    admin = User.get_by_username('admin')
    if not admin:
        admin_password = generate_password_hash('admin123')
        admin = User(
            id=generate_id(),
            username='admin',
            password=admin_password,
            company_name='Dreame Technology',
            email='admin@dreame.com',
            phone='123456789',
            status='approved',
            is_admin=True
        )
        admin.save()
        app.logger.info('管理员账户已创建')
    
    # 创建SSL上下文
    try:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile='cert.pem', keyfile='key.pem')
        
        # 启动HTTPS服务器
        https_server = Thread(target=lambda: app.run(debug=False, host='0.0.0.0', port=3443, ssl_context=ssl_context))
        https_server.daemon = True
        https_server.start()
        app.logger.info('HTTPS服务器已启动在端口3443')
    except Exception as e:
        app.logger.error(f'HTTPS服务器启动失败: {str(e)}')
        app.logger.warning('请确保cert.pem和key.pem文件存在')
    
    # 启动HTTP服务器（主线程）
    app.logger.info('HTTP服务器已启动在端口3001')
    app.run(debug=True, host='0.0.0.0', port=3001, use_reloader=False)