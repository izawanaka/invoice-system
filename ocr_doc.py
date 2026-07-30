#!/usr/bin/env python3
"""
ocr_doc.py -- OCR SATU PINTU untuk dokumen yang dikirim ke bot Telegram invoice.

Menggantikan pemanggilan ocr_bap.py di n8n (node 'Fix Base64').

APA YANG BERUBAH DIBANDING ocr_bap.py:
  - ocr_bap.py MENGASUMSIKAN setiap file adalah BAP.
  - ocr_doc.py MENGKLASIFIKASI dulu: BAP, PO, atau LAIN -- lalu merutekan.

PRINSIP (lihat DESIGN.md):
  - TIDAK ADA efek permanen di sini. Script ini hanya membaca dokumen dan menulis
    file STATE (addpo_state.json / multi_bap_state.json). Penyimpanan ke database
    baru terjadi setelah user mengetik YA (PO) atau SELESAI (BAP).
  - Jalur PO TIDAK menduplikasi logika addpo.py. Ia menyusun teks berlabel '/addpo'
    lalu memanggil addpo.process(). Semua validasi, konfirmasi, insert Postgres (I8),
    dan regenerate po_tracker*.json tetap ditangani addpo.py yang sudah teruji.
  - Kalau klasifikasi/pembacaan meleset, user melihatnya di pesan konfirmasi dan
    tinggal ketik BATAL. Tidak ada data yang berubah.

CATATAN PENTING soal ocr_bap.py:
  ocr_bap.py mendefinisikan save_to_state() DUA KALI. Saat dijalankan sebagai script,
  versi pertama (yang menangani qty_m3) yang dipakai. Tapi kalau di-IMPORT, versi kedua
  (TANPA qty_m3) yang menang -- itu akan merusak Senyiur/KKS. Maka fungsi penyimpan
  state BAP di bawah SENGAJA disalin, BUKAN di-import dari ocr_bap.
  (ocr_bap.py sendiri tidak disentuh -- di luar lingkup perubahan ini.)
"""
import os
import config

import subprocess, json, urllib.request, sys, os, base64

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_bap          # HANYA untuk konstanta (import tidak menjalankan apa pun)
import addpo            # dipakai ulang untuk seluruh alur PO
import pt_site         # pemetaan nama PT -> site (fix tebakan site salah)

TG_TOKEN           = ocr_bap.TG_TOKEN
ANTHROPIC_KEY_FILE = ocr_bap.ANTHROPIC_KEY_FILE
BAP_STATE_FILE     = config.d("multi_bap_state.json")
MODEL              = "claude-opus-4-6"

SITES = ["Suring", "Jembayan", "Sebakis", "Sesayap", "Senyiur", "MPS"]


# ---------------------------------------------------------------- fungsi murni
# (tidak menyentuh jaringan/DB -- bisa diuji lewat --selftest)

def paksa_jenis(caption):
    """Caption pada foto/PDF boleh MEMAKSA jenis dokumen, mengalahkan tebakan AI.
    Ini jaring pengaman kalau klasifikasi otomatis meleset."""
    c = (caption or "").strip().lower()
    if not c:
        return None
    if "addpo" in c or c.startswith("/po") or c == "po":
        return "PO"
    if "bap" in c:
        return "BAP"
    return None


def paksa_site(caption):
    """Caption boleh MEMAKSA site, mengalahkan tebakan AI -- sama seperti
    paksa_jenis() memaksa jenis dokumen. Jaring pengaman kalau site salah dibaca
    dari foto (mis. 'Jembayan' malah tertebak 'Suring'). Kembalikan nama site
    kanonik dari SITES, atau None kalau caption tidak menyebut site mana pun."""
    c = (caption or "").strip().lower()
    if not c:
        return None
    for s in SITES:
        if s.lower() in c:
            return s
    return None

def bangun_teks_addpo(ocr):
    """Ubah hasil OCR PO menjadi pesan berlabel yang dimengerti addpo.parse_labeled().
    Field yang tidak terbaca sengaja TIDAK ditulis -- addpo.py akan menanyakannya
    satu per satu (perilaku yang sudah ada, tidak diubah)."""
    baris = ["/addpo"]
    if ocr.get("po_no"):
        baris.append(f"PO: {ocr['po_no']}")
    if ocr.get("site"):
        baris.append(f"Site: {ocr['site']}")
    if ocr.get("customer"):
        baris.append(f"Customer: {ocr['customer']}")
    if float(ocr.get("total_qty") or 0) > 0:
        baris.append(f"Total: {ocr['total_qty']}")
    if float(ocr.get("harga") or 0) > 0:
        baris.append(f"Harga: {ocr['harga']}")
    return "\n".join(baris)


