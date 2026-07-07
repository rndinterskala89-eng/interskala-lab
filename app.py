"""
MHB-832SD Dashboard - Flask Application
Dengan Fitur Foto Hasil Pekerjaan Teknisi
Versi Production untuk Neo Lite
"""

import os
import sys
import json
import time
import base64
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from io import BytesIO

import requests
import pandas as pd
from flask import Flask, jsonify, request, render_template, send_file, send_from_directory
from flask_cors import CORS

# ============================================================
# KONFIGURASI ENVIRONMENT
# ============================================================

# Deteksi environment
ENV = os.environ.get('FLASK_ENV', 'development')
IS_PRODUCTION = ENV == 'production'

# Port untuk production (gunakan 8084 agar tidak bentrok dengan port 8083)
PRODUCTION_PORT = 8084

# Folder untuk upload file
UPLOAD_FOLDER = Path('uploads')
UPLOAD_FOLDER.mkdir(exist_ok=True)

# ============================================================
# LOAD KONFIGURASI DARI ENVIRONMENT / CONFIG.PY
# ============================================================

try:
    from config import (
        THINGSPEAK_API_KEY,
        THINGSPEAK_CHANNEL_ID,
        SERVER_HOST,
        SERVER_PORT,
        DEBUG_MODE,
        SUHU_MIN,
        SUHU_MAX,
        KELEMBABAN_MIN,
        KELEMBABAN_MAX,
        SAVE_INTERVAL_MINUTES,
        DEFAULT_USERNAME,
        DEFAULT_PASSWORD
    )
except ImportError:
    # Fallback jika config.py tidak ada - gunakan environment variables
    THINGSPEAK_API_KEY = os.environ.get('THINGSPEAK_API_KEY', 'YOUR_API_KEY')
    THINGSPEAK_CHANNEL_ID = os.environ.get('THINGSPEAK_CHANNEL_ID', 'YOUR_CHANNEL_ID')
    SERVER_HOST = '0.0.0.0'
    SERVER_PORT = int(os.environ.get('PORT', 8084))
    DEBUG_MODE = False
    SUHU_MIN = float(os.environ.get('SUHU_MIN', 18))
    SUHU_MAX = float(os.environ.get('SUHU_MAX', 26))
    KELEMBABAN_MIN = float(os.environ.get('KELEMBABAN_MIN', 20))
    KELEMBABAN_MAX = float(os.environ.get('KELEMBABAN_MAX', 60))
    SAVE_INTERVAL_MINUTES = int(os.environ.get('SAVE_INTERVAL_MINUTES', 5))
    DEFAULT_USERNAME = os.environ.get('DEFAULT_USERNAME', 'admin')
    DEFAULT_PASSWORD = os.environ.get('DEFAULT_PASSWORD', 'admin123')

# ============================================================
# THINGSPEAK CONFIG PERMANEN (Server-side)
# ============================================================

THINGSPEAK_CONFIG_FILE = 'thingspeak_config.json'

def load_thingspeak_config():
    """Load ThingSpeak config dari file JSON"""
    try:
        with open(THINGSPEAK_CONFIG_FILE, 'r') as f:
            config = json.load(f)
            print(f"📡 Loaded ThingSpeak config from file: {config.get('channelId', 'empty')}")
            return config
    except FileNotFoundError:
        print("📡 ThingSpeak config file not found, creating default")
        default_config = {
            "channelId": "",
            "readApiKey": "",
            "fieldSuhu": "field1",
            "fieldKelembaban": "field2",
            "fieldTekanan": "field3"
        }
        save_thingspeak_config(default_config)
        return default_config

def save_thingspeak_config(config):
    """Save ThingSpeak config ke file JSON"""
    with open(THINGSPEAK_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"💾 ThingSpeak config saved to file: {config.get('channelId', 'empty')}")

# Load config dari file
THINGSPEAK_CONFIG = load_thingspeak_config()

# Update API_KEY dan CHANNEL_ID dari config jika ada
if THINGSPEAK_CONFIG.get('channelId') and THINGSPEAK_CONFIG.get('readApiKey'):
    THINGSPEAK_CHANNEL_ID = THINGSPEAK_CONFIG.get('channelId')
    THINGSPEAK_API_KEY = THINGSPEAK_CONFIG.get('readApiKey')
    print(f"📡 ThingSpeak configured: Channel {THINGSPEAK_CHANNEL_ID}")

# ============================================================
# INISIALISASI FLASK
# ============================================================

app = Flask(__name__, 
    static_folder='static',
    template_folder='templates'
)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Enable CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ============================================================
# DATA STORE (In-memory database)
# ============================================================

