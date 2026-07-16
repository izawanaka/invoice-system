# DESIGN.md — Sistem Invoice Otomatis KKS & DKP

**Status:** STABIL (v1.0, 13 Juli 2026)
**Lokasi:** `/home/izawa/invoice-system/` di VM102 (docker-host)
**Wajib dibaca sebelum mengubah apa pun di folder ini.**

Dokumen ini adalah **kontrak desain**. Isinya bukan catatan sejarah, tapi aturan yang
mengikat. Kalau ada perubahan yang melanggar salah satu invariant di bawah, perubahan
itu SALAH — bukan dokumennya yang harus diubah.

---

## 1. Invariant (aturan yang TIDAK BOLEH dilanggar)

**I1. Saldo PO hanya boleh berubah bersamaan dengan tercatatnya invoice.**
Tidak boleh ada jalur kode yang menaikkan `used_qty` tanpa insert baris `invoices`, atau
sebaliknya. Keduanya harus dalam SATU transaksi database yang sama.

**I2. Tidak ada efek samping permanen sebelum PDF benar-benar berhasil ditulis.**
Urutan wajib: buka transaksi → kunci baris PO (`SELECT ... FOR UPDATE`) → tulis PDF →
kalau sukses: UPDATE PO + INSERT invoice + INSERT bap → `COMMIT`.
Kalau PDF gagal di tengah: `ROLLBACK` total. Tidak boleh ada saldo terpotong, nomor
invoice terpakai, atau baris nyangkut setengah jalan.

**I3. Nomor invoice tidak boleh mundur.**
Sumber nomor = `max(MAX(seq_no) di Postgres, isi counter file)` + 1.
Alasan `max()`: riwayat invoice lama (DKP 001–088, KKS 001–011) TIDAK ADA di Postgres
(tidak bisa direkonstruksi, lihat §4). Kalau hanya baca DB, nomor bisa jatuh ke 001.
Counter file = lantai bawah; DB = pengaman kalau file hilang/rusak.

**I4. Counter file hanya boleh ditulis SETELAH commit sukses.**
Jangan pernah menulis `last_invoice_no*.txt` di awal proses (bug ini pernah terjadi:
counter DKP kebablasan ke 098 padahal invoice sah terakhir 088).

**I5. Postgres (`bisnis-db`) adalah sumber kebenaran untuk PO & invoice.**
`po_tracker.json` dan `po_tracker_kks.json` adalah **turunan** — di-regenerate dari
Postgres setiap commit sukses (`db_helper.refresh_po_tracker_json`). Jangan pernah
memperlakukan file JSON itu sebagai sumber independen.

**I6. Kredensial tidak pernah masuk git.**
`.bisnis_db_credentials`, `anthropic_key.txt`, `*.pem`, `*_key.txt` → sudah di
`.gitignore`. Jangan pernah hardcode kredensial di file `.py`.

**I7. Split PO harus mendebit tiap PO secara terpisah.**
Kalau 1 BAP kepotong ke 2 PO, `PO_SPLITS = [(po_a, qty_a), (po_b, qty_b)]` dan KEDUANYA
di-`UPDATE`. Bug lama: hanya PO pertama yang didebit, penuh — PO kedua tidak tersentuh.

**I8. PO baru WAJIB masuk Postgres, bukan cuma JSON.**
`/addpo` menyimpan ke tabel `purchase_orders` dulu; `po_tracker*.json` di-regenerate dari DB
setelahnya. Kalau insert DB gagal, PO TIDAK tersimpan di mana pun. Alasan: invoice generator
memvalidasi PO di DB (I2) — PO yang cuma ada di JSON akan ditolak saat bikin invoice.

---

## 2. Arsitektur alur

```
Telegram (Izawa Ai Bot)
  └─ foto/PDF BAP → OCR (ocr_bap.py, Claude vision)
       └─ konfirmasi ke user → user ketik SELESAI
            └─ addpo.py (SELESAI handler)
                 └─ tulis bap_input.json / bap_input_kks.json
                      └─ bap_to_invoice.py   (DKP, kg,  badan_usaha_id=4)
                         bap_to_invoice_kks.py (KKS, m3, badan_usaha_id=5)
                           ├─ hitung nomor invoice (I3)
                           ├─ pilih PO aktif + hitung PO_SPLITS (I7)
                           └─ jalankan invoice_dkp.py / invoice_kks.py (via /tmp)
                                └─ TRANSAKSI ATOMIK (I1, I2):
                                     kunci PO → tulis PDF → commit PO+invoice+bap
                                     → refresh po_tracker*.json dari DB (I5)
```

