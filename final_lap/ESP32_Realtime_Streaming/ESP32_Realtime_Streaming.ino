/*
 * ESP32-S3 Realtime Voice Recognition với INMP441
 * Streaming audio realtime lên server để nhận diện giọng nói tiếng Việt
 * Sử dụng FontMaker để hiển thị tiếng Việt đúng trên OLED
 * Chỉ xóa văn bản khi nhận được dấu chấm (.), chấm than (!), hoặc hỏi chấm (?) v.v.
 */ 

 #include "driver/i2s.h"
 #include "WiFi.h"
 #include "WiFiClientSecure.h"  // Thêm để gọi API HTTPS
 #include "WebSocketsClient.h"
 #include "ArduinoJson.h"
 #include "base64.h"
 #include <Wire.h>
 #include <Adafruit_GFX.h>
 #include <Adafruit_SSD1306.h>
 #include "FontMaker.h"  // Thư viện FontMaker bắt buộc
 
 // Cấu hình WiFi - Sẽ được cập nhật động từ web portal
 String current_ssid = "VDK IOT";  // WiFi mặc định
 String current_password = "20242025x";
 
 // Thời gian kiểm tra cấu hình WiFi mới
 unsigned long lastWifiConfigCheck = 0;
 const unsigned long wifiConfigCheckInterval = 90000; // 30 giây
 
 // Cấu hình I2S cho INMP441
 #define I2S_WS 7
 #define I2S_SD 5
 #define I2S_SCK 6
 #define I2S_PORT I2S_NUM_0
 
 // Cấu hình audio
 #define SAMPLE_RATE 16000
 #define SAMPLE_BITS 16
 #define CHUNK_SIZE 512
 #define BUFFER_SIZE (CHUNK_SIZE * 4)  // Buffer lớn hơn cho streaming
 
// WebSocket server - Sử dụng URL công khai từ Cloudflare
const char* wsServer = "esp32.ptitavitech.online";  // URL công khai
const int wsPort = 443;  // WSS qua Cloudflare