# Users
USERS = [
    {"id": 1, "name": "Admin", "email": "admin@lab.com", "role": "Admin", "avatar": "A", "password": "admin123", 
     "access": {"dashboard": True, "setting": True, "history": True, "usermanagement": True, "schedule": True, "profile": True, "map": True}},
    {"id": 2, "name": "Teknisi 1", "email": "teknisi1@lab.com", "role": "Teknisi", "avatar": "T1", "password": "tek123",
     "access": {"dashboard": True, "setting": False, "history": False, "usermanagement": False, "schedule": True, "profile": False, "map": False}},
    {"id": 3, "name": "Sales 1", "email": "sales1@lab.com", "role": "Sales", "avatar": "S1", "password": "sales123",
     "access": {"dashboard": True, "setting": False, "history": False, "usermanagement": False, "schedule": True, "profile": False, "map": False}},
    {"id": 4, "name": "Viewer 1", "email": "viewer@lab.com", "role": "Viewer", "avatar": "V1", "password": "view123",
     "access": {"dashboard": True, "setting": False, "history": False, "usermanagement": False, "schedule": False, "profile": False, "map": False}}
]

# Schedules dengan field foto
SCHEDULES = [
    {"id": 1, "tglPengajuan": "2026-06-28", "namaTeknis": "Budi Santoso", "namaSales": "Andi Wijaya", 
     "customer": "PT Maju Jaya", "lokasiCustomer": "Jl. Sudirman No. 123, Jakarta Pusat", 
     "tglPelaksana": "2026-07-05", "jamMulai": "09:00", "jamSelesai": "17:00", 
     "keterangan": "Instalasi sensor suhu", "poSo": "PO-001", "status": "Done", 
     "foto": None, "fotoName": None, "pdf": None, "createdBy": "admin",
     "fotoUploadedAt": None, "fotoStatus": "Belum ada foto"},
    {"id": 2, "tglPengajuan": "2026-06-29", "namaTeknis": "Cahyo Prabowo", "namaSales": "Siti Rahayu", 
     "customer": "CV Berkah Abadi", "lokasiCustomer": "Jl. Pahlawan No. 45, Bandung", 
     "tglPelaksana": "2026-07-05", "jamMulai": "10:00", "jamSelesai": "15:00", 
     "keterangan": "Maintenance rutin", "poSo": "PO-002", "status": "Done", 
     "foto": None, "fotoName": None, "pdf": None, "createdBy": "admin",
     "fotoUploadedAt": None, "fotoStatus": "Belum ada foto"},
    {"id": 3, "tglPengajuan": "2026-07-01", "namaTeknis": "Dedi Kurniawan", "namaSales": "Rina Sari", 
     "customer": "PT Teknologi Nusantara", "lokasiCustomer": "Jl. Gatot Subroto No. 78, Surabaya", 
     "tglPelaksana": "2026-07-06", "jamMulai": "08:00", "jamSelesai": "16:00", 
     "keterangan": "Kalibrasi sensor tekanan", "poSo": "PO-003", "status": "On Progress", 
     "foto": None, "fotoName": None, "pdf": None, "createdBy": "admin",
     "fotoUploadedAt": None, "fotoStatus": "Belum ada foto"}
]

# History Data
history_data = []
history_id_counter = 1

# Cache untuk data sensor
last_data_cache = {
    "success": True,
    "data": {
        "suhu": 24.6,
        "kelembaban": 42.3,
        "tekanan": 1010.6,
        "waktu": datetime.now().isoformat(),
        "entry_id": "0"
    },
    "last_update": datetime.now().isoformat()
}
last_save_time = None
last_saved_data = {"suhu": 0, "kelembaban": 0, "tekanan": 0}

# Company Profile
PROFILE = {
    "nama": "PT Lab Interskala Mandiri Indonesia",
    "alamat": "Jl. Daan Mogot Sedayu Bizpark Dm.12 No.62 Kalideres Jakarta-Barat",
    "telepon": "(021) 555-1234",
    "email": "sales@interskala.com",
    "website": "www.labinterskala.com",
    "bidang": "Kalibrasi & Pengujian",
    "npwp": "01.234.567.8-123.000",
    "tahun": "2010"
}

