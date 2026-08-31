"""
paperless_push.py -- lapisan TIPIS & FAIL-SAFE di atas paperless_client untuk
mendorong berkas dokumen (Invoice PDF, BAP nota, PO scan, Resi) ke Paperless saat
dokumen dibuat, tanpa pernah menggagalkan alur utama.

Aturan: SEMUA fungsi di sini menelan error (return status string), TIDAK melempar.
Pemanggil (generate invoice, unggah resi, dll) tak boleh gagal hanya karena arsip
Paperless gagal -- Paperless adalah cermin, bukan sumber kebenaran.
"""
import os

import paperless_client as pc


def _resolve(path):
    """Kembalikan path absolut yang benar-benar ada, atau None.
    Coba apa adanya, lalu relatif ke INVOICE_DATA (mount /data)."""
    if not path:
        return None
    if os.path.isabs(path) and os.path.exists(path):
        return path
    base = os.getenv("INVOICE_DATA") or "/data"
    cand = os.path.join(base, path)
    if os.path.exists(cand):
        return cand
    if os.path.exists(path):
        return path
    return None


def arsip_path(path, judul, created=None):
    """Baca berkas lokal & arsipkan ke Paperless. Return (doc_id|None, status).
    status ikut paperless_client.arsipkan + tambahan 'gagal:file-*' kalau berkas
    tak ada. NEVER raises."""
    try:
        if not pc.paperless_aktif():
            return (None, "nonaktif")
        real = _resolve(path)
        if not real:
            return (None, "gagal:file-tidak-ada")
        with open(real, "rb") as f:
            isi = f.read()
        nama = os.path.basename(real)
        return pc.arsipkan(isi, nama, judul, created=created)
    except Exception as e:  # noqa: BLE001 -- fail-safe by design
        return (None, "gagal:" + str(e)[:150])


def set_doc_id(conn, tabel, kolom_id, id_nilai, kolom_doc, doc_id):
    """UPDATE terarah menyimpan doc_id Paperless ke satu baris. NEVER raises.
    Return True kalau tepat 1 baris diperbarui. Memakai koneksi yang diberi
    pemanggil (pemanggil yang commit/rollback)."""
    try:
        if doc_id is None:
            return False
        cur = conn.cursor()
        cur.execute(
            "UPDATE %s SET %s = %%s WHERE %s = %%s" % (tabel, kolom_doc, kolom_id),
            (str(doc_id), id_nilai),
        )
        return cur.rowcount == 1
    except Exception as e:  # noqa: BLE001
        print("  PERINGATAN paperless_push.set_doc_id gagal: %s" % str(e)[:150])
        return False