// Device ID duy nhất cho ESP32 này (sẽ được tạo từ MAC address)
String deviceId = "";
 
 // Buffer cho audio data
 int16_t audioBuffer[BUFFER_SIZE];
 int32_t i2sBuffer32[CHUNK_SIZE];
 size_t bytesRead = 0;
 bool isRecording = false;
 
 // WebSocket client
 WebSocketsClient webSocket;
 
 // OLED I2C (SSD1306 128x64)
 #define OLED_SDA 8
 #define OLED_SCL 9
 #define OLED_ADDR 0x3C
 #define SCREEN_WIDTH 128
 #define SCREEN_HEIGHT 64
 Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
 
 // FontMaker setup - Hàm vẽ pixel cho OLED
 void setPixelForFont(int16_t x, int16_t y, uint16_t color) {
   // Bật chế độ hiển thị gương (mirror) cho chữ vẽ bằng FontMaker
   static const bool mirrorText = true;
 
   // Ánh xạ hoành độ sang vị trí đối xứng qua trục dọc (gương)
   int16_t drawX = mirrorText ? (SCREEN_WIDTH - 1 - x) : x;
 
   if (drawX >= 0 && drawX < SCREEN_WIDTH && y >= 0 && y < SCREEN_HEIGHT) {
     if (color > 0) {
       display.drawPixel(drawX, y, SSD1306_WHITE);
     } else {
       display.drawPixel(drawX, y, SSD1306_BLACK);
     }
   }
 }
 
 // Khởi tạo FontMaker
 MakeFont vietnameseFont(&setPixelForFont);
 
 // Biến để lưu trữ văn bản hiện tại
 String currentText = "";
 
 void showOnOLED(const String &text, bool clearScreen) {
   if (clearScreen) {
     display.clearDisplay();
     currentText = ""; // Xóa văn bản hiện tại nếu cần
   }
   
   // Cập nhật văn bản hiện tại
   currentText += (currentText.length() > 0 && !text.startsWith(" ") ? " " : "") + text;
   
   // Sử dụng FontMaker để hiển thị tiếng Việt
   vietnameseFont.set_font(MakeFont_Font1);  // Thay đổi thành font bạn vừa tạo
   
   Serial.print("Displaying with FontMaker: ");
   Serial.println(currentText);
   
   // Tính toán vị trí hiển thị
   int startY = 2;
   int lineHeight = 10;  // Điều chỉnh theo font size
   int currentY = startY;
   int maxWidth = SCREEN_WIDTH - 4;  // Margin
   
   // Chia text thành các dòng
   String remainingText = currentText;
   
   while (remainingText.length() > 0 && currentY < SCREEN_HEIGHT - lineHeight) {
     String line = "";
     int lineWidth = 0;
     int charIndex = 0;
     
     // Tìm text vừa với độ rộng màn hình, thêm từng từ nguyên vẹn
     while (charIndex < remainingText.length()) {
       // Tìm từ tiếp theo (phân cách bởi space hoặc \n)
       int wordStart = charIndex;
       while (charIndex < remainingText.length() && remainingText[charIndex] != ' ' && remainingText[charIndex] != '\n') {
         charIndex++;
       }
       String word = remainingText.substring(wordStart, charIndex);
       
       // Bỏ qua space hoặc \n sau từ
       bool isNewline = false;
       if (charIndex < remainingText.length()) {
         if (remainingText[charIndex] == '\n') {
           isNewline = true;
         }
         charIndex++;  // Skip space or \n
       }
       
       // Kiểm tra nếu thêm word có vừa (thêm space nếu line không rỗng)
       String testLine = line + (line.length() > 0 && !word.startsWith("\n") ? " " : "") + word;
       int testWidth = vietnameseFont.getLength(testLine.c_str());
       
       if (testWidth <= maxWidth) {
         line = testLine;
         lineWidth = testWidth;
         
         // Nếu gặp \n, break sau khi thêm
         if (isNewline) {
           break;
         }
       } else {
         // Không vừa, nếu line rỗng thì thêm word (giả sử từ không quá dài, nếu quá có thể cắt)
         if (line.length() == 0) {
           line = word;
           // Nếu vẫn không vừa, có thể xử lý cắt từ, nhưng tạm thời bỏ qua
           break;
         } else {
           // Không thêm từ này, break để xuống dòng
           charIndex = wordStart;  // Quay lại vị trí bắt đầu từ để remainingText giữ nguyên từ này
           break;
         }
       }
     }
     
     // Hiển thị dòng nếu có nội dung
     if (line.length() > 0) {
       // Loại bỏ \n ở cuối dòng nếu có
       if (line.endsWith("\n")) {
         line = line.substring(0, line.length() - 1);
       }
       
       // Sử dụng print_noBackColor để không có nền
       vietnameseFont.print_noBackColor(2, currentY, line.c_str(), 1);  // 1 = WHITE
       currentY += lineHeight;
       
       Serial.print("Line displayed: ");
       Serial.println(line);
     }
     
     // Cập nhật text còn lại
     remainingText = remainingText.substring(charIndex);
     
     // Tránh vòng lặp vô hạn
     if (charIndex == 0 && remainingText.length() > 0) {
       // Nếu từ đầu tiên quá dài, thêm ký tự đầu và tiếp tục
       remainingText = remainingText.substring(1);
     }
   }
   
   display.display();
 }
 
 // Hàm chuyển đổi UTF-8 thành ASCII gần đúng cho tiếng Việt
 String convertVietnameseToASCII(const String& input) {
   String output = "";
   
   for (int i = 0; i < input.length(); i++) {
     unsigned char c = input[i];
     
     // Nếu là ký tự ASCII thường
     if (c < 128) {
       output += (char)c;
       continue;
     }
     
     // Xử lý UTF-8 tiếng Việt cơ bản
     if (i + 1 < input.length()) {
       unsigned char c1 = input[i];
       unsigned char c2 = input[i + 1];
       
       // Chữ a có dấu
       if (c1 == 0xC3) {
         switch (c2) {
           case 0xA0: case 0xA1: case 0xA2: case 0xA3: case 0xA4: case 0xA5: output += "a"; break; // à á â ã ä å
           case 0x80: case 0x81: case 0x82: case 0x83: case 0x84: case 0x85: output += "A"; break; // À Á Â Ã Ä Å
           case 0xA8: case 0xA9: case 0xAA: case 0xAB: output += "e"; break; // è é ê ë
           case 0x88: case 0x89: case 0x8A: case 0x8B: output += "E"; break; // È É Ê Ë
           case 0xAC: case 0xAD: case 0xAE: case 0xAF: output += "i"; break; // ì í î ï
           case 0x8C: case 0x8D: case 0x8E: case 0x8F: output += "I"; break; // Ì Í Î Ï
           case 0xB2: case 0xB3: case 0xB4: case 0xB5: case 0xB6: output += "o"; break; // ò ó ô õ ö
           case 0x92: case 0x93: case 0x94: case 0x95: case 0x96: output += "O"; break; // Ò Ó Ô Õ Ö
           case 0xB9: case 0xBA: case 0xBB: case 0xBC: output += "u"; break; // ù ú û ü
           case 0x99: case 0x9A: case 0x9B: case 0x9C: output += "U"; break; // Ù Ú Û Ü
           case 0xBD: case 0xBF: output += "y"; break; // ý ÿ
           case 0x9D: output += "Y"; break; // Ý
           default: output += "?"; break;
         }
         i++; // Skip next byte
       }
       // Xử lý các ký tự tiếng Việt khác (ă, đ, ê, ô, ơ, ư...)
       else if (c1 == 0xC4) {
         switch (c2) {
           case 0x83: output += "a"; break; // ă
           case 0x82: output += "A"; break; // Ă
           case 0x91: output += "d"; break; // đ
           case 0x90: output += "D"; break; // Đ
           default: output += "?"; break;
         }
         i++;
       }
       else if (c1 == 0xC6) {
         switch (c2) {
           case 0xB0: output += "u"; break; // ư
           case 0xAF: output += "U"; break; // Ư
           case 0xA1: output += "o"; break; // ơ
           case 0xA0: output += "O"; break; // Ơ
           default: output += "?"; break;
         }
         i++;
       }
       else {
         // Các ký tự UTF-8 khác, thay thế bằng ?
         output += "?";
         if ((c & 0xE0) == 0xC0) i++; // 2-byte UTF-8
         else if ((c & 0xF0) == 0xE0) i += 2; // 3-byte UTF-8
         else if ((c & 0xF8) == 0xF0) i += 3; // 4-byte UTF-8
       }
     } else {
       output += "?";
     }
   }
   
   return output;
 }
 
 // Hàm hiển thị với xử lý encoding
 void showOnOLEDSimple(const String &text) {
   display.clearDisplay();
   display.setTextSize(1);
   display.setTextColor(SSD1306_WHITE);
   display.setCursor(0, 0);
   
   // Chuyển đổi UTF-8 thành ASCII
   String convertedText = convertVietnameseToASCII(text);
   
   Serial.print("Original: ");
   Serial.println(text);
   Serial.print("Converted: ");
   Serial.println(convertedText);
   
   // Hiển thị text đã chuyển đổi
   int16_t x, y; 
   uint16_t w, h;
   String line = "";
   
   for (size_t i = 0; i < convertedText.length(); ++i) {
     line += convertedText[i];
     display.getTextBounds(line, 0, 0, &x, &y, &w, &h);
     if (w >= SCREEN_WIDTH - 2 || convertedText[i] == '\n') {
       display.println(line);
       line = "";
       if (display.getCursorY() > SCREEN_HEIGHT - 8) break;
     }
   }
   if (line.length() > 0) display.println(line);
   display.display();
 }
 
 void setup() {
   Serial.begin(115200); // Tăng baudrate
   Serial.println("🎤 ESP32-S3 Realtime Voice Recognition Starting...");
   
   // OLED init
   Wire.begin(OLED_SDA, OLED_SCL);
   if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
     Serial.println("❌ SSD1306 failed");
   } else {
     Serial.println("✅ SSD1306 initialized");
     display.clearDisplay();
     display.setTextSize(1);
     display.setTextColor(SSD1306_WHITE);
     display.setCursor(0, 0);
     display.println("ESP32-S3 Realtime");
     display.println("Speech to OLED");
     display.display();
     delay(2000); // Hiển thị thông báo khởi tạo
   }
   
   initI2S();
   connectWiFi();
   initWebSocket();
   
   // Kiểm tra WiFi config ngay sau khi khởi động
   Serial.println("🔍 Checking WiFi config at startup...");
   delay(2000); // Đợi kết nối ổn định
   checkForWiFiConfigUpdate();
   
   Serial.println("✅ Setup completed! Ready for realtime streaming...");
   Serial.println("🎙️ Press any key to start/stop streaming...");
   Serial.println("🔧 Press 'w' to check WiFi config manually");
   showOnOLEDSimple("Ready to stream\nPress any key...");
 }
 
