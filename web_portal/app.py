"""
ESP32 Management Portal - Main Application
Kết nối với PostgreSQL database
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
import secrets
from datetime import datetime, timedelta
import os
from functools import wraps
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'esp32-management-secret-key-2024')

# Database configuration
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'database': os.environ.get('DB_NAME', 'esp32_management'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', '1234'),
    'port': os.environ.get('DB_PORT', '5432')
}

def get_db_connection():
    """Tạo kết nối database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def test_database_connection():
    """Kiểm tra kết nối database và tạo bảng cần thiết"""
    conn = get_db_connection()
    if not conn:
        print("❌ Không thể kết nối database!")
        return False
    
    try:
        with conn.cursor() as cur:
            # Test connection
            cur.execute("SELECT version()")
            version_result = cur.fetchone()
            if version_result:
                version = version_result[0]
                print(f"✅ Database connected: {version[:50]}...")
            
            # Tạo bảng device_commands nếu chưa có
            cur.execute("""
                CREATE TABLE IF NOT EXISTS device_commands (
                    id SERIAL PRIMARY KEY,
                    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                    command_type VARCHAR(50) NOT NULL,
                    command_data JSONB DEFAULT '{}',
                    executed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    executed_at TIMESTAMP NULL
                )
            """)
            
            # Tạo indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_device_commands_device_id ON device_commands(device_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_device_commands_executed ON device_commands(executed)")
            
            conn.commit()
            print("✅ Device commands table ready")
            
            # Kiểm tra tables
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]
            print(f"📋 Tables found: {', '.join(tables)}")
            
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Database test error: {e}")
        return False

def login_required(f):
    """Decorator kiểm tra đăng nhập"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Trang chủ - redirect đến dashboard nếu đã đăng nhập"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Trang đăng nhập"""
    if request.method == 'POST':
        phone_number = request.form['phone_number']
        password = request.form['password']
        
        conn = get_db_connection()
        if not conn:
            flash('Lỗi kết nối database', 'error')
            return render_template('login.html')
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, password_hash FROM users WHERE phone_number = %s",
                    (phone_number,)
                )
                user = cur.fetchone()
                
                if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                    session['user_id'] = user['id']
                    session['phone_number'] = phone_number
                    flash('Đăng nhập thành công!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Số điện thoại hoặc mật khẩu không đúng', 'error')
        except Exception as e:
            flash(f'Lỗi đăng nhập: {e}', 'error')
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Trang đăng ký"""
    if request.method == 'POST':
        phone_number = request.form['phone_number']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Mật khẩu xác nhận không khớp', 'error')
            return render_template('register.html')
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        conn = get_db_connection()
        if not conn:
            flash('Lỗi kết nối database', 'error')
            return render_template('register.html')
        
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (phone_number, password_hash) VALUES (%s, %s)",
                    (phone_number, password_hash)
                )
                conn.commit()
                flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
                return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            flash('Số điện thoại đã được sử dụng', 'error')
        except Exception as e:
            flash(f'Lỗi đăng ký: {e}', 'error')
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    """Đăng xuất"""
    session.clear()
    flash('Đã đăng xuất thành công', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard chính - hiển thị danh sách thiết bị"""
    conn = get_db_connection()
    if not conn:
        flash('Lỗi kết nối database', 'error')
        return render_template('dashboard.html', devices=[])
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Lấy danh sách thiết bị của user
            cur.execute("""
                SELECT d.*, w.wifi_name, w.wifi_password 
                FROM devices d 
                LEFT JOIN wifi_configs w ON d.id = w.device_id AND w.is_active = true
                WHERE d.user_id = %s 
                ORDER BY d.created_at DESC
            """, (session['user_id'],))
            devices = cur.fetchall()
            
            print(f"🔍 Dashboard: Found {len(devices)} devices for user {session['user_id']}")
            for device in devices:
                print(f"   📱 {device['device_name']} ({device['device_id']}) - {device.get('status', 'unknown')}")
            
        return render_template('dashboard.html', devices=devices)
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
        flash(f'Lỗi tải dữ liệu: {e}', 'error')
        return render_template('dashboard.html', devices=[])
    finally:
        conn.close()

