"""
Server Python nhận realtime audio stream từ ESP32 và xử lý với Speechmatics API
Tương tự như stream_vi.py nhưng nhận audio từ ESP32 thay vì microphone laptop
"""

import speechmatics
from httpx import HTTPStatusError
import asyncio
import websockets
import json
import base64
from datetime import datetime

# API Key Speechmatics
API_KEY = "0pYyUIla5k2tKMgdI0SdliBfC4eh4Thd"
LANGUAGE = "vi"
CONNECTION_URL = f"wss://eu2.rt.speechmatics.com/v2/{LANGUAGE}"

# Cấu hình audio
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024

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

# Define transcription parameters
conf = speechmatics.models.TranscriptionConfig(
    language=LANGUAGE,
    enable_partials=True,
    operating_point="enhanced",
    max_delay=1,
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
    global current_final_transcript, esp32_websocket, sentence_buffer
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
        if esp32_websocket is not None:
            asyncio.create_task(
                esp32_websocket.send(json.dumps({
                    'partial': "",
                    'final': sentence,
                    'timestamp': datetime.now().isoformat()
                }))
            )
        # Reset cho câu tiếp theo
        sentence_buffer = ""
    else:
        # Chưa có dấu câu, cập nhật cùng dòng
        _print_status_line(sentence_buffer)

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
    global esp32_websocket
    esp32_websocket = websocket
    print(f"📡 ESP32 connected from {websocket.remote_address}")
    try:
        async for message in websocket:
            try:
                # Parse JSON message from ESP32
                data = json.loads(message)
                if data.get('type') == 'audio':
                    # Decode base64 audio data
                    audio_data = base64.b64decode(data['data'])
                    # Add to audio processor
                    audio_processor.write_audio(audio_data)
                    # Send acknowledgment
                    await websocket.send(json.dumps({
                        'status': 'received',
                        'timestamp': datetime.now().isoformat()
                    }))
            except json.JSONDecodeError:
                print("❌ Invalid JSON from ESP32")
            except Exception as e:
                print(f"❌ Error processing ESP32 message: {e}")
    except websockets.exceptions.ConnectionClosed:
        print("📡 ESP32 disconnected")
        esp32_websocket = None
    except Exception as e:
        print(f"❌ ESP32 connection error: {e}")

# Start Speechmatics transcription in background
async def start_transcription():
    print("🎤 Starting Speechmatics transcription...")
    try:
        # Chạy client đồng bộ ở thread phụ để không block asyncio loop
        await asyncio.to_thread(ws.run_synchronously, audio_processor, conf, settings)
    except Exception as e:
        print(f"❌ Speechmatics error: {e}")

# Main server function
async def main():
    print("🚀 Starting ESP32 Realtime Audio Server...")
    print("📡 WebSocket server: ws://0.0.0.0:8765")
    print("🎤 Speechmatics: Real-time Vietnamese transcription")
    print("-" * 60)
    # Start WebSocket server
    server = await websockets.serve(
        handle_esp32_client,
        "0.0.0.0",
        8765,
        ping_interval=20,
        ping_timeout=20,
        max_size=2**22,  # ~4MB, phòng khi gói base64 lớn
    )
    # Start transcription in background
    transcription_task = asyncio.create_task(start_transcription())
    print("✅ Server ready! Waiting for ESP32 connection...")
    # Keep server running
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")