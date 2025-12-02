"""
Server Python nhận realtime audio stream từ ESP32 và xử lý với Speechmatics API
CHỈ KẾT NỐI VỚI THIẾT BỊ ĐÃ ĐƯỢC THÊM VÀO WEB PORTAL
"""

import speechmatics
from httpx import HTTPStatusError
import asyncio
import websockets
import json 
import base64
from datetime import datetime
import requests
import os
import sys

"              ./start_all.bat      "


# API Key Speechmatics
API_KEY = "KtVYXdwFgjSeUzcjYguadk7drQKdjPgj"
LANGUAGE = "vi"
CONNECTION_URL = f"wss://eu2.rt.speechmatics.com/v2/{LANGUAGE}"

# Cấu hình audio - Cân bằng tốc độ và chất lượng
SAMPLE_RATE = 16000
CHUNK_SIZE = 768

# Cấu hình tối ưu hóa heartbeat
HEARTBEAT_INTERVAL = 120  # 2 phút thay vì 30 giây
HEARTBEAT_VERBOSE = False  # Tắt log heartbeat để giảm noise

class ESP32AudioProcessor:
    def __init__(self):
        self.wave_data = bytearray()
        self.read_offset = 0

    async def read(self, chunk_size):
        while self.read_offset + chunk_size > len(self.wave_data):
            await asyncio.sleep(0.001)
        new_offset = self.read_offset + chunk_size
        data = self.wave_data[self.read_offset: new_offset]
        self.read_offset = new_offset
        return data

    def write_audio(self, data):
        # Nhận audio từ ESP32 và đẩy vào buffer cho Speechmatics
        self.wave_data.extend(data)

# Global audio processor
audio_processor = ESP32AudioProcessor()

# Speechmatics connection
conn = speechmatics.models.ConnectionSettings(
    url=CONNECTION_URL,
    auth_token=API_KEY,
)

# Create transcription client
ws = speechmatics.client.WebsocketClient(conn)

# Define transcription parameters - Cân bằng tốc độ và độ chính xác
conf = speechmatics.models.TranscriptionConfig(
    language=LANGUAGE,
    enable_partials=True,
    operating_point="enhanced",  # Quay lại "enhanced" để độ chính xác cao
    max_delay=0.7,  # Giảm từ 0.7s để nhanh hơn
)

# Audio settings
settings = speechmatics.models.AudioSettings()
settings.encoding = "pcm_s16le"
settings.sample_rate = SAMPLE_RATE
settings.chunk_size = CHUNK_SIZE

# Global variables for results
current_partial_transcript = ""
current_final_transcript = ""
# Buffer để gom câu và chỉ gửi/in khi có dấu câu kết thúc
sentence_buffer = ""
# Độ dài dòng đã in gần nhất để xóa phần dư khi cập nhật cùng dòng
_last_print_len = 0

# Biến toàn cục lưu websocket client
esp32_websocket = None
current_device_id = None

# Web portal API URL
WEB_PORTAL_URL = os.environ.get('WEB_PORTAL_URL', 'http://localhost:5000')

def _has_sentence_end(s: str) -> bool:
    return any(ch in s for ch in [".", "!", "?"])

def _print_status_line(text: str):
    # In trên cùng một dòng trong terminal (Windows friendly)
    # Ghi đè phần thừa nếu lần trước dài hơn
    global _last_print_len
    line = f"[  FINAL] {text}"
    pad = max(0, _last_print_len - len(line))
    # ANSI clear-line (\033[2K) + carriage return to avoid residual text/newlines
    out = "\r\033[2K" + line + (" " * pad)
    try:
        import sys
        sys.stdout.write(out)
        sys.stdout.flush()
    except Exception:
        pass
    _last_print_len = len(line)

def print_partial_transcript(msg):
    # Gửi PARTIAL để client hiển thị tức thì, nhưng không chốt câu
    global current_partial_transcript, esp32_websocket
    partial = msg.get('metadata', {}).get('transcript', '')
    current_partial_transcript = partial
    if not partial:
        return
    # Cập nhật một dòng trạng thái (không xuống dòng)
    _print_status_line(partial)
    if esp32_websocket is not None:
        asyncio.create_task(
            esp32_websocket.send(json.dumps({
                'partial': partial,
                'final': "",
                'timestamp': datetime.now().isoformat()
            }))
        )

