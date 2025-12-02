-- PostgreSQL Database Schema cho ESP32 Management Portal
-- Tạo database: CREATE DATABASE esp32_management;

-- Bảng người dùng
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(15) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bảng thiết bị ESP32
CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    device_name VARCHAR(100) NOT NULL,
    device_id VARCHAR(50) UNIQUE NOT NULL, -- MAC address hoặc unique ID từ ESP32
    esp32_ip VARCHAR(15), -- IP của ESP32 trong mạng local
    client_ip VARCHAR(15), -- IP public của ESP32 (qua proxy/router)
    mac_address VARCHAR(17), -- MAC address của ESP32
    rssi INTEGER, -- Cường độ tín hiệu WiFi
    status VARCHAR(20) DEFAULT 'offline', -- online, offline, error
    last_seen TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bảng cấu hình WiFi
CREATE TABLE wifi_configs (
    id SERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    wifi_name VARCHAR(100) NOT NULL,
    wifi_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bảng lịch sử text (transcript) từ ESP32
CREATE TABLE text_history (
    id SERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    transcript_text TEXT NOT NULL,
    is_final BOOLEAN DEFAULT false, -- true cho final transcript, false cho partial
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bảng session đăng nhập
CREATE TABLE user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes để tối ưu performance
CREATE INDEX idx_devices_user_id ON devices(user_id);
CREATE INDEX idx_wifi_configs_device_id ON wifi_configs(device_id);
CREATE INDEX idx_text_history_device_id ON text_history(device_id);
CREATE INDEX idx_text_history_recorded_at ON text_history(recorded_at);
CREATE INDEX idx_user_sessions_token ON user_sessions(session_token);
CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);

-- Trigger để tự động cập nhật updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_devices_updated_at BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_wifi_configs_updated_at BEFORE UPDATE ON wifi_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Dữ liệu mẫu (optional)
-- INSERT INTO users (phone_number, password_hash) VALUES 
-- ('0123456789', '$2b$12$example_hash_here');