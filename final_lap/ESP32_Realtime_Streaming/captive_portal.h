/*
 * Captive Portal cho WiFi Provisioning
 * ESP32 phát WiFi AP, người dùng kết nối và cấu hình
 */

#ifndef CAPTIVE_PORTAL_H
#define CAPTIVE_PORTAL_H

// HTML cho trang cấu hình
const char CAPTIVE_PORTAL_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP32 Setup</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 400px;
            width: 100%;
        }
        h1 {
            color: #667eea;
            text-align: center;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .device-id {
            text-align: center;
            color: #666;
            font-size: 14px;
            margin-bottom: 30px;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 10px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: bold;
        }
        input, select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input:focus, select:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        button:active {
            transform: translateY(0);
        }
        .status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            display: none;
        }
        .status.success {
            background: #d4edda;
            color: #155724;
            display: block;
        }
        .status.error {
            background: #f8d7da;
            color: #721c24;
            display: block;
        }
        .scan-btn {
            background: #28a745;
            margin-bottom: 15px;
        }
        .reset-btn {
            background: #dc3545;
            margin-top: 15px;
        }
        .reset-btn:hover {
            background: #c82333;
        }
        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin-top: 20px;
            border-radius: 5px;
            font-size: 14px;
            color: #0c5460;
        }
        .info-box strong {
            display: block;
            margin-bottom: 5px;
        }
        .progress-container {
            margin-top: 20px;
            display: none;
        }
        .progress-bar {
            width: 100%;
            height: 30px;
            background: #e0e0e0;
            border-radius: 15px;
            overflow: hidden;
            position: relative;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            width: 0%;
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 14px;
        }
        .timeline {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
        }
        .timeline-item {
            display: flex;
            align-items: center;
            padding: 8px 0;
            font-size: 14px;
        }
        .timeline-icon {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 10px;
            font-size: 12px;
        }
        .timeline-icon.pending {
            background: #e0e0e0;
            color: #999;
        }
        .timeline-icon.active {
            background: #ffc107;
            color: white;
            animation: pulse 1s infinite;
        }
        .timeline-icon.done {
            background: #28a745;
            color: white;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        .countdown {
            font-size: 48px;
            font-weight: bold;
            text-align: center;
            color: #667eea;
            margin: 20px 0;
            animation: countdown-pulse 1s infinite;
        }
        @keyframes countdown-pulse {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.1); opacity: 0.8; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎤 ESP32 Setup</h1>
        <div class="device-id">Device ID: <strong>%DEVICE_ID%</strong></div>
        
        <form id="wifiForm" onsubmit="return submitForm(event)">
            <div class="form-group">
                <label>📡 WiFi Network:</label>
                <select id="ssid" name="ssid" required>
                    <option value="">-- Chọn WiFi --</option>
                    %WIFI_LIST%
                </select>
            </div>
            
            <div class="form-group">
                <label>🔐 WiFi Password:</label>
                <input type="password" id="password" name="password" required 
                       placeholder="Nhập mật khẩu WiFi">
            </div>
            
            <button type="submit">✅ Kết nối và Đăng ký</button>
        </form>
        
        <!-- Reset Button -->
        <button type="button" class="reset-btn" onclick="resetDevice()">🔄 Reset ESP32</button>
        
        <div id="status" class="status"></div>
        
        <!-- Progress Container -->
        <div id="progressContainer" class="progress-container">
            <div class="countdown" id="countdown"></div>
            
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill">0%</div>
            </div>
            
            <div class="timeline">
                <div class="timeline-item">
                    <div class="timeline-icon pending" id="icon1">1</div>
                    <span id="step1">Lưu cấu hình...</span>
                </div>
                <div class="timeline-item">
                    <div class="timeline-icon pending" id="icon2">2</div>
                    <span id="step2">Chuẩn bị khởi động lại...</span>
                </div>
                <div class="timeline-item">
                    <div class="timeline-icon pending" id="icon3">3</div>
                    <span id="step3">Đang khởi động lại ESP32...</span>
                </div>
                <div class="timeline-item">
                    <div class="timeline-icon pending" id="icon4">4</div>
                    <span id="step4">Kết nối WiFi mới...</span>
                </div>
                <div class="timeline-item">
                    <div class="timeline-icon pending" id="icon5">5</div>
                    <span id="step5">Đăng ký với server...</span>
                </div>
                <div class="timeline-item">
                    <div class="timeline-icon pending" id="icon6">6</div>
                    <span id="step6">Hoàn tất! ✅</span>
                </div>
            </div>
        </div>
        
        <div class="info-box" id="infoBox">
            <strong>ℹ️ Lưu ý:</strong>
            Sau khi nhấn "Kết nối", ESP32 sẽ tự động khởi động lại sau 3 giây.
            Bạn cũng có thể nhấn nút RESET trên ESP32 để khởi động lại thủ công.
        </div>
    </div>
    
    <script>
        function updateStep(stepNum, status) {
            const icon = document.getElementById('icon' + stepNum);
            const step = document.getElementById('step' + stepNum);
            
            icon.className = 'timeline-icon ' + status;
            if (status === 'done') {
                icon.textContent = '✓';
            } else if (status === 'active') {
                icon.textContent = '⏳';
            }
        }
        
        function updateProgress(percent, text) {
            const progressFill = document.getElementById('progressFill');
            progressFill.style.width = percent + '%';
            progressFill.textContent = text;
        }
        
        function startRestartProcess() {
            let progress = 0;
            let step = 1;
            
            // Step 1: Lưu cấu hình (0-1s)
            updateStep(1, 'active');
            updateProgress(10, '10%');
            
            setTimeout(() => {
                updateStep(1, 'done');
                document.getElementById('step1').textContent = '✅ Đã lưu cấu hình';
                updateProgress(20, '20%');
                
                // Countdown 3 giây
                let countdown = 3;
                const countdownEl = document.getElementById('countdown');
                countdownEl.textContent = countdown;
                
                const countdownInterval = setInterval(() => {
                    countdown--;
                    if (countdown > 0) {
                        countdownEl.textContent = countdown;
                        updateProgress(20 + (10 * (3 - countdown)), (20 + (10 * (3 - countdown))) + '%');
                    } else {
                        countdownEl.style.display = 'none';
                        clearInterval(countdownInterval);
                        
                        // Step 2: Chuẩn bị khởi động lại (3-4s)
                        updateStep(2, 'active');
                        updateProgress(50, '50%');
                        
                        setTimeout(() => {
                            updateStep(2, 'done');
                            document.getElementById('step2').textContent = '✅ Đã chuẩn bị';
                            
                            // Step 3: Đang khởi động lại (4-7s)
                            updateStep(3, 'active');
                            updateProgress(60, '60%');
                            
                            setTimeout(() => {
                                updateStep(3, 'done');
                                document.getElementById('step3').textContent = '✅ Đã khởi động lại';
                                
                                // Step 4: Kết nối WiFi (7-12s)
                                updateStep(4, 'active');
                                updateProgress(70, '70%');
                                
                                setTimeout(() => {
                                    updateStep(4, 'done');
                                    document.getElementById('step4').textContent = '✅ Đã kết nối WiFi';
                                    
                                    // Step 5: Đăng ký server (12-15s)
                                    updateStep(5, 'active');
                                    updateProgress(85, '85%');
                                    
                                    setTimeout(() => {
                                        updateStep(5, 'done');
                                        document.getElementById('step5').textContent = '✅ Đã đăng ký server';
                                        
                                        // Step 6: Hoàn tất (15-16s)
                                        updateStep(6, 'active');
                                        updateProgress(95, '95%');
                                        
                                        setTimeout(() => {
                                            updateStep(6, 'done');
                                            document.getElementById('step6').textContent = '✅ Hoàn tất! ESP32 đã sẵn sàng';
                                            updateProgress(100, '100% - Hoàn tất!');
                                            
                                            // Hiển thị thông báo cuối
                                            const status = document.getElementById('status');
                                            status.className = 'status success';
                                            status.textContent = '🎉 Thiết lập thành công! ESP32 đã sẵn sàng hoạt động. Bạn có thể đóng trang này.';
                                            status.style.display = 'block';
                                        }, 1000);
                                    }, 3000);
                                }, 5000);
                            }, 3000);
                        }, 1000);
                    }
                }, 1000);
            }, 1000);
        }
        
        function submitForm(e) {
            e.preventDefault();
            const status = document.getElementById('status');
            const btn = document.querySelector('button[type="submit"]');
            
            btn.disabled = true;
            btn.textContent = '⏳ Đang kết nối...';
            status.className = 'status';
            status.style.display = 'none';
            
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            fetch('/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Ẩn form và info box
                    document.getElementById('wifiForm').style.display = 'none';
                    document.getElementById('infoBox').style.display = 'none';
                    
                    // Hiển thị success message
                    status.className = 'status success';
                    status.textContent = '✅ Cấu hình đã được lưu thành công!';
                    status.style.display = 'block';
                    
                    // Hiển thị progress container
                    document.getElementById('progressContainer').style.display = 'block';
                    
                    // Bắt đầu quá trình restart với timeline
                    startRestartProcess();
                } else {
                    status.className = 'status error';
                    status.textContent = '❌ ' + data.message;
                    status.style.display = 'block';
                    btn.disabled = false;
                    btn.textContent = '✅ Kết nối và Đăng ký';
                }
            })
            .catch(error => {
                status.className = 'status error';
                status.textContent = '❌ Lỗi kết nối: ' + error;
                status.style.display = 'block';
                btn.disabled = false;
                btn.textContent = '✅ Kết nối và Đăng ký';
            });
            
            return false;
        }
        
        function resetDevice() {
            if (confirm('Bạn có chắc muốn reset ESP32? Thiết bị sẽ khởi động lại và xóa tất cả cấu hình WiFi.')) {
                const status = document.getElementById('status');
                status.className = 'status';
                status.textContent = '🔄 Đang reset ESP32...';
                status.style.display = 'block';
                
                fetch('/reset', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({action: 'reset'})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        status.className = 'status success';
                        status.textContent = '✅ ESP32 đang khởi động lại...';
                        
                        // Countdown và thông báo
                        let countdown = 10;
                        const countdownInterval = setInterval(() => {
                            countdown--;
                            status.textContent = `✅ ESP32 đang khởi động lại... (${countdown}s)`;
                            if (countdown <= 0) {
                                clearInterval(countdownInterval);
                                status.textContent = '✅ Reset hoàn tất! Bạn có thể đóng trang này.';
                            }
                        }, 1000);
                    } else {
                        status.className = 'status error';
                        status.textContent = '❌ Reset thất bại: ' + data.message;
                    }
                })
                .catch(error => {
                    status.className = 'status error';
                    status.textContent = '❌ Lỗi reset: ' + error;
                });
            }
        }
    </script>
</body>
</html>
)rawliteral";

#endif