**Perbedaan DKP vs KKS:**
| | DKP | KKS |
|---|---|---|
| `badan_usaha_id` | 4 | 5 |
| Satuan | kg | m3 |
| PPN | 12% atas DPP (11/12 × subtotal) | **Non-PKP: dpp=0, ppn=0**, grand = subtotal |
| Site | Suring, Jembayan, Sebakis, Sesayap | Senyiur |

---

## 3. File & tanggung jawabnya

| File | Tanggung jawab | Boleh diubah? |
|---|---|---|
| `db_helper.py` | Satu-satunya tempat baca kredensial DB + koneksi + refresh JSON turunan | Hati-hati |
| `invoice_dkp.py` / `invoice_kks.py` | Render PDF + TRANSAKSI ATOMIK. **Jantung sistem.** | **Hanya dengan alasan kuat + test hijau** |
| `bap_to_invoice.py` / `_kks.py` | Penomoran, pilih PO, hitung split, panggil generator | Hati-hati |
| `addpo.py` | Handler command Telegram (`/addpo`, `/syncpo`, `TAMBAH`, `SELESAI`) | Boleh |
| `ocr_bap.py` | OCR BAP via Claude | Boleh |
| `test_invoice_flow.py` | **Penjaga invariant.** 6 skenario, 22 assertion. | Boleh ditambah, jangan dilemahkan |
| `.bisnis_db_credentials` | Kredensial DB (chmod 600, gitignored) | Jangan commit |

---

## 4. Keputusan yang sudah diambil (jangan diulang perdebatannya)

**K1. Riwayat invoice lama TIDAK di-backfill.**
Dicoba 13 Juli 2026: log baris-per-invoice di `PO_Tracker_*.xlsx` ternyata sudah ter-reset
(DKP nyisa 1 baris, KKS 3 baris — bukan 88 dan 11). Sumber lain tidak ada. Jadi:
- **Saldo PO agregat** → akurat, sudah di-backfill ke Postgres ✅
- **Riwayat invoice per baris** → mulai bersih dari invoice DKP 089 / KKS 012 ke depan
- Konsekuensinya I3 (`max()`) wajib ada, jangan dihapus.

**K2. Node Postgres di n8n dihapus.**
`PG: Update PO`, `PG: Insert BAP`, `PG: Insert Invoice` dulu jalan PARALEL dengan pesan
Telegram "berhasil" — jadi kalau DB gagal, user tetap dikasih tau "sukses". Sekarang semua
pencatatan DB terjadi di dalam transaksi atomik di script. **Jangan tambahkan node Postgres
lagi di workflow n8n untuk pencatatan invoice/PO.**

**K3. Satu bot Telegram = satu workflow n8n.**
Telegram hanya izinkan 1 webhook aktif per bot. Dua workflow berbagi bot = webhook saling
rebut = salah satu mati diam-diam. Sudah dipisah: invoice pakai `Izawa Ai Bot`, validasi
laporan pakai `Validasi Bot`.

**K4. Versi kontrol pakai git, bukan file `.bak`.**
Jangan bikin `namafile.bak-tanggal` lagi. Pakai `git commit`.

---

## 5. Cara aman mengembangkan sistem ini

1. **Baca dokumen ini + `Business/Invoice-KKS-DKP/progress.md` di Obsidian.**
2. Jalankan `python3 test_invoice_flow.py` → pastikan **hijau (0 FAIL)** SEBELUM mulai ngoding.
3. Buat perubahan.
4. Jalankan test lagi → **harus tetap hijau.** Kalau merah, perubahan Anda melanggar invariant.
5. Kalau menambah fitur, **tambahkan skenario test baru** untuk fitur itu.
6. `git commit` dengan pesan jelas.
7. Catat di `progress.md` (append, jangan timpa).

**Aturan untuk Claude / AI assistant:**
- Jangan pernah mengubah nomor invoice, saldo PO, atau menghapus file invoice tanpa
  konfirmasi eksplisit dari owner — sekalipun bug-nya terlihat jelas.
- Selalu verifikasi kondisi terkini lewat tool, jangan berasumsi dari histori chat.
- Perubahan pada §1 (Invariant) hanya boleh atas permintaan eksplisit owner.

---

## 6. Riwayat versi

| Versi | Tanggal | Perubahan |
|---|---|---|
| v1.0 | 13 Juli 2026 | Transaksi atomik (I1, I2), fix counter (I4), fix split-PO (I7), Postgres jadi source of truth (I5), test suite 22 assertion, git + gitignore kredensial (I6) |
| v1.1 | 13 Juli 2026 | `/addpo` format satu-pesan berlabel + simpan ke Postgres (I8) + dukungan KKS/Senyiur. `/syncpo` baca dari DB. Kegagalan invoice dilaporkan eksplisit ke Telegram. |