def pesan_bap(ocr):
    qty = "tidak terbaca"
    if float(ocr.get("qty_m3") or 0) > 0:
        qty = f"{float(ocr['qty_m3']):,.2f} m3"
    elif float(ocr.get("qty_kg") or 0) > 0:
        qty = f"{float(ocr['qty_kg']):,.0f} Kg"

    kosong = (not ocr.get("no_bap") or not ocr.get("site") or qty == "tidak terbaca")
    kepala = "BAP diterima:" if not kosong else "BAP TIDAK TERBACA PENUH -- periksa dulu:"
    ekor = (
        "\n\nKetik SELESAI -> terbitkan invoice\nKirim BAP lagi -> gabung jadi 1 invoice"
        if not kosong else
        "\n\nJANGAN ketik SELESAI. Kirim ulang foto yang lebih jelas."
    )
    return (
        f"{kepala}\n\n"
        f"No BAP  : {ocr.get('no_bap') or 'tidak terbaca'}\n"
        f"Tanggal : {ocr.get('tanggal') or 'tidak terbaca'}\n"
        f"Site    : {ocr.get('site') or 'tidak terbaca'}\n"
        f"QTY     : {qty}" + ekor
    )


def simpan_state_bap(ocr):
    """Salinan sengaja dari ocr_bap.save_to_state() versi-1 (yang menangani qty_m3).
    Lihat catatan di docstring modul kenapa TIDAK di-import."""
    try:
        with open(BAP_STATE_FILE) as f:
            state = json.load(f)
    except Exception:
        state = {"active": False, "bap_list": [], "site": "", "inv_date": ""}
    entri = {
        "no_bap": ocr.get("no_bap", ""),
        "qty_kg": float(ocr.get("qty_kg", 0) or 0),
        "qty_m3": float(ocr.get("qty_m3", 0) or 0),
    }
    if not state.get("active"):
        state = {
            "active": True,
            "site": ocr.get("site", ""),
            "inv_date": ocr.get("tanggal", ""),
            "bap_list": [entri],
        }
    else:
        state["bap_list"].append(entri)
    with open(BAP_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- I/O

def bagian_dari_berkas(nama, data):
    """Ubah isi berkas (gambar ATAU PDF) jadi bagian gambar untuk dikirim ke model.

    SENGAJA dipisah dari ambil_gambar() supaya FIXTURE -- dokumen ASLI yang tersimpan di
    disk -- bisa diuji tanpa Telegram. Tanpa ini prompt OCR tidak punya jaring pengaman:
    bug "berat kotor 19.104 dibaca, bukan berat bersih 18.852" dan "customer terbaca nama
    perusahaan sendiri" LOLOS seluruh 74 test, karena test tidak pernah melihat dokumen
    sungguhan. Fixture-lah yang menangkapnya.
    """
    bagian = []
    if any(nama.lower().endswith(e) for e in [".jpg", ".jpeg", ".png", ".webp"]):
        ext = nama.split(".")[-1].lower()
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        bagian.append({"type": "image", "source": {"type": "base64",
                       "media_type": mime, "data": base64.b64encode(data).decode()}})
    else:
        with open("/tmp/doc.pdf", "wb") as f:
            f.write(data)
        subprocess.run(["pdftoppm", "-r", "120", "-png", "-l", "2",
                        "/tmp/doc.pdf", "/tmp/doc_p"], check=True, capture_output=True)
        for hal in ("1", "2"):
            p = f"/tmp/doc_p-{hal}.png"
            if os.path.exists(p):
                bagian.append({"type": "image", "source": {"type": "base64",
                               "media_type": "image/png",
                               "data": base64.b64encode(open(p, "rb").read()).decode()}})
    return bagian


# Berkas mentah terakhir yang diunduh -- dipakai bap_arsip untuk mengarsipkan BAP
# yang masuk lewat Telegram (keputusan owner 28 Jul 2026: BAP bisa dari 2 pintu,
# Telegram maupun web, dan keduanya WAJIB tercatat di app_bap_nota).
_BERKAS_TERAKHIR = {"nama": None, "data": None}


def ambil_gambar(file_id):
    r = urllib.request.urlopen(
        f"https://api.telegram.org/bot{TG_TOKEN}/getFile?file_id={file_id}")
    file_path = json.loads(r.read())["result"]["file_path"]
    data = urllib.request.urlopen(
        f"https://api.telegram.org/file/bot{TG_TOKEN}/{file_path}").read()
    _BERKAS_TERAKHIR["nama"] = os.path.basename(file_path)
    _BERKAS_TERAKHIR["data"] = data
    return bagian_dari_berkas(file_path, data)


PROMPT = (
    "Dokumen ini milik usaha cocopeat. Bisa berupa BAP (Berita Acara Penerimaan/serah terima barang) "
    "ATAU PO (Purchase Order dari customer). Format PO BERBEDA-BEDA antar customer, jadi jangan "
    "mengandalkan tata letak -- pahami isinya.\n\n"
    "Tentukan jenisnya, lalu isi field yang relevan. Jawab HANYA JSON, tanpa teks lain:\n"
    "{\"jenis\":\"BAP atau PO atau LAIN\","
    "\"no_bap\":\"nomor BAP (kosongkan kalau PO)\","
    "\"tanggal\":\"DD Bulan YYYY contoh 15 Juni 2026 (kosongkan kalau PO)\","
    "\"site\":\"Senyiur atau Jembayan atau Suring atau Sebakis atau Sesayap atau MPS\","
    "\"qty_kg\":angka_berat_bersih_KG_untuk_BAP_atau_0,"
    "\"qty_m3\":angka_total_m3_untuk_BAP_atau_0,"
    "\"jumlah_sak\":angka_sak_untuk_BAP_atau_0,"
    "\"po_no\":\"nomor PO (kosongkan kalau BAP)\","
    "\"customer\":\"nama perusahaan pembeli/penerbit PO (kosongkan kalau BAP)\","
    "\"total_qty\":angka_total_kuantitas_PO_atau_0,"
    "\"harga\":angka_harga_per_satuan_PO_tanpa_titik_koma_atau_0,"
    "\"confidence\":\"high atau medium atau low\"}\n\n"
    "Aturan:\n"
    "- SITE pada PO Adindo DITENTUKAN OLEH KODE PLANT, bukan oleh alamat. PO dari "
    "PT Adindo Hutani Lestari memuat kolom 'PO No / Plant' dan 'Deliver to' berisi "
    "'AHL Nursery-XXX'. Petakan kode XXX itu: SSP = Sesayap. SBS = Sebakis. "
    "JANGAN menebak site dari alamat customer (Malinau/Kalimantan Utara) atau dari nama "
    "customer -- alamat kantornya SAMA untuk semua site, jadi alamat tidak memberi "
    "petunjuk apa pun. Perhatikan SSP dan SBS mirip: baca huruf per huruf. "
    "Kalau kode plant tidak dikenali, KOSONGKAN site dan set confidence low -- lebih baik "
    "bertanya daripada menebak salah.\n"
    "- BAP Senyiur memakai kolom Total (m3). BAP site lain memakai Berat Bersih (KG).\n"
    "- PENTING: BAP sering memuat DUA angka berat. Contoh: 'Jumlah Berdasarkan "
    "pengiriman = 19.104 Kg' dan 'Berat Bersih sesuai standar yang di terima = "
    "18.852 Kg' (selisihnya dipotong). Yang DITAGIHKAN adalah BERAT BERSIH SESUAI "
    "STANDAR YANG DITERIMA -- angka yang LEBIH KECIL. JANGAN pakai jumlah pengiriman "
    "dan JANGAN pakai hasil (jumlah bag x berat per bag). Kalau hanya ada satu angka "
    "berat, pakai angka itu.\n"
    "- PO Senyiur satuannya m3, PO site lain satuannya KG.\n"
    "- 'site' adalah lokasi/tujuan pengiriman, bukan alamat kantor customer.\n"
    "- PENTING soal 'customer': kita adalah PENJUAL. Badan usaha KITA adalah "
    "PT Deliandra Karya Pratama (DKP) dan CV Kreasi Karya Sukses (KKS) -- keduanya "
    "JANGAN PERNAH diisi sebagai customer. Customer = pihak PEMBELI yang MENERBITKAN "
    "PO ini kepada kami (contoh: PT Ichi Hutani Manunggal). Kalau nama pembeli tidak "
    "jelas, kosongkan customer dan set confidence low -- JANGAN menebak dengan nama kami.\n"
    "- Angka JANGAN pakai pemisah ribuan. Kalau ragu, isi 0 dan set confidence low.\n"
    "- Kalau dokumen jelas bukan BAP maupun PO, isi jenis = LAIN."
)


def terapkan_pt_site(ocr):
    """Koreksi 'site' dari nama PT/customer (lihat pt_site.py). Nama PT dibaca
    OCR andal; site sering ditebak salah. Status: 'autofill'|'kept'|'ask'."""
    site, status = pt_site.resolve_site(ocr.get("customer", ""), ocr.get("site", ""))
    if status == "autofill":
        ocr["site"] = site
    elif status == "ask":
        ocr["site"] = ""
    return status


def baca_dokumen(bagian):
    with open(ANTHROPIC_KEY_FILE) as f:
        key = f.read().strip()
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 700,
        "messages": [{"role": "user",
                      "content": bagian + [{"type": "text", "text": PROMPT}]}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body)
    req.add_header("x-api-key", key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")
    resp = json.loads(urllib.request.urlopen(req).read())
    teks = resp["content"][0]["text"].replace("```json", "").replace("```", "").strip()
    return json.loads(teks)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"jenis": "LAIN", "confidence": "low",
                          "reply": "Gagal: tidak ada file."}))
        sys.exit(1)

    file_id = sys.argv[1]
    caption = sys.argv[2] if len(sys.argv) > 2 else ""

    try:
        ocr = baca_dokumen(ambil_gambar(file_id))
    except Exception as e:
        print(json.dumps({"jenis": "LAIN", "confidence": "low",
                          "reply": f"Gagal membaca dokumen: {e}"}))
        return

    jenis = paksa_jenis(caption) or (ocr.get("jenis") or "LAIN").upper()
    ocr["jenis"] = jenis

    if jenis == "PO":
        # Serahkan sepenuhnya ke addpo.py (state machine + konfirmasi YA + insert DB).
        _status = terapkan_pt_site(ocr)
        hasil = json.loads(addpo.process(bangun_teks_addpo(ocr)))
        if _status == "ask":
            _pt = ocr.get("customer") or "PT ini"
            hasil["reply"] = ("Catatan: " + _pt + " belum terdaftar, site tidak "
                              "ditebak otomatis. Mohon pilih/ketik site di bawah." + chr(10) + chr(10) + hasil["reply"])
        ocr["reply"] = "Terbaca sebagai PURCHASE ORDER.\n\n" + hasil["reply"]
    elif jenis == "BAP":
        site_paksa = paksa_site(caption)   # caption mengalahkan tebakan AI
        if site_paksa:
            ocr["site"] = site_paksa
        simpan_state_bap(ocr)
        # Catat BAP ke app_bap_nota supaya Aturan Bisnis #9 (invoice hanya terbit
        # setelah BAP ada) juga berlaku untuk BAP yang masuk lewat Telegram.
        # Sengaja gagal-aman: kegagalan di sini TIDAK boleh mengganggu balasan bot.
        try:
            _dir_webapp = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "webapp")
            if _dir_webapp not in sys.path:
                sys.path.insert(0, _dir_webapp)
            import bap_arsip
            if _BERKAS_TERAKHIR["data"]:
                bap_arsip.daftarkan_dari_telegram(
                    _BERKAS_TERAKHIR["nama"] or "telegram.jpg",
                    _BERKAS_TERAKHIR["data"], ocr)
        except Exception as _e:
            print(f"  [ocr_doc] PERINGATAN: arsip BAP dilewati: {_e}", file=sys.stderr)
        ocr["reply"] = pesan_bap(ocr)
    else:
        ocr["reply"] = ("Dokumen tidak dikenali sebagai BAP maupun PO.\n\n"
                        "Tidak ada yang disimpan. Kirim ulang dengan caption "
                        "'/addpo' (untuk PO) atau 'BAP' (untuk BAP).")

    print(json.dumps(ocr, ensure_ascii=False))


