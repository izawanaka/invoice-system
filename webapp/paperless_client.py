"""
paperless_client.py -- klien Paperless-ngx LANGSUNG untuk app invoice.

Pola diambil dari sawit-app/app/paperless.py (31 Jul 2026). Kunci: penanganan
DUPLIKAT yang anggun -- kalau Paperless menolak karena checksum identik, dokumen
lama DIPAKAI ULANG (bukan error). Owner memilih perilaku ini (bukan memaksa
Paperless menerima duplikat, yang memang tidak aman).

Config lewat environment (.env, TIDAK di-hardcode):
  PAPERLESS_BASE_URL   mis. http://192.168.68.107:8010
  PAPERLESS_TOKEN      token API user 'invoice-app'

Semua fail-safe: kalau Paperless nonaktif/tak terjangkau, fungsi tingkat-tinggi
mengembalikan (None, status) alih-alih melempar -- pemanggil (generate invoice,
unggah resi, dst) TIDAK boleh gagal hanya karena arsip Paperless gagal.
"""
import os
import re
import time

import httpx


def _base() -> str:
    return (os.getenv("PAPERLESS_BASE_URL") or "").rstrip("/")


def _headers() -> dict:
    return {"Authorization": "Token " + os.getenv("PAPERLESS_TOKEN", "")}


def paperless_aktif() -> bool:
    return bool(_base() and os.getenv("PAPERLESS_TOKEN"))


def _client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(base_url=_base(), headers=_headers(), timeout=timeout)


def unggah(isi: bytes, nama_file: str, judul: str, created=None) -> str:
    """Kirim dokumen ke Paperless (konsumsi ASINKRON). Return task UUID (str).
    Raise RuntimeError kalau Paperless menolak permintaan unggah."""
    data = {"title": judul}
    if created is not None:
        data["created"] = created.isoformat() if hasattr(created, "isoformat") else str(created)
    with _client() as c:
        r = c.post("/api/documents/post_document/", data=data,
                   files={"document": (nama_file, isi)})
    if r.status_code != 200:
        raise RuntimeError("Paperless menolak upload (HTTP %s): %s" % (r.status_code, r.text[:200]))
    ct = r.headers.get("content-type", "")
    task = r.json() if ct.startswith("application/json") else r.text
    return str(task).strip().strip('"')


def cek_task(task_uuid: str):
    """Return (STATUS_UPPER, doc_id | None). STATUS: PENDING/STARTED/SUCCESS/FAILURE/UNKNOWN."""
    try:
        with _client(30) as c:
            r = c.get("/api/tasks/", params={"task_id": task_uuid})
    except httpx.HTTPError:
        return ("UNKNOWN", None)
    if r.status_code != 200:
        return ("UNKNOWN", None)
    arr = r.json()
    if isinstance(arr, dict):
        arr = arr.get("results", [])
    if not arr:
        return ("UNKNOWN", None)
    t = arr[0]
    doc = t.get("related_document")
    if not doc:
        rd = t.get("result_data")
        if isinstance(rd, dict):
            doc = rd.get("document_id")
    if not doc:
        ids = t.get("related_document_ids") or []
        doc = ids[0] if ids else None
    return ((t.get("status") or "UNKNOWN").upper(), int(doc) if doc else None)


def _pesan_task(task_uuid: str) -> str:
    try:
        with _client(30) as c:
            r = c.get("/api/tasks/", params={"task_id": task_uuid})
        arr = r.json() if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return ""
    if isinstance(arr, dict):
        arr = arr.get("results", [])
    if not arr:
        return ""
    return str(arr[0].get("result") or arr[0].get("result_data") or "")


def duplikat_dari(task_uuid: str):
    """doc_id LAMA kalau task gagal karena duplikat; selain itu None."""
    m = re.search(r"duplicate of .+? \(#(\d+)\)", _pesan_task(task_uuid))
    return int(m.group(1)) if m else None


def arsipkan(isi: bytes, nama_file: str, judul: str, created=None,
             attempts: int = 10, delay: float = 1.5):
    """Upload + poll sampai selesai. Return (doc_id | None, status).
      status = 'baru'      -> tersimpan, doc_id valid
               'duplikat'  -> sudah pernah ada; doc_id = dokumen lama (dipakai ulang)
               'pending'   -> masih diproses saat attempts habis (doc_id None)
               'nonaktif'  -> Paperless tidak dikonfigurasi (fail-safe)
               'gagal:...' -> error lain (doc_id None)
    """
    if not paperless_aktif():
        return (None, "nonaktif")
    try:
        task = unggah(isi, nama_file, judul, created=created)
    except Exception as e:
        return (None, "gagal:" + str(e)[:150])
    for _ in range(attempts):
        time.sleep(delay)
        status, doc_id = cek_task(task)
        if status == "SUCCESS" and doc_id:
            return (doc_id, "baru")
        if status == "FAILURE":
            dup = duplikat_dari(task)
            if dup:
                return (dup, "duplikat")
            return (None, "gagal")
    return (None, "pending")


def unduh(doc_id: int):
    """Ambil isi dokumen dari Paperless (diproxy ke browser pengguna).
    Return (bytes, content_type, nama_file). Raise RuntimeError kalau gagal."""
    with _client(60) as c:
        r = c.get("/api/documents/%s/download/" % int(doc_id))
    if r.status_code == 404:
        raise RuntimeError("Dokumen %s tidak ditemukan di Paperless" % doc_id)
    if r.status_code != 200:
        raise RuntimeError("Paperless menolak unduh dokumen %s (HTTP %s)" % (doc_id, r.status_code))
    ct = r.headers.get("content-type", "application/octet-stream")
    cd = r.headers.get("content-disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
    nama = m.group(1) if m else ("dokumen-%s" % doc_id)
    return r.content, ct, nama


def hapus(doc_id: int) -> bool:
    """Hapus dokumen (masuk trash Paperless). Return True kalau sukses/sudah tidak ada.
    Dipakai HANYA untuk cleanup uji; jalur produksi memakai 'Lepas' (putus tautan,
    berkas tetap di Paperless) di lapisan aplikasi, bukan hapus."""
    try:
        with _client(30) as c:
            r = c.delete("/api/documents/%s/" % int(doc_id))
    except httpx.HTTPError:
        return False
    return r.status_code in (204, 404)
