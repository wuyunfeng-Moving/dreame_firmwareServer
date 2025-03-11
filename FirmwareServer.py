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
                 created_at=None, updated_at=None, is_admin=False):
        self.id = id
        self.username = username
        self.password = password
        self.company_name = company_name
        self.email = email
        self.phone = phone
        self.status = status
        self.created_at = created_at or datetime.datetime.utcnow().isoformat()
        self.updated_at = updated_at or datetime.datetime.utcnow().isoformat()
        self.is_admin = is_admin
        
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'password': self.password,
            'company_name': self.company_name,
            'email': self.email,
            'phone': self.phone,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'is_admin': self.is_admin
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data['id'],
            username=data['username'],
            password=data['password'],
            company_name=data['company_name'],
            email=data['email'],
            phone=data['phone'],
            status=data['status'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            is_admin=data['is_admin']
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
        self.updated_at = datetime.datetime.utcnow().isoformat()
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
        self.created_at = created_at or datetime.datetime.utcnow().isoformat()
        self.updated_at = updated_at or datetime.datetime.utcnow().isoformat()
    
    def to_dict(self):
        return {
            'id': self.id,
            'model_number': self.model_number,
            'model_name': self.model_name,
            'description': self.description,
            'user_id': self.user_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data['id'],
            model_number=data['model_number'],
            model_name=data['model_name'],
            description=data['description'],
            user_id=data['user_id'],
            created_at=data['created_at'],
            updated_at=data['updated_at']
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
        self.updated_at = datetime.datetime.utcnow().isoformat()
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
        self.created_at = created_at or datetime.datetime.utcnow().isoformat()
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
            'created_at': self.created_at,
            'compatible_versions': self.compatible_versions
        }
    
    @classmethod
    def from_dict(cls, data):
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
            created_at=data['created_at'],
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

# 计算文件CRC16校验和
def calculate_crc_modbus(file_path):
    crc16_table = [0] * 256
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc = crc >> 1
        crc16_table[i] = crc & 0xFFFF
    
    crc = 0xFFFF
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            for byte in chunk:
                crc = crc16_table[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return f"{crc & 0xFFFF:04X}"

# 添加模板全局函数
@app.template_global()
def get_device(device_id):
    return Device.get(device_id)

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
    devices = Device.get_all(user_id=current_user.id)
    return render_template('dashboard.html', devices=devices)

# 路由: 设备管理
@app.route('/devices', methods=['GET'])
@login_required
def list_devices():
    devices = Device.get_all(user_id=current_user.id)
    return render_template('devices.html', devices=devices)

# 路由: 添加设备
@app.route('/devices/add', methods=['GET', 'POST'])
@login_required
def add_device():
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
    device_id = request.args.get('device_id')
    if device_id:
        device = Device.get(device_id)
        if not device or device.user_id != current_user.id:
            return redirect(url_for('list_devices'))
        
        firmwares = Firmware.get_all(device_id=device_id)
        return render_template('firmwares.html', firmwares=firmwares, device=device)
    else:
        firmwares = Firmware.get_all(user_id=current_user.id)
        return render_template('firmwares.html', firmwares=firmwares)

# 验证版本格式是否符合 x.x.x
def validate_version_format(version):
    pattern = r'^\d+\.\d+\.\d+$'
    return re.match(pattern, version) is not None

# 路由: 上传固件
@app.route('/firmwares/upload', methods=['GET', 'POST'])
@login_required
def upload_firmware():
    if request.method == 'POST':
        device_id = request.form.get('device_id')
        version = request.form.get('version')
        description = request.form.get('description')
        firmware_type = request.form.get('firmware_type')
        compatible_versions = request.form.getlist('compatible_versions')
        
        # 验证版本格式
        if not validate_version_format(version):
            flash('版本格式必须为 x.x.x（如 1.0.0）')
            return redirect(request.url)
        
        # 验证兼容版本格式
        for cv in compatible_versions:
            if not validate_version_format(cv):
                flash(f'兼容版本 {cv} 格式不正确，必须为 x.x.x（如 1.0.0）')
                return redirect(request.url)
        
        if 'firmware_file' not in request.files:
            flash('没有选择文件')
            return redirect(request.url)
        
        file = request.files['firmware_file']
        if file.filename == '':
            flash('没有选择文件')
            return redirect(request.url)
        
        # 检查设备是否存在
        device = Device.get(device_id)
        if not device or device.user_id != current_user.id:
            flash('设备不存在')
            return redirect(url_for('list_devices'))
        
        # 检查版本是否已存在
        is_wifi = firmware_type == 'wifi'
        is_device = firmware_type == 'device'
        
        # 检查是否已存在相同版本的固件
        existing_firmwares = Firmware.get_all(device_id=device_id)
        for firmware in existing_firmwares:
            if firmware.version == version and firmware.is_wifi_firmware == is_wifi and firmware.is_device_firmware == is_device:
                flash('该版本固件已存在')
                return redirect(url_for('upload_firmware'))
        
        # 验证兼容版本是否存在于该设备的固件中
        valid_compatible_versions = []
        for cv in compatible_versions:
            for ef in existing_firmwares:
                if ef.version == cv and ef.is_wifi_firmware == is_wifi and ef.is_device_firmware == is_device:
                    valid_compatible_versions.append(cv)
                    break
        
        # 保存文件
        filename = secure_filename(f"{device.model_number}_{firmware_type}_{version}_{uuid.uuid4()}.bin")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # 计算CRC校验和
        crc = calculate_crc(file_path)
        
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
            compatible_versions=valid_compatible_versions
        )
        
        new_firmware.save()
        
        flash('固件上传成功')
        return redirect(url_for('list_firmwares', device_id=device_id))
    
    devices = Device.get_all(user_id=current_user.id)
    return render_template('upload_firmware.html', devices=devices)

# API: 固件查询
@app.route('/firmware/check', methods=['POST'])
def check_firmware():
    print("check_firmware")
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    model_number = data.get('device_model')
    device_version = data.get('device_version')
    wifi_version = data.get('wifi_version')
    
    if not model_number or not device_version or not wifi_version:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # 验证版本格式
    if not validate_version_format(device_version):
        return jsonify({'error': 'Invalid device version format, must be x.x.x'}), 400
    
    if not validate_version_format(wifi_version):
        return jsonify({'error': 'Invalid WiFi version format, must be x.x.x'}), 400
    
    # 查找设备
    device = Device.get_by_model_number(model_number)
    if not device:
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
        download_url = url_for('download_firmware', firmware_id=device_firmware.id, _external=True)
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
        is_device=False,
        getlatest=True
    )
    
    if wifi_firmware:
        download_url = url_for('download_firmware', firmware_id=wifi_firmware.id, _external=True)
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
    
    return jsonify(response)