@app.route('/add_device', methods=['GET', 'POST'])
@login_required
def add_device():
    """Thêm thiết bị mới"""
    if request.method == 'POST':
        device_name = request.form['device_name']
        device_id = request.form['device_id']
        wifi_name = request.form['wifi_name']
        wifi_password = request.form['wifi_password']
        
        conn = get_db_connection()
        if not conn:
            flash('Lỗi kết nối database', 'error')
            return render_template('add_device.html')
        
        try:
            with conn.cursor() as cur:
                # Thêm thiết bị
                cur.execute("""
                    INSERT INTO devices (user_id, device_name, device_id, status) 
                    VALUES (%s, %s, %s, 'offline') RETURNING id
                """, (session['user_id'], device_name, device_id))
                
                result = cur.fetchone()
                device_db_id = result[0] if result else None
                
                if device_db_id:
                    # Thêm cấu hình WiFi
                    cur.execute("""
                        INSERT INTO wifi_configs (device_id, wifi_name, wifi_password) 
                        VALUES (%s, %s, %s)
                    """, (device_db_id, wifi_name, wifi_password))
                    
                    conn.commit()
                    print(f"✅ Device added: {device_name} ({device_id}) for user {session['user_id']}")
                    flash('Thêm thiết bị thành công!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Lỗi tạo thiết bị', 'error')
        except psycopg2.IntegrityError:
            flash('Device ID đã tồn tại', 'error')
        except Exception as e:
            flash(f'Lỗi thêm thiết bị: {e}', 'error')
        finally:
            conn.close()
    
    return render_template('add_device.html')

