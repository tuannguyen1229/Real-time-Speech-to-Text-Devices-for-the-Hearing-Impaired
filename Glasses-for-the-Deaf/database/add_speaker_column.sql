-- Migration script: Thêm cột speaker_id vào bảng text_history
-- Chạy script này để cập nhật database hiện có

-- Thêm cột speaker_id vào bảng text_history
ALTER TABLE text_history 
ADD COLUMN speaker_id VARCHAR(50) DEFAULT 'Unknown';

-- Thêm comment cho cột mới
COMMENT ON COLUMN text_history.speaker_id IS 'Thông tin người nói từ Speaker Diarization (speaker_0, speaker_1, etc.)';

-- Tạo index cho cột speaker_id để tối ưu query
CREATE INDEX idx_text_history_speaker_id ON text_history(speaker_id);

-- Kiểm tra kết quả
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'text_history' 
ORDER BY ordinal_position;

-- Hiển thị thông báo hoàn thành
SELECT 'Migration completed successfully! Speaker diarization column added.' as status;