# API: 固件下载
@app.route('/firmware/download/<firmware_id>', methods=['GET'])
def download_firmware(firmware_id):
    firmware = Firmware.get(firmware_id)
    if not firmware:
        return jsonify({'error': 'Firmware not found'}), 404
    
    return send_file(firmware.file_path, as_attachment=True)

# 新增: 固件分块下载API
@app.route('/api/firmware/download/chunk/<int:firmware_id>', methods=['GET'])
def download_firmware_chunk(firmware_id):
    firmware = Firmware.get(firmware_id)
    if not firmware:
        return jsonify({'error': 'Firmware not found'}), 404
    
    # 获取分块参数
    chunk_size = request.args.get('chunk_size', type=int, default=1024)
    chunk_index = request.args.get('chunk_index', type=int, default=0)
    
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
            
            # 返回分块数据和元数据
            response = {
                'chunk_index': chunk_index,
                'total_chunks': total_chunks,
                'chunk_size': len(chunk_data),
                'data': chunk_data.hex()  # 将二进制数据转换为十六进制字符串
            }
            
            return jsonify(response)
    except Exception as e:
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
    return redirect(url_for('admin_users'))

# 路由: 删除设备
@app.route('/devices/delete/<device_id>', methods=['POST'])
@login_required
def delete_device(device_id):
    device = Device.get(device_id)
    
    # 检查设备是否存在且属于当前用户
    if not device or device.user_id != current_user.id:
        flash('设备不存在或您没有权限删除')
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
    
    flash('设备及其所有固件已成功删除')
    return redirect(url_for('list_devices'))

# API: 获取设备的现有固件版本
@app.route('/api/device/<device_id>/versions', methods=['GET'])
@login_required
def get_device_versions(device_id):
    # 检查设备是否存在且属于当前用户
    device = Device.get(device_id)
    if not device or device.user_id != current_user.id:
        return jsonify({'error': 'Device not found or access denied'}), 404
    
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
    firmware = Firmware.get(firmware_id)
    
    # 检查固件是否存在
    if not firmware:
        flash('固件不存在')
        return redirect(url_for('list_firmwares'))
    
    # 检查固件是否属于当前用户
    device = Device.get(firmware.device_id)
    if not device or device.user_id != current_user.id:
        flash('您没有权限删除此固件')
        return redirect(url_for('list_firmwares'))
    
    # 删除固件二进制文件
    if os.path.exists(firmware.file_path):
        os.remove(firmware.file_path)
    
    # 删除固件JSON文件
    firmware_file = os.path.join(app.config['DATA_FOLDER'], 'firmwares', f"{firmware.id}.json")
    if os.path.exists(firmware_file):
        os.remove(firmware_file)
    
    flash('固件已成功删除')
    
    # 如果是从设备固件列表页面删除，则返回到该页面
    device_id = request.args.get('device_id')
    if device_id:
        return redirect(url_for('list_firmwares', device_id=device_id))
    else:
        return redirect(url_for('list_firmwares'))

if __name__ == '__main__':
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
        print('管理员账户已创建')
    
    # 创建SSL上下文
    try:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile='cert.pem', keyfile='key.pem')
        
        # 启动HTTPS服务器
        https_server = Thread(target=lambda: app.run(debug=False, host='0.0.0.0', port=3443, ssl_context=ssl_context))
        https_server.daemon = True
        https_server.start()
        print('HTTPS服务器已启动在端口3443')
    except Exception as e:
        print(f'HTTPS服务器启动失败: {str(e)}')
        print('请确保cert.pem和key.pem文件存在')
    
    # 启动HTTP服务器（主线程）
    print('HTTP服务器已启动在端口3000')
    app.run(debug=True, host='0.0.0.0', port=3000, use_reloader=False)