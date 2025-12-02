-- Xóa cột speaker_id khỏi bảng text_history
-- Không cần phân biệt người nói nữa

ALTER TABLE text_history DROP COLUMN IF EXISTS speaker_id;
ALTER TABLE text_history DROP COLUMN IF EXISTS confidence_score;

-- Xác nhận thay đổi
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'text_history'
ORDER BY ordinal_position;