def print_transcript(msg):
    global current_final_transcript, esp32_websocket, sentence_buffer, current_device_id
    final_transcript = msg.get('metadata', {}).get('transcript', '')
    if not final_transcript:
        return
    # Cập nhật buffer theo final hiện tại (final thường là cụm mới)
    if sentence_buffer:
        # Thêm khoảng trắng nếu cần
        if not sentence_buffer.endswith(' ') and not final_transcript.startswith(' '):
            sentence_buffer += ' '
        sentence_buffer += final_transcript
    else:
        sentence_buffer = final_transcript

    # Nếu đã có dấu câu kết thúc → chốt câu: in 1 dòng và gửi final 1 lần
    if _has_sentence_end(sentence_buffer):
        sentence = sentence_buffer.strip()
        # In câu hoàn chỉnh và xuống dòng một lần
        print(f"\r[  FINAL] {sentence}")
        # Reset chiều dài để lần sau không cần xóa đuôi
        global _last_print_len
        _last_print_len = 0
        current_final_transcript = sentence
        
        # Gửi đến ESP32 client
        if esp32_websocket is not None:
            asyncio.create_task(
                esp32_websocket.send(json.dumps({
                    'partial': "",
                    'final': sentence,
                    'timestamp': datetime.now().isoformat()
                }))
            )
        
        # Lưu vào database qua web portal API
        if current_device_id:
            asyncio.create_task(save_text_to_database(current_device_id, sentence, True))
        
        # Reset cho câu tiếp theo
        sentence_buffer = ""
    else:
        # Chưa có dấu câu, cập nhật cùng dòng
        _print_status_line(sentence_buffer)

async def save_text_to_database(device_id, transcript, is_final):
    """Lưu text transcript vào database qua web portal API"""
    try:
        response = requests.post(f"{WEB_PORTAL_URL}/api/text/save", 
            json={
                'device_id': device_id,
                'transcript': transcript,
                'is_final': is_final
            },
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"✅ Saved to DB: {transcript[:50]}...")
            else:
                print(f"❌ DB save failed: {result.get('message')}")
        else:
            print(f"❌ DB save failed: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ DB save error: {e}")

async def send_heartbeat():
    """Gửi heartbeat định kỳ để duy trì trạng thái online - Tối ưu hóa"""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)  # 2 phút thay vì 30 giây
        if current_device_id:
            try:
                # Sử dụng requests với timeout ngắn
                response = requests.post(f"{WEB_PORTAL_URL}/api/device/heartbeat",
                    json={'device_id': current_device_id}, timeout=3)
                if response.status_code == 200:
                    # Chỉ in heartbeat khi debug mode
                    if HEARTBEAT_VERBOSE:
                        print(f"💓 Heartbeat sent for {current_device_id}")
                else:
                    print(f"⚠️ Heartbeat failed: {response.status_code}")
            except Exception as e:
                # Chỉ log lỗi kết nối
                if "Connection" in str(e) or "timeout" in str(e).lower():
                    if HEARTBEAT_VERBOSE:
                        print(f"⚠️ Heartbeat connection issue")
                else:
                    print(f"⚠️ Heartbeat error: {e}")

async def notify_device_disconnect(device_id):
    """Thông báo thiết bị ngắt kết nối"""
    try:
        response = requests.post(f"{WEB_PORTAL_URL}/api/device/disconnect",
            json={'device_id': device_id}, timeout=5)
        if response.status_code == 200:
            print(f"📴 Notified web portal: {device_id} disconnected")
    except Exception as e:
        print(f"⚠️ Could not notify disconnect: {e}")

# Register event handlers
ws.add_event_handler(
    event_name=speechmatics.models.ServerMessageType.AddPartialTranscript,
    event_handler=print_partial_transcript,
)

ws.add_event_handler(
    event_name=speechmatics.models.ServerMessageType.AddTranscript,
    event_handler=print_transcript,
)

