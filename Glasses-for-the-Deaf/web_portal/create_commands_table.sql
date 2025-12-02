-- Tạo bảng device_commands để lưu các lệnh gửi đến ESP32
CREATE TABLE IF NOT EXISTS device_commands (
    id SERIAL PRIMARY KEY,
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    command_type VARCHAR(50) NOT NULL, -- 'reset', 'wifi_update', etc.
    command_data JSONB DEFAULT '{}', -- Dữ liệu lệnh dạng JSON
    executed BOOLEAN DEFAULT FALSE, -- Đã thực hiện chưa
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP NULL
);

-- Tạo index để tăng tốc truy vấn
CREATE INDEX IF NOT EXISTS idx_device_commands_device_id ON device_commands(device_id);
CREATE INDEX IF NOT EXISTS idx_device_commands_executed ON device_commands(executed);
CREATE INDEX IF NOT EXISTS idx_device_commands_created_at ON device_commands(created_at);

-- Thêm comment
COMMENT ON TABLE device_commands IS 'Lưu các lệnh cần gửi đến ESP32 devices';
COMMENT ON COLUMN device_commands.command_type IS 'Loại lệnh: reset, wifi_update, etc.';
COMMENT ON COLUMN device_commands.command_data IS 'Dữ liệu lệnh dạng JSON';
COMMENT ON COLUMN device_commands.executed IS 'Trạng thái thực hiện lệnh';