# Settings
settings = {
    "saveInterval": SAVE_INTERVAL_MINUTES,
    "suhuMin": SUHU_MIN,
    "suhuMax": SUHU_MAX,
    "kelembabanMin": KELEMBABAN_MIN,
    "kelembabanMax": KELEMBABAN_MAX
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_status(suhu, kelembaban):
    """Mendapatkan status berdasarkan threshold"""
    s = settings
    status = "✅ Normal"
    color = "#22c55e"
    bg = "#d1fae5"
    
    if suhu < s["suhuMin"] or suhu > s["suhuMax"] or kelembaban < s["kelembabanMin"] or kelembaban > s["kelembabanMax"]:
        status = "🔴 Danger"
        color = "#ef4444"
        bg = "#fee2e2"
    elif suhu < s["suhuMin"] + 2 or suhu > s["suhuMax"] - 2 or kelembaban < s["kelembabanMin"] + 5 or kelembaban > s["kelembabanMax"] - 5:
        status = "⚠️ Warning"
        color = "#f59e0b"
        bg = "#fef3c7"
    
    return {"status": status, "color": color, "bg": bg}

def format_time(dt):
    """Format datetime ke string waktu"""
    return dt.strftime("%H:%M:%S")

def format_datetime(dt):
    """Format datetime ke string lengkap"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def fetch_thingspeak_data():
    """Mengambil data dari ThingSpeak"""
    global last_data_cache, THINGSPEAK_CHANNEL_ID, THINGSPEAK_API_KEY
    
    # Cek apakah config sudah diisi
    if not THINGSPEAK_CHANNEL_ID or THINGSPEAK_CHANNEL_ID == 'YOUR_CHANNEL_ID':
        print("⚠️ ThingSpeak not configured - using simulation data")
        return {
            "success": True,
            "data": {
                "suhu": 24.6 + (time.time() % 2 - 1) * 2,
                "kelembaban": 42.3 + (time.time() % 3 - 1) * 3,
                "tekanan": 1010.6 + (time.time() % 2 - 1) * 1.5,
                "waktu": datetime.now().isoformat(),
                "entry_id": "0"
            },
            "last_update": datetime.now().isoformat(),
            "source": "simulasi"
        }
    
    try:
        url = f'https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds/last.json?api_key={THINGSPEAK_API_KEY}'
        
        print(f"📡 Fetching data at {datetime.now().strftime('%H:%M:%S')}")
        
        headers = {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            latest = response.json()
            
            field1 = latest.get('field1')
            field2 = latest.get('field2')
            field3 = latest.get('field3')
            
            if field1 is not None and field2 is not None and field3 is not None:
                print(f"✅ Data: Suhu={field1}°C, Kelembaban={field2}%, Tekanan={field3}hPa")
                
                result = {
                    "success": True,
                    "data": {
                        "suhu": float(field1),
                        "kelembaban": float(field2),
                        "tekanan": float(field3),
                        "waktu": latest.get('created_at', datetime.now().isoformat()),
                        "entry_id": latest.get('entry_id', '0')
                    },
                    "last_update": datetime.now().isoformat(),
                    "source": "thingspeak"
                }
                
                last_data_cache = result
                return result
            else:
                print(f"❌ Data tidak lengkap: field1={field1}, field2={field2}, field3={field3}")
                
    except requests.exceptions.Timeout:
        print(f"❌ ThingSpeak timeout - using cached data")
    except requests.exceptions.RequestException as e:
        print(f"❌ ThingSpeak request error: {e}")
    except Exception as e:
        print(f"❌ ThingSpeak error: {e}")
    
    if last_data_cache and last_data_cache.get("success"):
        print("📡 Returning cached data")
        return last_data_cache
    
    # Fallback ke simulasi
    return {
        "success": True,
        "data": {
            "suhu": 24.6 + (time.time() % 2 - 1) * 2,
            "kelembaban": 42.3 + (time.time() % 3 - 1) * 3,
            "tekanan": 1010.6 + (time.time() % 2 - 1) * 1.5,
            "waktu": datetime.now().isoformat(),
            "entry_id": "0"
        },
        "last_update": datetime.now().isoformat(),
        "source": "simulasi"
    }

def save_to_history(data):
    """Menyimpan data ke history berdasarkan interval"""
    global last_save_time, last_saved_data, history_id_counter
    
    if not data or not data.get("success"):
        return
    
    now = datetime.now()
    interval_ms = settings["saveInterval"] * 60 * 1000
    
    if "data" not in data:
        return
    
    sensor_data = data["data"]
    suhu = sensor_data.get("suhu", 0)
    kelembaban = sensor_data.get("kelembaban", 0)
    tekanan = sensor_data.get("tekanan", 0)
    
    if last_save_time is None:
        last_save_time = now
        last_saved_data = {"suhu": suhu, "kelembaban": kelembaban, "tekanan": tekanan}
        add_history(suhu, kelembaban, tekanan)
        return
    
    elapsed = (now - last_save_time).total_seconds() * 1000
    if elapsed >= interval_ms:
        diff_suhu = abs(suhu - last_saved_data["suhu"])
        diff_kelem = abs(kelembaban - last_saved_data["kelembaban"])
        
        if diff_suhu > 0.1 or diff_kelem > 0.5 or elapsed >= interval_ms * 1.5:
            last_save_time = now
            last_saved_data = {"suhu": suhu, "kelembaban": kelembaban, "tekanan": tekanan}
            add_history(suhu, kelembaban, tekanan)

def add_history(suhu, kelembaban, tekanan):
    """Menambahkan data ke history"""
    global history_id_counter
    
    status = get_status(suhu, kelembaban)
    
    history_data.append({
        "id": history_id_counter,
        "time": format_datetime(datetime.now()),
        "user": "System",
        "suhu": f"{suhu:.1f}",
        "kelembaban": f"{kelembaban:.1f}",
        "tekanan": f"{tekanan:.1f}",
        "status": status["status"],
        "statusColor": status["color"],
        "statusBg": status["bg"]
    })
    
    history_id_counter += 1
    
    if len(history_data) > 500:
        history_data.pop(0)

def add_schedule_history(schedule_id, action, description, user="Teknisi"):
    """Tambahkan history untuk schedule"""
    global history_id_counter
    
    # Cari schedule
    schedule = None
    for s in SCHEDULES:
        if s["id"] == schedule_id:
            schedule = s
            break
    
    if schedule is None:
        return
    
    customer_name = schedule.get("customer", "Unknown")
    
    history_data.append({
        "id": history_id_counter,
        "time": format_datetime(datetime.now()),
        "user": user,
        "suhu": "-",
        "kelembaban": "-",
        "tekanan": "-",
        "status": f"📋 {action}",
        "statusColor": "#800020",
        "statusBg": "#fdf2f4",
        "schedule_customer": customer_name,
        "schedule_action": description
    })
    
    history_id_counter += 1
    
    if len(history_data) > 500:
        history_data.pop(0)

def get_schedule_by_id(schedule_id):
    """Get schedule by ID"""
    for s in SCHEDULES:
        if s["id"] == schedule_id:
            return s
    return None

# ============================================================
# API ROUTES - FOTO & STATUS
# ============================================================

@app.route('/api/schedule/<int:schedule_id>/upload-foto', methods=['POST'])
def upload_schedule_foto(schedule_id):
    """Upload foto untuk schedule tertentu"""
    try:
        schedule = get_schedule_by_id(schedule_id)
        if schedule is None:
            return jsonify({"success": False, "message": "Schedule tidak ditemukan"}), 404
        
        # Cek file foto
        if 'foto' not in request.files:
            return jsonify({"success": False, "message": "Tidak ada file foto"}), 400
        
        file = request.files['foto']
        if file.filename == '':
            return jsonify({"success": False, "message": "Nama file kosong"}), 400
        
        # Baca dan convert ke base64
        file_data = file.read()
        base64_data = base64.b64encode(file_data).decode('utf-8')
        
        # Tentukan mime type
        filename = file.filename or 'image.jpg'
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'jpg'
        mime_type = f"image/{ext}"
        if ext in ['jpg', 'jpeg']:
            mime_type = "image/jpeg"
        elif ext == 'png':
            mime_type = "image/png"
        elif ext == 'gif':
            mime_type = "image/gif"
        elif ext == 'webp':
            mime_type = "image/webp"
        
        foto_data_url = f"data:{mime_type};base64,{base64_data}"
        
        # Update schedule
        schedule['foto'] = foto_data_url
        schedule['fotoName'] = filename
        schedule['fotoUploadedAt'] = datetime.now().isoformat()
        schedule['fotoStatus'] = "✅ Foto terupload"
        
        # Tambah history
        user_from_form = request.form.get('user')
        if user_from_form is None:
            user_from_form = 'Teknisi'
        
        add_schedule_history(
            schedule_id,
            "📷 Upload Foto",
            f"Upload foto: {filename} untuk customer {schedule.get('customer', 'Unknown')}",
            user=user_from_form
        )
        
        return jsonify({
            "success": True,
            "message": "Foto berhasil diupload!",
            "foto": foto_data_url,
            "fotoName": filename,
            "schedule": schedule
        })
        
    except Exception as e:
        print(f"❌ Upload foto error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/schedule/<int:schedule_id>/update-status', methods=['POST'])
def update_schedule_status(schedule_id):
    """Update status schedule - dengan validasi foto jika status Done"""
    try:
        schedule = get_schedule_by_id(schedule_id)
        if schedule is None:
            return jsonify({"success": False, "message": "Schedule tidak ditemukan"}), 404
        
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
        
        new_status = data.get('status', '')
        user_from_data = data.get('user', 'Teknisi')
        
        # Pastikan user adalah string
        if user_from_data is None:
            user_from_data = 'Teknisi'
        
        valid_status = ['On Progress', 'Done', 'Cancel', 'Reschedule']
        if new_status not in valid_status:
            return jsonify({"success": False, "message": "Status tidak valid"}), 400
        
        old_status = schedule.get('status', 'On Progress')
        
        # Jika status diubah ke Done, wajib ada foto
        if new_status == 'Done' and schedule.get('foto') is None:
            return jsonify({
                "success": False, 
                "message": "⚠️ Wajib upload foto sebelum mengubah status ke Done!"
            }), 400
        
        # Update status
        schedule['status'] = new_status
        
        # Tambah history
        add_schedule_history(
            schedule_id,
            "📝 Status Berubah",
            f"Status berubah dari {old_status} ke {new_status} untuk customer {schedule.get('customer', 'Unknown')}",
            user=user_from_data
        )
        
        # Jika status Done dan ada foto, update fotoStatus
        if new_status == 'Done' and schedule.get('foto') is not None:
            schedule['fotoStatus'] = "✅ Foto terupload - Status Done"
        
        return jsonify({
            "success": True,
            "message": f"Status berhasil diubah ke {new_status}",
            "schedule": schedule
        })
        
    except Exception as e:
        print(f"❌ Update status error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/schedule/<int:schedule_id>/foto')
def get_schedule_foto(schedule_id):
    """Get foto untuk schedule tertentu"""
    schedule = get_schedule_by_id(schedule_id)
    if schedule is None:
        return jsonify({"success": False, "message": "Schedule tidak ditemukan"}), 404
    
    return jsonify({
        "success": True,
        "foto": schedule.get('foto'),
        "fotoName": schedule.get('fotoName'),
        "fotoStatus": schedule.get('fotoStatus', 'Belum ada foto'),
        "fotoUploadedAt": schedule.get('fotoUploadedAt')
    })

@app.route('/api/schedules/done-with-foto')
def get_done_schedules_with_foto():
    """Get semua schedule dengan status Done dan memiliki foto"""
    done_schedules = []
    for s in SCHEDULES:
        if s.get('status') == 'Done' and s.get('foto') is not None:
            done_schedules.append(s)
    
    return jsonify({
        "success": True,
        "count": len(done_schedules),
        "schedules": done_schedules
    })

# ============================================================
# API ROUTES - MAIN
# ============================================================

@app.route('/')
def index():
    """Halaman utama dashboard"""
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    """API Login"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
            
        username = data.get('username', '').strip().lower()
        password = data.get('password', '').strip()
        
        for u in USERS:
            if u.get('name', '').lower() == username and u.get('password', '') == password:
                return jsonify({
                    "success": True,
                    "user": {
                        "id": u.get('id'),
                        "name": u.get('name'),
                        "role": u.get('role'),
                        "avatar": u.get('avatar')
                    }
                })
        
        return jsonify({"success": False, "message": "Username atau password salah!"}), 401
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/data')
def get_data():
    """API mengambil data dari ThingSpeak"""
    data = fetch_thingspeak_data()
    if data and data.get("success"):
        save_to_history(data)
    return jsonify(data)

@app.route('/api/users')
def get_users():
    """API mendapatkan daftar user"""
    users = []
    for u in USERS:
        users.append({
            "id": u.get('id'),
            "name": u.get('name', ''),
            "email": u.get('email', ''),
            "role": u.get('role', ''),
            "avatar": u.get('avatar', ''),
            "access": u.get('access', {})
        })
    return jsonify({"success": True, "users": users})

@app.route('/api/users', methods=['POST'])
def add_user():
    """API menambah user"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
        
        # Hitung ID baru
        max_id = 0
        for u in USERS:
            if u.get('id', 0) > max_id:
                max_id = u.get('id', 0)
        new_id = max_id + 1
            
        new_user = {
            "id": new_id,
            "name": data.get('name', ''),
            "email": data.get('email', ''),
            "role": data.get('role', 'Viewer'),
            "avatar": data.get('name', 'U')[0].upper() if data.get('name') else 'U',
            "password": data.get('password', 'default123'),
            "access": data.get('access', {})
        }
        USERS.append(new_user)
        return jsonify({"success": True, "user": new_user})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """API mengupdate user"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
            
        for u in USERS:
            if u.get('id') == user_id:
                u['name'] = data.get('name', u.get('name', ''))
                u['email'] = data.get('email', u.get('email', ''))
                u['role'] = data.get('role', u.get('role', ''))
                u['password'] = data.get('password', u.get('password', ''))
                if data.get('name'):
                    u['avatar'] = data.get('name', '')[0].upper()
                u['access'] = data.get('access', u.get('access', {}))
                return jsonify({"success": True, "user": u})
        return jsonify({"success": False, "message": "User not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """API menghapus user"""
    try:
        global USERS
        new_users = []
        for u in USERS:
            if u.get('id') != user_id:
                new_users.append(u)
        USERS = new_users
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/schedules')
def get_schedules():
    """API mendapatkan daftar schedule"""
    return jsonify({"success": True, "schedules": SCHEDULES})

@app.route('/api/schedules', methods=['POST'])
def add_schedule():
    """API menambah schedule"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
        
        # Hitung ID baru
        max_id = 0
        for s in SCHEDULES:
            if s.get('id', 0) > max_id:
                max_id = s.get('id', 0)
        new_id = max_id + 1
            
        new_schedule = {
            "id": new_id,
            "tglPengajuan": data.get('tglPengajuan', ''),
            "namaTeknis": data.get('namaTeknis', ''),
            "namaSales": data.get('namaSales', ''),
            "customer": data.get('customer', ''),
            "lokasiCustomer": data.get('lokasiCustomer', ''),
            "tglPelaksana": data.get('tglPelaksana', ''),
            "jamMulai": data.get('jamMulai', ''),
            "jamSelesai": data.get('jamSelesai', ''),
            "keterangan": data.get('keterangan', ''),
            "poSo": data.get('poSo', ''),
            "status": data.get('status', 'On Progress'),
            "foto": None,
            "fotoName": None,
            "pdf": None,
            "createdBy": data.get('createdBy', 'System'),
            "fotoUploadedAt": None,
            "fotoStatus": "Belum ada foto"
        }
        SCHEDULES.append(new_schedule)
        return jsonify({"success": True, "schedule": new_schedule})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/schedules/<int:schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    """API mengupdate schedule"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
            
        for s in SCHEDULES:
            if s.get('id') == schedule_id:
                if 'tglPengajuan' in data:
                    s['tglPengajuan'] = data['tglPengajuan']
                if 'namaTeknis' in data:
                    s['namaTeknis'] = data['namaTeknis']
                if 'namaSales' in data:
                    s['namaSales'] = data['namaSales']
                if 'customer' in data:
                    s['customer'] = data['customer']
                if 'lokasiCustomer' in data:
                    s['lokasiCustomer'] = data['lokasiCustomer']
                if 'tglPelaksana' in data:
                    s['tglPelaksana'] = data['tglPelaksana']
                if 'jamMulai' in data:
                    s['jamMulai'] = data['jamMulai']
                if 'jamSelesai' in data:
                    s['jamSelesai'] = data['jamSelesai']
                if 'keterangan' in data:
                    s['keterangan'] = data['keterangan']
                if 'poSo' in data:
                    s['poSo'] = data['poSo']
                if 'status' in data:
                    s['status'] = data['status']
                
                # Update foto jika ada
                if data.get('foto'):
                    s['foto'] = data.get('foto')
                    s['fotoName'] = data.get('fotoName', s.get('fotoName'))
                    s['fotoUploadedAt'] = datetime.now().isoformat()
                    s['fotoStatus'] = "✅ Foto terupload"
                
                return jsonify({"success": True, "schedule": s})
        return jsonify({"success": False, "message": "Schedule not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/schedules/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """API menghapus schedule"""
    try:
        global SCHEDULES
        new_schedules = []
        for s in SCHEDULES:
            if s.get('id') != schedule_id:
                new_schedules.append(s)
        SCHEDULES = new_schedules
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/history')
def get_history():
    """API mendapatkan history"""
    return jsonify({"success": True, "history": history_data})

@app.route('/api/history/<int:history_id>', methods=['PUT'])
def update_history(history_id):
    """API mengupdate history"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
            
        for h in history_data:
            if h.get('id') == history_id:
                if 'suhu' in data:
                    h['suhu'] = data['suhu']
                if 'kelembaban' in data:
                    h['kelembaban'] = data['kelembaban']
                if 'tekanan' in data:
                    h['tekanan'] = data['tekanan']
                
                status = get_status(float(h.get('suhu', 0)), float(h.get('kelembaban', 0)))
                h['status'] = status['status']
                h['statusColor'] = status['color']
                h['statusBg'] = status['bg']
                return jsonify({"success": True, "history": h})
        return jsonify({"success": False, "message": "History not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/history/<int:history_id>', methods=['DELETE'])
def delete_history_item(history_id):
    """API menghapus history item"""
    try:
        global history_data
        new_history = []
        for h in history_data:
            if h.get('id') != history_id:
                new_history.append(h)
        history_data = new_history
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/history/delete-multiple', methods=['POST'])
def delete_multiple_history():
    """API menghapus multiple history items"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
            
        ids = data.get('ids', [])
        if not ids:
            return jsonify({"success": False, "message": "Tidak ada data yang dipilih"}), 400
            
        global history_data
        new_history = []
        for h in history_data:
            if h.get('id') not in ids:
                new_history.append(h)
        history_data = new_history
        return jsonify({"success": True, "deleted": len(ids)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/history/export/excel')
def export_history_excel():
    """Export history ke Excel"""
    try:
        if not history_data:
            return jsonify({"success": False, "message": "Tidak ada data"}), 400
        
        df = pd.DataFrame(history_data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='History')
        
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'history_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/history/export/csv')
def export_history_csv():
    """Export history ke CSV"""
    try:
        if not history_data:
            return jsonify({"success": False, "message": "Tidak ada data"}), 400
        
        df = pd.DataFrame(history_data)
        csv_data = df.to_csv(index=False)
        
        return send_file(
            BytesIO(csv_data.encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'history_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """API mendapatkan settings"""
    return jsonify({"success": True, "settings": settings})

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """API mengupdate settings"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
            
        if 'saveInterval' in data:
            settings['saveInterval'] = data['saveInterval']
        if 'suhuMin' in data:
            settings['suhuMin'] = data['suhuMin']
        if 'suhuMax' in data:
            settings['suhuMax'] = data['suhuMax']
        if 'kelembabanMin' in data:
            settings['kelembabanMin'] = data['kelembabanMin']
        if 'kelembabanMax' in data:
            settings['kelembabanMax'] = data['kelembabanMax']
            
        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/profile')
def get_profile():
    """API mendapatkan profile perusahaan"""
    return jsonify({"success": True, "profile": PROFILE})

@app.route('/api/profile', methods=['POST'])
def update_profile():
    """API mengupdate profile perusahaan"""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "message": "Data tidak valid"}), 400
            
        for key in PROFILE.keys():
            if key in data:
                PROFILE[key] = data[key]
        return jsonify({"success": True, "profile": PROFILE})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ============================================================
# API ROUTES - THINGSPEAK CONFIG
# ============================================================

@app.route('/api/thingspeak/config', methods=['GET', 'POST'])
def thingspeak_config_api():
    """API untuk mendapatkan dan menyimpan konfigurasi ThingSpeak"""
    global THINGSPEAK_CONFIG, THINGSPEAK_CHANNEL_ID, THINGSPEAK_API_KEY
    
    if request.method == 'POST':
        try:
            config = request.get_json()
            if config is None:
                return jsonify({"success": False, "message": "Data tidak valid"}), 400
            
            channel_id = config.get('channelId', '').strip()
            api_key = config.get('readApiKey', '').strip()
            
            if not channel_id or not api_key:
                return jsonify({"success": False, "message": "Channel ID dan API Key harus diisi"}), 400
            
            # Simpan config
            save_thingspeak_config(config)
            THINGSPEAK_CONFIG = config
            
            # Update global variables
            THINGSPEAK_CHANNEL_ID = channel_id
            THINGSPEAK_API_KEY = api_key
            
            return jsonify({
                "success": True, 
                "message": "Konfigurasi ThingSpeak berhasil disimpan permanen!",
                "config": config
            })
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    else:
        # GET - return config
        return jsonify(THINGSPEAK_CONFIG)

# ============================================================
# HEALTH CHECK & STATUS ENDPOINTS
# ============================================================

@app.route('/health')
def health_check():
    """Health check endpoint untuk monitoring"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "environment": ENV,
        "history_count": len(history_data),
        "schedules_count": len(SCHEDULES),
        "users_count": len(USERS),
        "thingspeak_configured": THINGSPEAK_CHANNEL_ID != 'YOUR_CHANNEL_ID'
    })

@app.route('/api/status')
def api_status():
    """Status API endpoint"""
    return jsonify({
        "success": True,
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "data_source": "ThingSpeak" if THINGSPEAK_CHANNEL_ID != 'YOUR_CHANNEL_ID' else "Simulasi",
        "environment": ENV,
        "port": PRODUCTION_PORT if IS_PRODUCTION else SERVER_PORT
    })

@app.route('/api/ping')
def ping():
    """Simple ping endpoint"""
    return jsonify({"pong": True, "timestamp": datetime.now().isoformat()})

# ============================================================
# THINGSPEAK CONFIG - SERVER SIDE
# ============================================================

THINGSPEAK_CONFIG_FILE = 'thingspeak_config.json'

def load_thingspeak_config():
    try:
        with open(THINGSPEAK_CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        default_config = {
            "channelId": "",
            "readApiKey": "",
            "fieldSuhu": "field1",
            "fieldKelembaban": "field2",
            "fieldTekanan": "field3"
        }
        save_thingspeak_config(default_config)
        return default_config

def save_thingspeak_config(config):
    with open(THINGSPEAK_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

@app.route('/api/thingspeak/config', methods=['GET', 'POST'])
def thingspeak_config_api():
    global THINGSPEAK_CONFIG, THINGSPEAK_CHANNEL_ID, THINGSPEAK_API_KEY
    
    if request.method == 'POST':
        try:
            config = request.get_json()
            if config is None:
                return jsonify({"success": False, "message": "Data tidak valid"}), 400
            
            channel_id = config.get('channelId', '').strip()
            api_key = config.get('readApiKey', '').strip()
            
            if not channel_id or not api_key:
                return jsonify({"success": False, "message": "Channel ID dan API Key harus diisi"}), 400
            
            save_thingspeak_config(config)
            THINGSPEAK_CONFIG = config
            THINGSPEAK_CHANNEL_ID = channel_id
            THINGSPEAK_API_KEY = api_key
            
            return jsonify({
                "success": True,
                "message": "Konfigurasi ThingSpeak berhasil disimpan permanen!",
                "config": config
            })
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    else:
        return jsonify(THINGSPEAK_CONFIG)

# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == '__main__':
    try:
        from config import print_config
        print_config()
    except:
        print("="*50)
        print("📋 CONFIGURATION")
        print("="*50)
        print(f"🌐 Server: {SERVER_HOST}:{SERVER_PORT}")
        print(f"🔧 Debug Mode: {DEBUG_MODE}")
        print(f"📡 ThingSpeak Channel: {THINGSPEAK_CHANNEL_ID}")
        print(f"📊 Save Interval: {settings.get('saveInterval', 60)} menit")
        print(f"🌡️ Suhu: {settings.get('suhuMin')}°C - {settings.get('suhuMax')}°C")
        print(f"💧 Kelembaban: {settings.get('kelembabanMin')}% - {settings.get('kelembabanMax')}%")
        print("="*50)
    
    print("\n🔑 Login Credentials:")
    print(f"   Username: {DEFAULT_USERNAME}")
    print(f"   Password: {DEFAULT_PASSWORD}")
    print(f"\n📡 History Data: {len(history_data)} records")
    print(f"📋 Schedules: {len(SCHEDULES)} schedules")
    print(f"👥 Users: {len(USERS)} users")
    print(f"⏱️ Save Interval: {settings.get('saveInterval', 5)} menit")
    print("\n📷 Fitur Foto Hasil Pekerjaan Teknisi:")
    print("   - Upload foto per schedule")
    print("   - Foto tampil di dashboard saat status Done")
    print("   - History aktivitas upload foto")
    print("\n" + "="*50)
    
    # Buat folder yang diperlukan
    Path("templates").mkdir(exist_ok=True)
    Path("static").mkdir(exist_ok=True)
    Path("uploads").mkdir(exist_ok=True)
    
    # ============================================================
    # KONFIGURASI PORT UNTUK PRODUCTION
    # ============================================================
    
    # Jika production, gunakan port 8084
    if IS_PRODUCTION or os.environ.get('PORT'):
        host = '0.0.0.0'
        port = int(os.environ.get('PORT', PRODUCTION_PORT))
        debug_mode = False
    else:
        host = SERVER_HOST
        port = SERVER_PORT
        debug_mode = DEBUG_MODE
    
    print(f"\n🚀 Server running on http://{host}:{port}")
    print(f"🌐 Environment: {'PRODUCTION' if IS_PRODUCTION else 'DEVELOPMENT'}")
    if IS_PRODUCTION:
        print(f"📌 Using port {port} (avoid conflict with port 8083)")
    print("="*50)
    
    app.run(
        debug=debug_mode,
        host=host,
        port=port
    )