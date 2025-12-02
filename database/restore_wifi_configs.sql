-- Script khôi phục table wifi_configs
-- Chạy script này để tạo lại table wifi_configs đã bị xóa

-- Tạo lại bảng wifi_configs
CREATE TABLE IF NOT EXISTS wifi_configs (
    id SERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    wifi_name VARCHAR(100) NOT NULL,
    wifi_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tạo index để tối ưu hóa truy vấn
CREATE INDEX IF NOT EXISTS idx_wifi_configs_device_id ON wifi_configs(device_id);
CREATE INDEX IF NOT EXISTS idx_wifi_configs_active ON wifi_configs(device_id, is_active);

-- Thêm comment cho table
COMMENT ON TABLE wifi_configs IS 'Bảng lưu cấu hình WiFi cho từng thiết bị ESP32';
COMMENT ON COLUMN wifi_configs.device_id IS 'ID thiết bị (foreign key từ bảng devices)';
COMMENT ON COLUMN wifi_configs.wifi_name IS 'Tên WiFi (SSID)';
COMMENT ON COLUMN wifi_configs.wifi_password IS 'Mật khẩu WiFi';
COMMENT ON COLUMN wifi_configs.is_active IS 'Cấu hình có đang active không (chỉ 1 config active/device)';

-- Kiểm tra table đã tạo thành công
SELECT 'Table wifi_configs restored successfully!' as status;