# WebSocket server for ESP32
async def handle_esp32_client(websocket, path):
    global esp32_websocket, current_device_id
    esp32_websocket = websocket
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    print(f"📡 ESP32 connected from {client_ip}")
    
    try:
        async for message in websocket:
            try:
                # Parse JSON message from ESP32
                data = json.loads(message)
                
                # Device registration
                if data.get('type') == 'register':
                    device_id = data.get('device_id')
                    esp32_ip = data.get('ip_address', 'unknown')
                    mac_address = data.get('mac_address', 'unknown')
                    rssi = data.get('rssi', 0)
                    
                    if device_id:
                        current_device_id = device_id
                        print(f"📡 Device registered: {device_id}")
                        print(f"   📍 ESP32 IP: {esp32_ip}")
                        print(f"   🔗 MAC: {mac_address}")
                        print(f"   📶 RSSI: {rssi} dBm")
                        print(f"   🌐 Client IP: {client_ip}")
                        
                        # Đăng ký thiết bị với web portal
                        try:
                            registration_data = {
                                'device_id': device_id,
                                'esp32_ip': esp32_ip,
                                'client_ip': client_ip,
                                'mac_address': mac_address,
                                'rssi': rssi
                            }
                            print(f"📤 Registering with web portal: {registration_data}")
                            
                            response = requests.post(f"{WEB_PORTAL_URL}/api/device/register",
                                json=registration_data, timeout=5)
                            
                            if response.status_code == 200:
                                result = response.json()
                                if result.get('success'):
                                    print(f"✅ Device registered with web portal: {result.get('message')}")
                                else:
                                    print(f"❌ Registration failed: {result.get('message')}")
                                    print("💡 Please add this device via web portal first!")
                            else:
                                print(f"⚠️ Web portal registration failed: HTTP {response.status_code}")
                                print(f"   Response: {response.text}")
                        except requests.exceptions.ConnectionError:
                            print(f"❌ Cannot connect to web portal at {WEB_PORTAL_URL}")
                            print(f"   Make sure web portal is running on port 5000")
                        except Exception as e:
                            print(f"⚠️ Could not register with web portal: {e}")
                        
                        # Send acknowledgment back to ESP32
                        await websocket.send(json.dumps({
                            'type': 'register_ack',
                            'status': 'success',
                            'device_id': device_id,
                            'client_ip': client_ip,
                            'timestamp': datetime.now().isoformat()
                        }))
                    continue
                
                # App-level keepalive - Tối ưu hóa
                if data.get('type') == 'ping':
                    # Chỉ gửi pong nhanh, không cập nhật heartbeat ở đây
                    # Heartbeat sẽ được xử lý bởi task riêng
                    await websocket.send(json.dumps({
                        'type': 'pong',
                        'ts': datetime.now().isoformat()
                    }))
                    continue
                    
                if data.get('type') == 'audio':
                    # Decode base64 audio data
                    audio_data = base64.b64decode(data['data'])
                    # Add to audio processor
                    audio_processor.write_audio(audio_data)
                    
                    # Gửi acknowledgment nhẹ để đảm bảo chất lượng truyền
                    await websocket.send(json.dumps({
                        'status': 'ok'
                    }))
            except json.JSONDecodeError:
                print("❌ Invalid JSON from ESP32")
            except Exception as e:
                print(f"❌ Error processing ESP32 message: {e}")
    except websockets.exceptions.ConnectionClosed:
        print(f"📡 ESP32 disconnected: {current_device_id}")
        if current_device_id:
            asyncio.create_task(notify_device_disconnect(current_device_id))
        esp32_websocket = None
        current_device_id = None
    except Exception as e:
        print(f"❌ ESP32 connection error: {e}")
        if current_device_id:
            print(f"📴 Notifying disconnect due to error: {current_device_id}")
            asyncio.create_task(notify_device_disconnect(current_device_id))
        esp32_websocket = None
        current_device_id = None

# Start Speechmatics transcription in background
async def start_transcription():
    print("🎤 Starting Speechmatics transcription...")
    # Tự động retry nếu lỗi
    while True:
        try:
            await asyncio.to_thread(ws.run_synchronously, audio_processor, conf, settings)
        except Exception as e:
            print(f"❌ Speechmatics error: {e}")
            await asyncio.sleep(2)
            print("↻ Retrying Speechmatics connection...")
            continue
        break

# Main server function
async def main():
    print("🚀 Starting ESP32 Realtime Audio Server...")
    print("📡 WebSocket server: ws://0.0.0.0:8765")
    print("🎤 Speechmatics: Real-time Vietnamese transcription")
    print("🔗 Web Portal: " + WEB_PORTAL_URL)
    print("⚠️  ONLY devices added via web portal will be accepted!")
    print("-" * 60)
    # Start WebSocket server
    server = await websockets.serve(
        handle_esp32_client,
        "0.0.0.0",
        8765,
        # Tắt ping/pong ở tầng protocol để tránh xung đột với proxy
        ping_interval=None,
        ping_timeout=None,
        close_timeout=30,
        max_size=None,  # Không giới hạn, base64 có thể lớn theo chunk
    )
    # Start transcription in background
    transcription_task = asyncio.create_task(start_transcription())
    # Start heartbeat task
    heartbeat_task = asyncio.create_task(send_heartbeat())
    print("✅ Server ready! Waiting for ESP32 connection...")
    print("💓 Heartbeat optimized: every 2 minutes, reduced logging")
    # Keep server running
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")