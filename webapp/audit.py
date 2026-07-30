"""
audit.py -- pencatatan app_audit_log. Dipanggil oleh endpoint TULIS (PO baru,
generate invoice, update status bayar, upload faktur pajak) supaya ada jejak
"siapa mengubah apa" -- penting karena multi-user pegang data finansial
(lihat 02_db_schema.md #4).

Audit log ditulis di TRANSAKSI YANG SAMA dengan perubahan data (commit bersama)
kalau dipanggil sebelum conn.commit() milik pemanggil; kalau audit gagal karena
alasan tak terduga, itu TIDAK BOLEH menggagalkan aksi utama -- makanya dibungkus
try/except di sini, bukan di tiap caller.
"""
import json


def log_audit(conn, user_id: int, aksi: str, entity: str, entity_id: str, detail: dict = None):
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO app_audit_log (user_id, aksi, entity, entity_id, detail) "
            "VALUES (%s, %s, %s, %s, %s)",
            (user_id, aksi, entity, str(entity_id) if entity_id is not None else None,
             json.dumps(detail or {}, ensure_ascii=False, default=str)),
        )
    except Exception as e:
        # Jangan biarkan kegagalan audit log menggagalkan transaksi utama.
        print(f"  PERINGATAN: gagal tulis app_audit_log: {e}")