@app.route('/device/<int:device_id>')
@login_required
def device_detail(device_id):
    """Chi tiết thiết bị và lịch sử text"""
    conn = get_db_connection()
    if not conn:
        flash('Lỗi kết nối database', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Kiểm tra quyền truy cập thiết bị
            cur.execute("""
                SELECT d.*, w.wifi_name, w.wifi_password 
                FROM devices d 
                LEFT JOIN wifi_configs w ON d.id = w.device_id AND w.is_active = true
                WHERE d.id = %s AND d.user_id = %s
            """, (device_id, session['user_id']))
            
            device = cur.fetchone()
            if not device:
                flash('Không tìm thấy thiết bị', 'error')
                return redirect(url_for('dashboard'))
            
            # Lấy lịch sử text 1 ngày gần nhất
            cur.execute("""
                SELECT * FROM text_history 
                WHERE device_id = %s AND recorded_at >= %s 
                ORDER BY recorded_at DESC
                LIMIT 100
            """, (device_id, datetime.now() - timedelta(days=1)))
            
            text_history = cur.fetchall()
            
        return render_template('device_detail.html', device=device, text_history=text_history)
    except Exception as e:
        flash(f'Lỗi tải chi tiết thiết bị: {e}', 'error')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

@app.route('/update_wifi/<int:device_id>', methods=['POST'])
@login_required
def update_wifi(device_id):
    """Cập nhật cấu hình WiFi cho thiết bị"""
    wifi_name = request.form['wifi_name']
    wifi_password = request.form['wifi_password']
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Lỗi kết nối database'})
    
    try:
        with conn.cursor() as cur:
            # Kiểm tra quyền truy cập
            cur.execute("""
                SELECT id FROM devices WHERE id = %s AND user_id = %s
            """, (device_id, session['user_id']))
            
            if not cur.fetchone():
                return jsonify({'success': False, 'message': 'Không có quyền truy cập'})
            
            # Vô hiệu hóa config cũ
            cur.execute("""
                UPDATE wifi_configs SET is_active = false WHERE device_id = %s
            """, (device_id,))
            
            # Thêm config mới
            cur.execute("""
                INSERT INTO wifi_configs (device_id, wifi_name, wifi_password) 
                VALUES (%s, %s, %s)
            """, (device_id, wifi_name, wifi_password))
            
            conn.commit()
            
            return jsonify({'success': True, 'message': 'Cập nhật WiFi thành công'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi cập nhật: {e}'})
    finally:
        conn.close()

# ===== API ENDPOINTS CHO ESP32 SERVER =====

@app.route('/api/device/register', methods=['POST'])
def api_device_register():
    """API để ESP32 server đăng ký thiết bị khi kết nối"""
    data = request.get_json()
    device_id = data.get('device_id')
    esp32_ip = data.get('esp32_ip', 'unknown')
    client_ip = data.get('client_ip', 'unknown')
    mac_address = data.get('mac_address', 'unknown')
    rssi = data.get('rssi', 0)
    
    print(f"🔍 Registration request: {device_id}")
    print(f"   📍 ESP32 IP: {esp32_ip}")
    print(f"   🌐 Client IP: {client_ip}")
    print(f"   🔗 MAC: {mac_address}")
    print(f"   📶 RSSI: {rssi}")
    
    if not device_id:
        return jsonify({'success': False, 'message': 'Missing device_id'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Kiểm tra thiết bị có tồn tại trong database không
            cur.execute("SELECT id, device_name, user_id FROM devices WHERE device_id = %s", (device_id,))
            existing_device = cur.fetchone()
            
            if existing_device:
                # Cập nhật thông tin thiết bị hiện có
                cur.execute("""
                    UPDATE devices SET 
                        status = 'online', 
                        last_seen = CURRENT_TIMESTAMP,
                        esp32_ip = %s,
                        client_ip = %s,
                        mac_address = %s,
                        rssi = %s
                    WHERE device_id = %s 
                    RETURNING id, device_name
                """, (esp32_ip, client_ip, mac_address, rssi, device_id))
                
                result = cur.fetchone()
                conn.commit()
                print(f"✅ Device '{result['device_name']}' ({device_id}) is now online")
                return jsonify({
                    'success': True, 
                    'message': f"Device {result['device_name']} registered successfully"
                })
            else:
                # Thiết bị chưa được thêm vào web portal
                print(f"⚠️ Device {device_id} not found in database. Please add it via web portal first.")
                return jsonify({
                    'success': False, 
                    'message': 'Device not found. Please add device via web portal first.'
                })
                
    except Exception as e:
        print(f"❌ Device registration error: {e}")
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/api/device/disconnect', methods=['POST'])
def api_device_disconnect():
    """API để ESP32 server báo thiết bị ngắt kết nối"""
    data = request.get_json()
    device_id = data.get('device_id')
    
    if not device_id:
        return jsonify({'success': False, 'message': 'Missing device_id'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    
    try:
        with conn.cursor() as cur:
            # Cập nhật trạng thái offline
            cur.execute("""
                UPDATE devices SET status = 'offline' WHERE device_id = %s
            """, (device_id,))
            conn.commit()
            print(f"📴 Device {device_id} is now offline")
            
        return jsonify({'success': True, 'message': 'Device disconnected'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/api/text/save', methods=['POST'])
def api_save_text():
    """API để lưu text transcript từ ESP32 server"""
    data = request.get_json()
    device_id = data.get('device_id')
    transcript = data.get('transcript')
    is_final = data.get('is_final', False)
    
    if not device_id or not transcript:
        return jsonify({'success': False, 'message': 'Missing required fields'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    
    try:
        with conn.cursor() as cur:
            # Lấy device database ID
            cur.execute("SELECT id, device_name FROM devices WHERE device_id = %s", (device_id,))
            device_row = cur.fetchone()
            
            if not device_row:
                return jsonify({'success': False, 'message': 'Device not found'})
            
            device_db_id = device_row[0]
            device_name = device_row[1]
            
            # Lưu transcript
            cur.execute("""
                INSERT INTO text_history (device_id, transcript_text, is_final) 
                VALUES (%s, %s, %s)
            """, (device_db_id, transcript, is_final))
            
            conn.commit()
            print(f"✅ Text saved for {device_name}: {transcript[:50]}...")
            return jsonify({'success': True, 'message': 'Text saved successfully'})
    except Exception as e:
        print(f"❌ Text save error: {e}")
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/api/device/heartbeat', methods=['POST'])
def api_device_heartbeat():
    """API để ESP32 server gửi heartbeat"""
    data = request.get_json()
    device_id = data.get('device_id')
    
    if not device_id:
        return jsonify({'success': False, 'message': 'Missing device_id'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    
    try:
        with conn.cursor() as cur:
            # Cập nhật last_seen để duy trì trạng thái online
            cur.execute("""
                UPDATE devices SET last_seen = CURRENT_TIMESTAMP 
                WHERE device_id = %s
            """, (device_id,))
            conn.commit()
            
        return jsonify({'success': True, 'message': 'Heartbeat received'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/api/device/status/<device_id>')
@login_required
def api_device_status(device_id):
    """API lấy trạng thái thiết bị realtime"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Kiểm tra quyền truy cập và lấy thông tin thiết bị
            cur.execute("""
                SELECT d.*, w.wifi_name 
                FROM devices d 
                LEFT JOIN wifi_configs w ON d.id = w.device_id AND w.is_active = true
                WHERE d.id = %s AND d.user_id = %s
            """, (device_id, session['user_id']))
            
            device = cur.fetchone()
            if not device:
                return jsonify({'success': False, 'message': 'Device not found'})
            
            # Kiểm tra thiết bị có online không (trong vòng 60 giây)
            is_online = False
            if device['last_seen']:
                time_diff = datetime.now() - device['last_seen']
                is_online = time_diff.total_seconds() < 60
            
            return jsonify({
                'success': True,
                'device': {
                    'id': device['id'],
                    'name': device['device_name'],
                    'device_id': device['device_id'],
                    'status': 'online' if is_online else 'offline',
                    'wifi_name': device['wifi_name'],
                    'esp32_ip': device.get('esp32_ip'),
                    'rssi': device.get('rssi'),
                    'last_seen': device['last_seen'].isoformat() if device['last_seen'] else None
                }
            })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/device/<int:device_id>/text-history')
@login_required
def api_device_text_history(device_id):
    """API lấy lịch sử text của thiết bị"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'})
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Kiểm tra quyền truy cập thiết bị
            cur.execute("""
                SELECT id FROM devices WHERE id = %s AND user_id = %s
            """, (device_id, session['user_id']))
            
            if not cur.fetchone():
                return jsonify({'success': False, 'message': 'Device not found'})
            
            # Lấy lịch sử text 24 giờ gần nhất, chỉ lấy final transcript
            cur.execute("""
                SELECT transcript_text, recorded_at, is_final
                FROM text_history 
                WHERE device_id = %s AND recorded_at >= %s
                AND is_final = true
                ORDER BY recorded_at DESC
                LIMIT 20
            """, (device_id, datetime.now() - timedelta(hours=24)))
            
            text_history = cur.fetchall()
            
            # Convert to list of dicts for JSON serialization
            text_list = []
            for record in text_history:
                text_list.append({
                    'transcript_text': record['transcript_text'],
                    'recorded_at': record['recorded_at'].isoformat(),
                    'is_final': record['is_final']
                })
            
            return jsonify({
                'success': True,
                'text_history': text_list,
                'count': len(text_list)
            })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/delete_device/<int:device_id>', methods=['POST'])
@login_required
def delete_device(device_id):
    """Xóa thiết bị"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Lỗi kết nối database'})
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Kiểm tra quyền truy cập
            cur.execute("""
                SELECT device_name FROM devices WHERE id = %s AND user_id = %s
            """, (device_id, session['user_id']))
            
            device = cur.fetchone()
            if not device:
                return jsonify({'success': False, 'message': 'Không có quyền truy cập thiết bị này'})
            
            # Xóa thiết bị (CASCADE sẽ tự động xóa wifi_configs và text_history)
            cur.execute("DELETE FROM devices WHERE id = %s", (device_id,))
            conn.commit()
            
            print(f"🗑️ Device deleted: {device['device_name']} (ID: {device_id})")
            return jsonify({
                'success': True, 
                'message': f'Đã xóa thiết bị {device["device_name"]} thành công'
            })
            
    except Exception as e:
        print(f"❌ Delete device error: {e}")
        return jsonify({'success': False, 'message': f'Lỗi xóa thiết bị: {e}'})
    finally:
        conn.close()

@app.route('/api/device/wifi-config/<device_id>')
def api_get_wifi_config(device_id):
    """API để ESP32 lấy cấu hình WiFi mới"""
    print(f"🔍 ESP32 requesting WiFi config for device: {device_id}")
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Lấy cấu hình WiFi active cho device
            cur.execute("""
                SELECT wc.wifi_name, wc.wifi_password, wc.created_at
                FROM wifi_configs wc
                JOIN devices d ON wc.device_id = d.id
                WHERE d.device_id = %s AND wc.is_active = true
                ORDER BY wc.created_at DESC
                LIMIT 1
            """, (device_id,))
            
            wifi_config = cur.fetchone()
            
            if wifi_config:
                print(f"✅ Found WiFi config: {wifi_config['wifi_name']}")
                return jsonify({
                    'success': True,
                    'wifi_name': wifi_config['wifi_name'],
                    'wifi_password': wifi_config['wifi_password'],
                    'updated_at': wifi_config['created_at'].isoformat()
                })
            else:
                print(f"❌ No WiFi config found for device: {device_id}")
                return jsonify({
                    'success': False,
                    'message': 'No WiFi config found'
                })
                
    except Exception as e:
        print(f"❌ Error getting WiFi config: {e}")
        return jsonify({'success': False, 'message': f'Error: {e}'})
    finally:
        conn.close()

@app.route('/api/device/wifi-status', methods=['POST'])
def api_wifi_status():
    """API để ESP32 báo cáo trạng thái kết nối WiFi"""
    try:
        data = request.get_json()
        device_id = data.get('device_id')
        wifi_status = data.get('status')  # 'connected', 'failed', 'connecting'
        wifi_name = data.get('wifi_name')
        rssi = data.get('rssi', 0)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})
        
        with conn.cursor() as cur:
            # Cập nhật trạng thái thiết bị
            cur.execute("""
                UPDATE devices 
                SET status = %s, rssi = %s, last_seen = CURRENT_TIMESTAMP
                WHERE device_id = %s
            """, (wifi_status, rssi, device_id))
            
            conn.commit()
            
        return jsonify({'success': True, 'message': 'WiFi status updated'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {e}'})
    finally:
        if conn:
            conn.close()

@app.route('/api/device/commands/<device_id>')
def api_get_device_commands(device_id):
    """API để ESP32 lấy các lệnh cần thực hiện"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Database connection error'})
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Lấy device database ID
            cur.execute("SELECT id FROM devices WHERE device_id = %s", (device_id,))
            device_row = cur.fetchone()
            
            if not device_row:
                return jsonify({'success': False, 'message': 'Device not found'})
            
            device_db_id = device_row['id']
            
            # Lấy lệnh chưa thực hiện
            cur.execute("""
                SELECT id, command_type, command_data, created_at
                FROM device_commands 
                WHERE device_id = %s AND executed = false
                ORDER BY created_at ASC
                LIMIT 1
            """, (device_db_id,))
            
            command = cur.fetchone()
            
            if command:
                print(f"📋 Found pending command for {device_id}: {command['command_type']}")
                
                return jsonify({
                    'success': True,
                    'has_command': True,
                    'command_id': command['id'],
                    'command_data': command['command_data'],
                    'created_at': command['created_at'].isoformat()
                })
            else:
                return jsonify({
                    'success': True,
                    'has_command': False,
                    'message': 'No pending commands'
                })
                
    except Exception as e:
        print(f"❌ Get commands error: {e}")
        return jsonify({'success': False, 'message': f'Error: {e}'})
    finally:
        conn.close()

@app.route('/api/device/send-command', methods=['POST'])
def api_send_device_command():
    """API để gửi lệnh đến ESP32"""
    try:
        data = request.get_json()
        device_id = data.get('device_id')  # ESP32 device ID
        command_type = data.get('command_type')  # 'reset', 'wifi_update'
        command_data = data.get('command_data', {})  # Dữ liệu lệnh
        
        if not device_id or not command_type:
            return jsonify({
                'success': False,
                'message': 'device_id and command_type are required'
            })
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})
        
        with conn.cursor() as cur:
            # Lấy device database ID
            cur.execute("SELECT id FROM devices WHERE device_id = %s", (device_id,))
            device_row = cur.fetchone()
            
            if not device_row:
                return jsonify({'success': False, 'message': 'Device not found'})
            
            device_db_id = device_row[0]
            
            # Thêm lệnh vào queue
            cur.execute("""
                INSERT INTO device_commands (device_id, command_type, command_data)
                VALUES (%s, %s, %s)
            """, (device_db_id, command_type, json.dumps(command_data)))
            
            conn.commit()
            
            print(f"📤 Command sent to {device_id}: {command_type}")
            return jsonify({
                'success': True,
                'message': f'Command {command_type} sent to device'
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {e}'})
    finally:
        if conn:
            conn.close()

# ===== WIFI MANAGEMENT ROUTES =====

@app.route('/wifi-manager')
@login_required
def wifi_manager():
    """Trang quản lý WiFi từ xa"""
    return render_template('wifi_manager.html')

@app.route('/api/wifi/update-config', methods=['POST'])
@login_required
def api_wifi_update_config():
    """API cập nhật cấu hình WiFi từ xa"""
    try:
        data = request.get_json()
        device_id = data.get('device_id')  # ESP32 device ID (string)
        wifi_name = data.get('wifi_name')
        wifi_password = data.get('wifi_password', '')
        
        if not device_id or not wifi_name:
            return jsonify({
                'success': False,
                'message': 'device_id and wifi_name are required'
            }), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database connection error'
            }), 500
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Tìm device trong database
            cur.execute("""
                SELECT d.id, d.device_name, d.user_id 
                FROM devices d 
                WHERE d.device_id = %s
            """, (device_id,))
            
            device = cur.fetchone()
            if not device:
                return jsonify({
                    'success': False,
                    'message': 'Device not found'
                }), 404
            
            # Kiểm tra quyền truy cập
            if device['user_id'] != session['user_id']:
                return jsonify({
                    'success': False,
                    'message': 'Access denied'
                }), 403
            
            # Vô hiệu hóa config cũ
            cur.execute("""
                UPDATE wifi_configs SET is_active = false 
                WHERE device_id = %s
            """, (device['id'],))
            
            # Thêm config mới
            cur.execute("""
                INSERT INTO wifi_configs (device_id, wifi_name, wifi_password, is_active) 
                VALUES (%s, %s, %s, true)
            """, (device['id'], wifi_name, wifi_password))
            
            # Gửi lệnh cập nhật WiFi đến ESP32
            cur.execute("""
                INSERT INTO device_commands (device_id, command_type, command_data)
                VALUES (%s, %s, %s)
            """, (device['id'], 'wifi_update', json.dumps({
                'wifi_name': wifi_name,
                'wifi_password': wifi_password
            })))
            
            conn.commit()
            
            print(f"📡 WiFi config updated and command sent to {device['device_name']}: {wifi_name}")
            return jsonify({
                'success': True,
                'message': f'WiFi config updated for {device["device_name"]}. Device will update automatically.',
                'device_name': device['device_name']
            })
            
    except Exception as e:
        print(f"❌ WiFi config update error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error updating WiFi config: {str(e)}'
        }), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/wifi/list-configs')
@login_required
def api_wifi_list_configs():
    """API liệt kê tất cả cấu hình WiFi của user"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database connection error'
            }), 500
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Lấy tất cả thiết bị và WiFi config của user
            cur.execute("""
                SELECT d.device_id, d.device_name, d.status, d.last_seen,
                       wc.wifi_name, wc.created_at as config_time, wc.is_active
                FROM devices d
                LEFT JOIN wifi_configs wc ON d.id = wc.device_id AND wc.is_active = true
                WHERE d.user_id = %s
                ORDER BY d.device_name
            """, (session['user_id'],))
            
            devices = cur.fetchall()
            
            # Format response
            configs = {}
            for device in devices:
                # Kiểm tra thiết bị có online không (trong vòng 60 giây)
                is_online = False
                if device['last_seen']:
                    time_diff = datetime.now() - device['last_seen']
                    is_online = time_diff.total_seconds() < 60
                
                configs[device['device_id']] = {
                    'device_name': device['device_name'],
                    'wifi_name': device['wifi_name'] or '',
                    'status': 'online' if is_online else 'offline',
                    'config_time': device['config_time'].isoformat() if device['config_time'] else '',
                    'is_active': device['is_active'] or False
                }
            
            return jsonify({
                'success': True,
                'configs': configs,
                'total': len(configs)
            })
            
    except Exception as e:
        print(f"❌ List WiFi configs error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error listing configs: {str(e)}'
        }), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/wifi/reset-config/<device_id>', methods=['POST'])
@login_required
def api_wifi_reset_config(device_id):
    """API reset cấu hình WiFi cho thiết bị"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database connection error'
            }), 500
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Tìm device và kiểm tra quyền truy cập
            cur.execute("""
                SELECT d.id, d.device_name, d.user_id 
                FROM devices d 
                WHERE d.device_id = %s
            """, (device_id,))
            
            device = cur.fetchone()
            if not device:
                return jsonify({
                    'success': False,
                    'message': 'Device not found'
                }), 404
            
            # Kiểm tra quyền truy cập
            if device['user_id'] != session['user_id']:
                return jsonify({
                    'success': False,
                    'message': 'Access denied'
                }), 403
            
            # Vô hiệu hóa tất cả WiFi config của device
            cur.execute("""
                UPDATE wifi_configs SET is_active = false 
                WHERE device_id = %s
            """, (device['id'],))
            
            # Gửi lệnh reset đến ESP32 (sẽ được poll mỗi 30 giây)
            cur.execute("""
                INSERT INTO device_commands (device_id, command_type, command_data)
                VALUES (%s, %s, %s)
            """, (device['id'], 'reset', json.dumps({'type': 'wifi_reset'})))
            
            conn.commit()
            
            print(f"🔄 WiFi config reset and reset command sent to {device['device_name']}")
            return jsonify({
                'success': True,
                'message': f'Reset command sent to {device["device_name"]}. Device will restart automatically.'
            })
            
    except Exception as e:
        print(f"❌ WiFi config reset error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error resetting config: {str(e)}'
        }), 500
    finally:
        if conn:
            conn.close()

@app.route('/test')
def test():
    """Test endpoint"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'status': 'ERROR', 'message': 'Database connection failed'})
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            users_result = cur.fetchone()
            users_count = users_result[0] if users_result else 0
            
            cur.execute("SELECT COUNT(*) FROM devices")
            devices_result = cur.fetchone()
            devices_count = devices_result[0] if devices_result else 0
            
            # Kiểm tra device_commands table
            cur.execute("SELECT COUNT(*) FROM device_commands")
            commands_result = cur.fetchone()
            commands_count = commands_result[0] if commands_result else 0
            
            # Lấy 5 lệnh gần nhất
            cur.execute("""
                SELECT dc.command_type, dc.executed, dc.created_at, d.device_id
                FROM device_commands dc
                JOIN devices d ON dc.device_id = d.id
                ORDER BY dc.created_at DESC
                LIMIT 5
            """)
            recent_commands = cur.fetchall()
            
        return jsonify({
            'status': 'OK',
            'message': 'ESP32 Management Portal is running with PostgreSQL!',
            'timestamp': datetime.now().isoformat(),
            'database': DB_CONFIG['database'],
            'users_count': users_count,
            'devices_count': devices_count,
            'commands_count': commands_count,
            'recent_commands': [dict(cmd) for cmd in recent_commands]
        })
    except Exception as e:
        return jsonify({'status': 'ERROR', 'message': f'Database error: {e}'})
    finally:
        conn.close()

@app.route('/test-command/<device_id>')
def test_command(device_id):
    """Test gửi lệnh reset đến device"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})
        
        with conn.cursor() as cur:
            # Lấy device database ID
            cur.execute("SELECT id, device_name FROM devices WHERE device_id = %s", (device_id,))
            device_row = cur.fetchone()
            
            if not device_row:
                return jsonify({'success': False, 'message': 'Device not found'})
            
            device_db_id = device_row[0]
            device_name = device_row[1]
            
            # Thêm lệnh reset test
            cur.execute("""
                INSERT INTO device_commands (device_id, command_type, command_data)
                VALUES (%s, %s, %s)
            """, (device_db_id, 'reset', json.dumps({'type': 'test_reset'})))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Test reset command sent to {device_name}',
                'device_id': device_id
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {e}'})
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print("🚀 Starting ESP32 Management Portal...")
    print(f"📊 Database: {DB_CONFIG['database']} @ {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print("📱 Web Portal: http://localhost:5000")
    print("-" * 60)
    
    # Test database connection
    if test_database_connection():
        print("✅ Database ready!")
        print("🌐 Starting web server...")
        app.run(debug=True, host='0.0.0.0', port=5000)
    else:
        print("❌ Database connection failed!")
        print("💡 Kiểm tra lại:")
        print("   - PostgreSQL đang chạy")
        print("   - Thông tin kết nối trong file .env")
        print("   - Database 'esp32_management' đã được tạo")
app.route('/api/device/send-command', methods=['POST'])
@login_required
def api_send_device_command():
    """API để gửi lệnh đến ESP32"""
    try:
        data = request.get_json()
        device_db_id = data.get('device_id')  # Database device ID
        command_type = data.get('command_type')
        command_data = data.get('command_data', {})
        
        if not device_db_id or not command_type:
            return jsonify({'success': False, 'message': 'Missing required fields'})
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})
        
        with conn.cursor() as cur:
            # Kiểm tra quyền truy cập thiết bị
            cur.execute("""
                SELECT device_name FROM devices 
                WHERE id = %s AND user_id = %s
            """, (device_db_id, session['user_id']))
            
            device = cur.fetchone()
            if not device:
                return jsonify({'success': False, 'message': 'Device not found or access denied'})
            
            # Thêm lệnh vào queue
            cur.execute("""
                INSERT INTO device_commands (device_id, command_type, command_data)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (device_db_id, command_type, json.dumps(command_data)))
            
            command_id = cur.fetchone()[0]
            conn.commit()
            
            print(f"📤 Command queued: {command_type} for device {device[0]} (ID: {command_id})")
            
            return jsonify({
                'success': True, 
                'message': f'Command {command_type} queued successfully',
                'command_id': command_id
            })
            
    except Exception as e:
        print(f"❌ Send command error: {e}")
        return jsonify({'success': False, 'message': f'Error: {e}'})
    finally:
        if conn:
            conn.close()

# Route để gửi lệnh từ web interface
@app.route('/send_command/<int:device_id>', methods=['POST'])
@login_required
def send_command_to_device(device_id):
    """Gửi lệnh đến thiết bị từ web interface"""
    try:
        command_type = request.form.get('command_type')
        
        if command_type == 'wifi_update':
            wifi_name = request.form.get('wifi_name')
            wifi_password = request.form.get('wifi_password')
            
            if not wifi_name:
                flash('Tên WiFi không được để trống', 'error')
                return redirect(url_for('device_detail', device_id=device_id))
            
            command_data = {
                'wifi_name': wifi_name,
                'wifi_password': wifi_password
            }
        elif command_type == 'reset':
            command_data = {
                'type': 'wifi_reset'
            }
        else:
            flash('Loại lệnh không hợp lệ', 'error')
            return redirect(url_for('device_detail', device_id=device_id))
        
        # Gửi lệnh qua API
        response = api_send_device_command()
        if hasattr(response, 'get_json'):
            result = response.get_json()
            if result.get('success'):
                flash(f'Đã gửi lệnh {command_type} thành công!', 'success')
            else:
                flash(f'Lỗi gửi lệnh: {result.get("message")}', 'error')
        else:
            # Gọi trực tiếp function
            from flask import request as flask_request
            original_json = flask_request.get_json
            flask_request.get_json = lambda: {
                'device_id': device_id,
                'command_type': command_type,
                'command_data': command_data
            }
            
            result = api_send_device_command()
            flask_request.get_json = original_json
            
            if isinstance(result, tuple):
                result_data = result[0].get_json()
            else:
                result_data = result.get_json()
                
            if result_data.get('success'):
                flash(f'Đã gửi lệnh {command_type} thành công!', 'success')
            else:
                flash(f'Lỗi gửi lệnh: {result_data.get("message")}', 'error')
        
        return redirect(url_for('device_detail', device_id=device_id))
        
    except Exception as e:
        print(f"❌ Send command from web error: {e}")
        flash(f'Lỗi gửi lệnh: {e}', 'error')
        return redirect(url_for('device_detail', device_id=device_id))

if __name__ == '__main__':
    print("🚀 Starting ESP32 Management Portal...")
    
    # Test database connection
    if test_database_connection():
        print("✅ Database connection successful")
        print("🌐 Starting Flask server on http://localhost:5000")
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        print("❌ Database connection failed. Please check your configuration.")
        print("💡 Make sure PostgreSQL is running and credentials are correct.")


# ============================================================
# Command Management Routes
# ============================================================

@app.route('/send_command/<int:device_id>', methods=['POST'])
@login_required
def send_command_to_device(device_id):
    """Gửi lệnh đến thiết bị từ web interface"""
    try:
        command_type = request.form.get('command_type')
        
        conn = get_db_connection()
        if not conn:
            flash('Lỗi kết nối database', 'error')
            return redirect(url_for('device_detail', device_id=device_id))
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Kiểm tra quyền truy cập
            cur.execute("""
                SELECT id, device_name FROM devices 
                WHERE id = %s AND user_id = %s
            """, (device_id, session['user_id']))
            
            device = cur.fetchone()
            if not device:
                flash('Không có quyền truy cập thiết bị này', 'error')
                return redirect(url_for('dashboard'))
            
            # Xử lý theo loại lệnh
            if command_type == 'wifi_update':
                wifi_name = request.form.get('wifi_name')
                wifi_password = request.form.get('wifi_password')
                
                if not wifi_name:
                    flash('Tên WiFi không được để trống', 'error')
                    return redirect(url_for('device_detail', device_id=device_id))
                
                command_data = {
                    'wifi_name': wifi_name,
                    'wifi_password': wifi_password
                }
                
                # Thêm lệnh vào queue
                cur.execute("""
                    INSERT INTO device_commands (device_id, command_type, command_data)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (device_id, 'wifi_update', json.dumps(command_data)))
                
                command_id = cur.fetchone()['id']
                conn.commit()
                
                print(f"📤 WiFi update command queued: ID={command_id}, Device={device['device_name']}")
                flash(f'Đã gửi lệnh cập nhật WiFi đến {device["device_name"]}!', 'success')
                
            elif command_type == 'reset':
                command_data = {'type': 'wifi_reset'}
                
                # Thêm lệnh vào queue
                cur.execute("""
                    INSERT INTO device_commands (device_id, command_type, command_data)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (device_id, 'reset', json.dumps(command_data)))
                
                command_id = cur.fetchone()['id']
                conn.commit()
                
                print(f"📤 Reset command queued: ID={command_id}, Device={device['device_name']}")
                flash(f'Đã gửi lệnh reset đến {device["device_name"]}!', 'success')
                
            else:
                flash('Loại lệnh không hợp lệ', 'error')
        
        return redirect(url_for('device_detail', device_id=device_id))
        
    except Exception as e:
        print(f"❌ Send command error: {e}")
        flash(f'Lỗi gửi lệnh: {e}', 'error')
        return redirect(url_for('device_detail', device_id=device_id))
    finally:
        if conn:
            conn.close()

@app.route('/api/device/send-command', methods=['POST'])
@login_required
def api_send_device_command():
    """API để gửi lệnh đến ESP32"""
    try:
        data = request.get_json()
        device_db_id = data.get('device_id')  # Database device ID
        command_type = data.get('command_type')
        command_data = data.get('command_data', {})
        
        if not device_db_id or not command_type:
            return jsonify({'success': False, 'message': 'Missing required fields'})
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})
        
        with conn.cursor() as cur:
            # Kiểm tra quyền truy cập thiết bị
            cur.execute("""
                SELECT device_name FROM devices 
                WHERE id = %s AND user_id = %s
            """, (device_db_id, session['user_id']))
            
            device = cur.fetchone()
            if not device:
                return jsonify({'success': False, 'message': 'Device not found or access denied'})
            
            # Thêm lệnh vào queue
            cur.execute("""
                INSERT INTO device_commands (device_id, command_type, command_data)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (device_db_id, command_type, json.dumps(command_data)))
            
            command_id = cur.fetchone()[0]
            conn.commit()
            
            print(f"📤 Command queued: {command_type} for device {device[0]} (ID: {command_id})")
            
            return jsonify({
                'success': True, 
                'message': f'Command {command_type} queued successfully',
                'command_id': command_id
            })
            
    except Exception as e:
        print(f"❌ Send command error: {e}")
        return jsonify({'success': False, 'message': f'Error: {e}'})
    finally:
        if conn:
            conn.close()

@app.route('/api/device/command-executed', methods=['POST'])
def api_command_executed():
    """API để ESP32 báo cáo lệnh đã được thực hiện"""
    try:
        data = request.get_json()
        command_id = data.get('command_id')
        device_id = data.get('device_id')  # ESP32 device ID
        
        if not command_id or not device_id:
            return jsonify({'success': False, 'message': 'Missing required fields'})
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection error'})
        
        with conn.cursor() as cur:
            # Cập nhật trạng thái lệnh đã thực hiện
            cur.execute("""
                UPDATE device_commands 
                SET executed = true, executed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING command_type
            """, (command_id,))
            
            result = cur.fetchone()
            if result:
                command_type = result[0]
                conn.commit()
                print(f"✅ Command {command_type} (ID: {command_id}) marked as executed by {device_id}")
                
                return jsonify({
                    'success': True, 
                    'message': f'Command {command_type} marked as executed'
                })
            else:
                return jsonify({'success': False, 'message': 'Command not found'})
                
    except Exception as e:
        print(f"❌ Command executed error: {e}")
        return jsonify({'success': False, 'message': f'Error: {e}'})
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print("🚀 Starting ESP32 Management Portal...")
    
    # Test database connection
    if test_database_connection():
        print("✅ Database connection successful")
        print("🌐 Starting Flask server on http://localhost:5000")
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        print("❌ Database connection failed. Please check your configuration.")
        print("💡 Make sure PostgreSQL is running and credentials are correct.")
