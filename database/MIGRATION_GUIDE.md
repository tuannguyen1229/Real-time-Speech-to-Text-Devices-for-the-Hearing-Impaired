# Hướng dẫn Migration Database

## Xóa tính năng Speaker Diarization

Hệ thống đã được cập nhật để loại bỏ tính năng phân biệt người nói (speaker diarization). 

### Bước 1: Backup Database (Khuyến nghị)

```bash
pg_dump -U postgres esp32_management > backup_before_migration.sql
```

### Bước 2: Chạy Migration Script

Kết nối vào PostgreSQL và chạy script:

```bash
psql -U postgres -d esp32_management -f database/remove_speaker_column.sql
```

Hoặc chạy trực tiếp trong psql:

```sql
\c esp32_management
\i database/remove_speaker_column.sql
```

### Bước 3: Kiểm tra kết quả

Sau khi chạy script, bảng `text_history` sẽ chỉ còn các cột:
- id
- device_id
- transcript_text
- is_final
- recorded_at
- created_at

### Lưu ý

- Script sẽ xóa cột `speaker_id` và `confidence_score`
- Dữ liệu cũ sẽ bị mất (chỉ mất thông tin speaker, transcript vẫn giữ nguyên)
- Nếu bạn tạo database mới, sử dụng file `schema.sql` đã được cập nhật

### Rollback (Nếu cần)

Nếu muốn khôi phục lại tính năng speaker diarization:

```bash
psql -U postgres -d esp32_management -f database/add_speaker_column.sql
```