void loop() {
  webSocket.loop();
 
   // Kiểm tra input từ Serial để bắt đầu/dừng streaming
   if (Serial.available()) {
     char c = Serial.read();
     if (c == 'w' || c == 'W') {
       // Nhấn 'w' để kiểm tra WiFi config ngay lập tức
       Serial.println("🔄 Manual WiFi config check...");
       checkForWiFiConfigUpdate();
     } else if (!isRecording) {
       startStreaming();
     } else {
       stopStreaming();
     }
   }
 
  // Streaming audio nếu đang recording
  if (isRecording) {
    streamAudio();
  }

  // Gửi keepalive app-level định kỳ nếu đã kết nối
  static unsigned long lastKeepaliveMs = 0;
  const unsigned long keepaliveIntervalMs = 15000; // 15s
  unsigned long nowMs = millis();
  if (webSocket.isConnected()) {
    if (nowMs - lastKeepaliveMs >= keepaliveIntervalMs) {
      DynamicJsonDocument pingDoc(128);
      pingDoc["type"] = "ping";
      pingDoc["ts"] = nowMs;
      String pingMsg;
      serializeJson(pingDoc, pingMsg);
      webSocket.sendTXT(pingMsg);
      lastKeepaliveMs = nowMs;
    }
  }

  // Kiểm tra cấu hình WiFi mới định kỳ
  if (nowMs - lastWifiConfigCheck >= wifiConfigCheckInterval) {
    if (WiFi.status() == WL_CONNECTED) {
      checkForWiFiConfigUpdate();
    }
    lastWifiConfigCheck = nowMs;
  }

  delay(10);
 }
 
 void initI2S() {
   Serial.println("🔧 Initializing I2S...");
   i2s_config_t i2s_config = {
     .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
     .sample_rate = SAMPLE_RATE,
     .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
     .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
     .communication_format = I2S_COMM_FORMAT_STAND_I2S,
     .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
     .dma_buf_count = 8,
     .dma_buf_len = CHUNK_SIZE,
     .use_apll = false,
     .tx_desc_auto_clear = false,
     .fixed_mclk = 0
   };
 
   i2s_pin_config_t pin_config = {
     .bck_io_num = I2S_SCK,
     .ws_io_num = I2S_WS,
     .data_out_num = -1,
     .data_in_num = I2S_SD
   };
 
   i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
   i2s_set_pin(I2S_PORT, &pin_config);
 }
 
 void connectWiFi() {
   Serial.print("🔌 Connecting to WiFi: ");
   Serial.println(current_ssid);
   WiFi.begin(current_ssid.c_str(), current_password.c_str());
   
   int attempts = 0;
   while (WiFi.status() != WL_CONNECTED && attempts < 20) {
     delay(500);
     Serial.print(".");
     attempts++;
   }
   
   if (WiFi.status() == WL_CONNECTED) {
     Serial.println();
     Serial.print("📡 IP address: ");
     Serial.println(WiFi.localIP());
     // Tắt power save để hạn chế ngắt kết nối định kỳ
     WiFi.setSleep(false);
     Serial.print("📶 RSSI: ");
     Serial.println(WiFi.RSSI());
     
     // Báo cáo trạng thái kết nối thành công
     reportWiFiStatus("connected");

     // Đồng bộ thời gian cho TLS (NTP)
     configTime(0, 0, "pool.ntp.org", "time.nist.gov");
     time_t now = time(nullptr);
     uint32_t waitStart = millis();
     while (now < 8 * 3600 * 2 && millis() - waitStart < 10000) { // đợi tối đa 10s
       delay(200);
       now = time(nullptr);
     }
     struct tm timeinfo;
     if (localtime_r(&now, &timeinfo)) {
       Serial.printf("🕒 Time synced: %04d-%02d-%02d %02d:%02d:%02d\n",
                     timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
                     timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
     } else {
       Serial.println("⚠️ Time sync failed or timed out");
     }
   } else {
     Serial.println();
     Serial.println("❌ WiFi connection failed!");
     reportWiFiStatus("failed");
   }
 }
 
 void initWebSocket() {
   Serial.println("🔌 Initializing WebSocket...");
   
   // Tạo device ID từ MAC address
   deviceId = "ESP32_" + WiFi.macAddress();
   deviceId.replace(":", "");  // Xóa dấu :
   Serial.print("📱 Device ID: ");
   Serial.println(deviceId);
   
   // Kết nối WSS (TLS) qua Cloudflare
   webSocket.beginSSL(wsServer, wsPort, "/");
   webSocket.onEvent(webSocketEvent);
   // Tự động reconnect và heartbeat để tránh ngắt kết nối
   webSocket.setReconnectInterval(3000);
   // Không dùng heartbeat protocol; dùng keepalive app-level trong loop()
 }
 
 void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
   switch(type) {
     case WStype_DISCONNECTED:
       Serial.println("❌ WebSocket disconnected!");
       if (isRecording) stopStreaming();
       showOnOLEDSimple("WebSocket\ndisconnected");
       break;
     case WStype_CONNECTED:
       Serial.println("✅ WebSocket connected to: /");
       showOnOLEDSimple("WebSocket\nconnected");
       
       // Đăng ký device với server
       registerDevice();
       
       if (!isRecording) startStreaming();
       break;
     case WStype_TEXT:
       {
         // In ra dữ liệu thô để debug
         Serial.print("Raw payload: ");
         for (size_t i = 0; i < length; i++) {
           Serial.printf("%02X ", payload[i]);
         }
         Serial.println();
         
         // Thử parse JSON
         DynamicJsonDocument doc(1024);
         DeserializationError err = deserializeJson(doc, payload, length);
         if (!err) {
           const char* finalText = doc["final"] | "";
           const char* partialText = doc["partial"] | ""; // Hỗ trợ partial nếu server gửi
 
           String textToDisplay = "";
           bool clearScreen = false;
 
           if (partialText[0] != '\0') {
             textToDisplay = String(partialText);
           } else if (finalText[0] != '\0') {
             textToDisplay = String(finalText);
           }
 
           if (textToDisplay != "") {
             // Kiểm tra xem văn bản có chứa dấu câu kết thúc hay không
             if (textToDisplay.indexOf('.') != -1 || textToDisplay.indexOf('!') != -1 || textToDisplay.indexOf('?') != -1) {
               clearScreen = true; // Xóa màn hình nếu có dấu câu kết thúc
             }
             showOnOLED(textToDisplay, clearScreen);
             Serial.print("Displayed text: ");
             Serial.println(textToDisplay);
           }
         } else {
           Serial.print("JSON parse error: ");
           Serial.println(err.c_str());
           
           // Fallback: hiển thị trực tiếp
           String rawText = "";
           for (size_t i = 0; i < length; i++) {
             if (payload[i] >= 32 && payload[i] < 127) { // Chỉ lấy ký tự có thể in được
               rawText += (char)payload[i];
             }
           }
           Serial.print("Raw text: ");
           Serial.println(rawText);
           
           // Hiển thị rawText, xóa màn hình nếu có dấu câu kết thúc
           bool clearScreen = rawText.indexOf('.') != -1 || rawText.indexOf('!') != -1 || rawText.indexOf('?') != -1;
           showOnOLED(rawText, clearScreen);
         }
       }
       break;
     case WStype_ERROR:
       Serial.println("❌ WebSocket error!");
       showOnOLEDSimple("WebSocket error");
       break;
     default:
       break;
   }
 }
 
 void registerDevice() {
   Serial.println("📝 Registering device with server...");
   
   // Tạo JSON message để đăng ký device với IP
   DynamicJsonDocument doc(512);
   doc["type"] = "register";
   doc["device_id"] = deviceId;
   doc["ip_address"] = WiFi.localIP().toString();
   doc["mac_address"] = WiFi.macAddress();
   doc["rssi"] = WiFi.RSSI();
   doc["timestamp"] = millis();
   
   String message;
   serializeJson(doc, message);
   
   // Gửi qua WebSocket
   webSocket.sendTXT(message);
   Serial.print("📤 Sent registration: ");
   Serial.println(message);
   Serial.print("📍 Local IP: ");
   Serial.println(WiFi.localIP());
 }

 void reportWiFiStatus(String status) {
   Serial.println("📡 Reporting WiFi status to web portal...");
   
   // Tạo HTTP client để gửi status
   WiFiClientSecure client;
   client.setInsecure(); // Bỏ qua SSL certificate validation
   
   if (client.connect("esp32.ptitavitech.online", 443)) {
     DynamicJsonDocument doc(256);
     doc["device_id"] = deviceId;
     doc["status"] = status;
     doc["wifi_name"] = current_ssid;
     doc["rssi"] = WiFi.RSSI();
     
     String jsonString;
     serializeJson(doc, jsonString);
     
     client.println("POST /api/device/wifi-status HTTP/1.1");
     client.println("Host: esp32.ptitavitech.online");
     client.println("Content-Type: application/json");
     client.print("Content-Length: ");
     client.println(jsonString.length());
     client.println();
     client.println(jsonString);
     
     Serial.println("✅ WiFi status reported: " + status);
   } else {
     Serial.println("❌ Failed to report WiFi status");
   }
   client.stop();
 }

 void checkForWiFiConfigUpdate() {
   Serial.println("🔍 Checking for WiFi config updates...");
   
   WiFiClientSecure client;
   client.setInsecure();
   
   if (client.connect("esp32.ptitavitech.online", 443)) {
     client.println("GET /api/device/wifi-config/" + deviceId + " HTTP/1.1");
     client.println("Host: esp32.ptitavitech.online");
     client.println("Connection: close");
     client.println();
     
     // Đọc response
     String response = "";
     bool headersPassed = false;
     
     while (client.connected() || client.available()) {
       if (client.available()) {
         String line = client.readStringUntil('\n');
         if (!headersPassed) {
           if (line == "\r") {
             headersPassed = true;
           }
         } else {
           response += line;
         }
       }
     }
     
     client.stop();
     
     // Parse JSON response
     DynamicJsonDocument doc(512);
     DeserializationError error = deserializeJson(doc, response);
     
     if (!error && doc["success"]) {
       String newSSID = doc["wifi_name"];
       String newPassword = doc["wifi_password"];
       
       // Kiểm tra xem có thay đổi không
       if (newSSID != current_ssid || newPassword != current_password) {
         Serial.println("🔄 New WiFi config detected!");
         Serial.println("New SSID: " + newSSID);
         
         // Cập nhật cấu hình
         current_ssid = newSSID;
         current_password = newPassword;
         
         // Ngắt kết nối hiện tại và kết nối lại
         WiFi.disconnect();
         delay(1000);
         
         showOnOLEDSimple("Updating WiFi...\n" + newSSID);
         connectWiFi();
         
         if (WiFi.status() == WL_CONNECTED) {
           showOnOLEDSimple("WiFi Updated!\n" + newSSID);
           // Kết nối lại WebSocket
           initWebSocket();
         } else {
           showOnOLEDSimple("WiFi Failed!\n" + newSSID);
         }
       } else {
         Serial.println("✅ WiFi config unchanged");
       }
     } else {
       Serial.println("❌ Failed to get WiFi config or no config found");
     }
   } else {
     Serial.println("❌ Failed to connect to web portal for WiFi config");
   }
 }

 void startStreaming() {
   isRecording = true;
   currentText = ""; // Xóa văn bản hiện tại khi bắt đầu streaming
   Serial.println("🎙️ Starting realtime streaming...");
   Serial.println("🔴 Streaming active - Speak into microphone!");
   Serial.println("🎙️ Press any key to stop streaming...");
   showOnOLEDSimple("Streaming...\nSpeak now");
 }
 
 void stopStreaming() {
   isRecording = false;
   currentText = ""; // Xóa văn bản hiện tại khi dừng streaming
   Serial.println("⏹️ Stopping streaming...");
   showOnOLEDSimple("Stopped\nPress any key...");
 }
 
 // Cân bằng tốc độ gửi và chất lượng audio
 unsigned long lastSendMs = 0;
 const uint16_t sendIntervalMs = 25; // Tăng từ 35ms xuống 15ms để nhanh hơn
 
 void streamAudio() {
   if (!webSocket.isConnected()) {
     Serial.println("❌ WebSocket not connected!");
     return;
   }
 
   // Hạn chế tốc độ gửi để dễ đọc trên Serial Monitor và ổn định mạng
   unsigned long now = millis();
   if (now - lastSendMs < sendIntervalMs) {
     return;
   }
 
   // Đọc dữ liệu audio từ I2S ở 32-bit, sau đó chuyển về 16-bit
   size_t bytesRead32 = 0;
   esp_err_t result = i2s_read(I2S_PORT, (char*)i2sBuffer32, CHUNK_SIZE * sizeof(int32_t), &bytesRead32, 0);
 
   if (result == ESP_OK && bytesRead32 > 0) {
     size_t samples = bytesRead32 / sizeof(int32_t);
     if (samples > BUFFER_SIZE) samples = BUFFER_SIZE; // an toàn
     for (size_t i = 0; i < samples; ++i) {
       // INMP441: 24-bit MSB trong 32-bit, dịch để còn 16-bit
       audioBuffer[i] = (int16_t)(i2sBuffer32[i] >> 14);
     }
 
     // Encode audio 16-bit PCM sang base64
     String encodedAudio = base64::encode((uint8_t*)audioBuffer, samples * sizeof(int16_t));
 
     // Create JSON message
     DynamicJsonDocument doc(2048);
     doc["type"] = "audio";
     doc["data"] = encodedAudio;
     doc["timestamp"] = millis();
 
     String message;
     serializeJson(doc, message);
 
     // Send via WebSocket - Không chờ ACK để tăng tốc độ
     webSocket.sendTXT(message);
 
     // cập nhật nhịp gửi
     lastSendMs = now;
   } else {
     // Debug I2S read error
     static unsigned long lastErrorMs = 0;
     if (now - lastErrorMs > 5000) {
       Serial.printf("❌ I2S read error: %d, bytes: %d\n", result, bytesRead32);
       lastErrorMs = now;
     }
   }
 }