def selftest():
    """Uji fungsi murni saja -- tanpa jaringan, tanpa database, tanpa menyentuh state."""
    lulus, gagal = [], []

    def cek(nama, kondisi, detail=""):
        (lulus if kondisi else gagal).append(nama)
        print(f"  {'PASS' if kondisi else 'FAIL'}: {nama}{'' if kondisi else '  -- ' + detail}")

    print("[Skenario G] Caption memaksa jenis dokumen")
    cek("G: caption '/addpo' -> PO", paksa_jenis("/addpo") == "PO")
    cek("G: caption 'bap juni' -> BAP", paksa_jenis("bap juni") == "BAP")
    cek("G: caption kosong -> tidak memaksa", paksa_jenis("") is None)
    print("\n[Skenario M] Caption memaksa site (BAP), mengalahkan tebakan AI")
    cek("M: 'BAP Jembayan' -> Jembayan", paksa_site("BAP Jembayan") == "Jembayan")
    cek("M: 'bap suring juni' -> Suring", paksa_site("bap suring juni") == "Suring")
    cek("M: 'laporan mps' -> MPS", paksa_site("laporan mps") == "MPS")
    cek("M: tanpa site -> None", paksa_site("BAP juni") is None)
    cek("M: kosong -> None", paksa_site("") is None)

    print("\n[Skenario H] OCR PO -> teks berlabel yang dimengerti addpo.parse_labeled()")
    ocr = {"po_no": "4500270001", "site": "Jembayan",
           "customer": "PT Ichi Hutani Manunggal", "total_qty": 140000, "harga": 3200}
    teks = bangun_teks_addpo(ocr)
    d = addpo.parse_labeled(teks)
    cek("H: po_no terbaca", d.get("po_no") == "4500270001", str(d))
    cek("H: site terbaca", d.get("site") == "Jembayan", str(d))
    cek("H: customer terbaca", d.get("customer") == "PT Ichi Hutani Manunggal", str(d))
    cek("H: total_qty terbaca", d.get("total_qty") == 140000, str(d))
    cek("H: harga terbaca", d.get("harga") == 3200, str(d))
    cek("H: tidak ada field yang kurang", addpo.missing_fields(d) == [], str(addpo.missing_fields(d)))

    print("\n[Skenario I] OCR PO Senyiur (m3, desimal) -> KKS")
    ocr2 = {"po_no": "14-0001-99999", "site": "Senyiur",
            "customer": "PT Contoh", "total_qty": 730.5, "harga": 758700}
    d2 = addpo.parse_labeled(bangun_teks_addpo(ocr2))
    cek("I: site Senyiur dikenali", d2.get("site") == "Senyiur", str(d2))
    cek("I: qty desimal utuh", d2.get("total_qty") == 730.5, str(d2))
    cek("I: Senyiur -> badan usaha KKS (5)", addpo.SITE_INFO["Senyiur"][0] == 5)

    print("\n[Skenario J] OCR PO tidak lengkap -> addpo menanyakan field yang kurang")
    d3 = addpo.parse_labeled(bangun_teks_addpo({"po_no": "123", "site": "Suring"}))
    kurang = addpo.missing_fields(d3)
    cek("J: field kosong tidak ditulis", "total_qty" not in d3 and "harga" not in d3, str(d3))
    cek("J: yang kurang terdeteksi", set(kurang) == {"customer", "total_qty", "harga"}, str(kurang))

    print("\n[Skenario K] Pesan BAP jujur saat tidak terbaca")
    p_kosong = pesan_bap({"no_bap": "", "site": "", "qty_kg": 0, "qty_m3": 0})
    cek("K: BAP kosong -> larang SELESAI", "JANGAN ketik SELESAI" in p_kosong)
    p_isi = pesan_bap({"no_bap": "B1", "tanggal": "1 Juli 2026", "site": "Senyiur",
                       "qty_kg": 0, "qty_m3": 50})
    cek("K: BAP lengkap -> tawarkan SELESAI", "Ketik SELESAI" in p_isi)
    cek("K: qty m3 dipakai untuk Senyiur", "50.00 m3" in p_isi, p_isi)

    print("\n" + "=" * 60)
    print("[Skenario L] Site ditentukan dari nama PT, bukan tebakan OCR")
    oL = {"po_no": "PO-12-00009675", "customer": "PT Mahakam Persada Sakti", "site": "Senyiur", "total_qty": 1114, "harga": 812600}
    stL = terapkan_pt_site(oL)
    cek("L: Mahakam -> site dikoreksi ke MPS", oL["site"] == "MPS" and stL == "autofill", str(oL["site"]) + "/" + stL)
    oL2 = {"po_no": "X", "customer": "PT Belum Terdaftar", "site": "Senyiur", "total_qty": 100, "harga": 5}
    stL2 = terapkan_pt_site(oL2)
    cek("L: PT asing -> site dikosongkan", oL2["site"] == "" and stL2 == "ask", str(oL2["site"]) + "/" + stL2)
    dL = addpo.parse_labeled(bangun_teks_addpo(oL2))
    cek("L: PT asing -> addpo minta site", "site" in addpo.missing_fields(dL), str(addpo.missing_fields(dL)))
    oL3 = {"po_no": "Y", "customer": "PT Itci Hutani Manunggal", "site": "Jembayan", "total_qty": 100, "harga": 5}
    stL3 = terapkan_pt_site(oL3)
    cek("L: PT multi-site -> tebakan valid dipertahankan", oL3["site"] == "Jembayan" and stL3 == "kept", str(oL3["site"]) + "/" + stL3)

    print(f"HASIL SELFTEST ocr_doc: {len(lulus)} PASS, {len(gagal)} FAIL")
    if gagal:
        print("ADA YANG GAGAL: " + ", ".join(gagal))
        sys.exit(1)
    print("SEMUA SKENARIO LOLOS.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        selftest()
    else:
        main()
