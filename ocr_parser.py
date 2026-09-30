"""ocr_parser.py -- mengubah keluaran mesin OCR (baris teks + kotak) menjadi field dokumen
BAP / PO dengan ATURAN PER TEMPLATE (Aturan Bisnis #21, 30 Sep 2026).

Masukan : daftar baris {"teks","skor","kotak":[[x,y],...]} dari ocr-paddle.
Keluaran: dict berbentuk PERSIS seperti hasil OCR lama (ocr_doc.PROMPT), sehingga web,
          bot Telegram, bap_arsip, penanda BAP kembar, dan wizard tidak berubah.

Prinsip: TIDAK MENEBAK. Yang tidak cocok pola -> kosong + confidence 'low'.
Hanya BAP yang lolos pengecekan silang angka yang boleh 'high'.
Kode ini sengaja ditulis lugas supaya bisa diperiksa tanpa latar belakang pemrograman.
"""
import re

SITES = ["Suring", "Jembayan", "Sebakis", "Sesayap", "Senyiur", "MPS"]
KODE_PLANT = {"SSP": "Sesayap", "SBS": "Sebakis"}          # PO/BAP Adindo
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
         "September", "Oktober", "November", "Desember"]
ROMAWI = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
          "IX": 9, "X": 10, "XI": 11, "XII": 12}

# ------------------------------------------------------------------ alat bantu

def angka(s):
    """Baca angka gaya Indonesia/Inggris: '5.940'->5940, '43,512'->43512, '5,393.40'->5393.4,
    '5.382,61'->5382.61, '8,00'->8.0, '0.120'->0.12, '(6.727)'->6727. Tidak yakin -> None."""
    if s is None:
        return None
    t = re.sub(r"[^\d.,]", "", str(s))
    if not t or not re.search(r"\d", t):
        return None
    if "." in t and "," in t:
        desimal = "." if t.rfind(".") > t.rfind(",") else ","
        t = t.replace("," if desimal == "." else ".", "").replace(desimal, ".")
        return float(t)
    sep = "." if "." in t else ("," if "," in t else None)
    if sep is None:
        return float(t)
    bagian = t.split(sep)
    if len(bagian) > 2:                                  # 1.234.567
        return float("".join(bagian))
    kepala, ekor = bagian
    if kepala in ("", "0") or len(ekor) != 3:            # 0.120 / 8,00 / 5382.61
        return float(kepala or "0") + float("0." + ekor) if ekor else float(kepala or "0")
    return float(kepala + ekor)                           # 5.940 / 43,512


def _y(b):  return min(p[1] for p in b["kotak"])
def _x(b):  return min(p[0] for p in b["kotak"])
def _tinggi(b): return max(p[1] for p in b["kotak"]) - _y(b)


def susun_baris(baris):
    """Kelompokkan kotak yang sejajar vertikal menjadi satu 'baris dokumen', urut kiri-kanan.
    Toleransi = 60% tinggi huruf tipikal, jadi ikut skala foto."""
    if not baris:
        return []
    tinggi = sorted(_tinggi(b) for b in baris)
    tol = max(6, int(tinggi[len(tinggi) // 2] * 0.6))
    urut = sorted(baris, key=_y)
    hasil, grup = [], [urut[0]]
    for b in urut[1:]:
        if abs(_y(b) - _y(grup[-1])) <= tol:
            grup.append(b)
        else:
            hasil.append(grup); grup = [b]
    hasil.append(grup)
    out = []
    for g in hasil:
        g = sorted(g, key=_x)
        out.append({"teks": " ".join(x["teks"] for x in g), "skor": min(x["skor"] for x in g),
                    "y": _y(g[0]), "kotak": g})
    return out


def rapikan(t):
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(?i)di\s+terima", "diterima", t)
    return t.strip()


def _cari(pola, teks, flags=re.I):
    m = re.search(pola, teks, flags)
    return m.group(1) if m else None


def tanggal_dari(teks):
    """'(26-09-2026)' atau '25 Juli 2026' -> '26 September 2026' (format lama)."""
    m = re.search(r"\(?\s*(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(20\d{2})\s*\)?", teks)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1)):02d} {BULAN[int(m.group(2)) - 1]} {m.group(3)}"
    m = re.search(r"(\d{1,2})\s+(" + "|".join(BULAN) + r")\s+(20\d{2})", teks, re.I)
    if m:
        return f"{int(m.group(1)):02d} {m.group(2).title()} {m.group(3)}"
    return ""


def plat_nomor(teks):
    """Cari plat kendaraan 'KT 8807 CK', 'DP 8639 HE', 'KT.0948CN' -> daftar unik urut."""
    hasil = []
    for m in re.finditer(r"\b([A-Z]{1,2})[\s.]?(\d{3,4})[\s.]?([A-Z]{1,3})\b", teks):
        p = f"{m.group(1)} {m.group(2)} {m.group(3)}"
        if p not in hasil and not re.match(r"(RT|RW|NO|PT|CV)\b", m.group(1)):
            hasil.append(p)
    return hasil


def kosong(jenis="LAIN", confidence="low", **isi):
    d = {"jenis": jenis, "no_bap": "", "tanggal": "", "site": "", "qty_kg": 0, "qty_m3": 0,
         "jumlah_sak": 0, "nopol": "", "po_no": "", "customer": "", "total_qty": 0, "harga": 0,
         "confidence": confidence, "template": "", "catatan": ""}
    d.update(isi)
    return d

# ------------------------------------------------------------------ pengenal template

def kenali(teks):
    t = teks.upper()
    if "PURCHASE ORDER" in t or ("PO NO" in t and "PLANT" in t):
        return "po_sap"                                   # Itci & Adindo memakai format SAP yang sama
    if "BERITA ACARA" in t:
        if "ADINDO" in t:
            return "bap_adindo"
        if "ITCI" in t or "ICHI" in t or "HUTANI MANUNGGAL" in t:
            return "bap_itci"
        if "MAHAKAM" in t or "MPS" in t or "M3" in t or "KEMASAN" in t or "KARYA SUKSES" in t:
            return "bap_kks"
    return ""

# ------------------------------------------------------------------ BAP kg (Itci & Adindo)

def _no_bap(rows):
    for r in rows:
        m = re.search(r"NO\s*[:.]?\s*(\d{3}\s*/\s*(?:[0-9A-Z\-]+\s*/\s*){1,3}20\d{2})", r["teks"], re.I)
        if m:
            return re.sub(r"\s+", "", m.group(1)).upper()
    return ""


def _angka_berlabel(rows, label):
    """Nilai kg di baris yang memuat label. Nilai boleh dipisah '=' dan boleh '(6.727)'."""
    for r in rows:
        t = rapikan(r["teks"])
        if re.search(label, t, re.I):
            m = re.search(label + r".*?[=:]?\s*\(?\s*([\d][\d.,]*)\s*\)?\s*K[Gg]", t, re.I)
            if m:
                return angka(m.group(1))
    return None


def _baris_total(rows):
    for r in rows:
        if re.match(r"\s*TOTAL\b", r["teks"], re.I):
            t = re.sub(r"(?i)total\s*=\s*[\d.,]+\s*kg", "", r["teks"])   # buang 'Total = 19,104 Kg'
            t = re.sub(r"@\s*[\d.,]+\s*kg\s*=\s*[\d.,]+\s*kg", "", t, flags=re.I)  # buang '@33kg=5.940kg'
            return [angka(x) for x in re.findall(r"\d[\d.,]*", t)]
    return []


def _berat_per_sak(rows):
    for r in rows:
        m = re.search(r"@\s*([\d.,]+)\s*kg", r["teks"], re.I) or \
            re.search(r"Berat Per Karung\s*=?\s*([\d.,]+)\s*kg", r["teks"], re.I)
        if m:
            return angka(m.group(1))
    return None


def baca_bap_kg(rows, template):
    teks = " ".join(r["teks"] for r in rows)
    d = kosong("BAP", "medium", template=template)
    d["customer"] = "PT Adindo Hutani Lestari" if template == "bap_adindo" else "PT Itci Hutani Manunggal"
    d["no_bap"] = _no_bap(rows)
    d["tanggal"] = tanggal_dari(teks)
    catatan = []

    # nomor BAP wajib cocok pola template -- ini yang menolak 'NSR-085' dan sejenisnya
    if template == "bap_itci":
        ok_no = re.fullmatch(r"\d{3}/\d{4}/20\d{2}", d["no_bap"] or "")
    else:
        m = re.fullmatch(r"\d{3}/NS[RY][-/](SBS|SSP)/([0-9]{1,2}|[IVX]+)/20\d{2}", d["no_bap"] or "")
        ok_no = m
        if m:
            d["site"] = KODE_PLANT[m.group(1)]
    if not ok_no:
        catatan.append(f"nomor BAP tidak cocok pola: '{d['no_bap']}'")
        d["no_bap"] = ""

    bersih = _angka_berlabel(rows, r"berat\s*bersih")
    kirim = _angka_berlabel(rows, r"jumlah\s*berdasarkan\s*pengiriman") or _angka_berlabel(rows, r"\bTotal\s*=")
    selisih = _angka_berlabel(rows, r"\bselisih")
    total = _baris_total(rows)
    per_sak = _berat_per_sak(rows)
    sak = next((int(x) for x in total if x and x >= 100 and float(x).is_integer()), 0)
    if template == "bap_adindo" and len([x for x in total if x and x >= 100]) >= 2:
        sak = int([x for x in total if x and x >= 100][-1])       # kolom 'Qty yang diterima' (paling kanan)
    d["jumlah_sak"] = sak
    d["nopol"] = ", ".join(plat_nomor(" ".join(r["teks"] for r in rows if not re.match(r"\s*TOTAL", r["teks"], re.I))))

    if bersih is None:
        catatan.append("berat bersih tidak ditemukan")
        d["confidence"] = "low"
    else:
        d["qty_kg"] = bersih
        # pengecekan silang: hanya kalau angka-angka saling mengunci -> high
        cocok = False
        if kirim and selisih is not None and abs((kirim - selisih) - bersih) < 1:
            cocok = True
        if sak and per_sak and (abs(sak * per_sak - bersih) < 1 or (kirim and abs(sak * per_sak - kirim) < 1)):
            cocok = True
        if kirim and sak and per_sak and abs(sak * per_sak - kirim) >= 1 and abs(sak * per_sak - bersih) >= 1:
            catatan.append(f"sak x berat/sak ({sak}x{per_sak}) tidak sama dengan pengiriman {kirim}")
            d["confidence"] = "low"
        elif cocok and d["no_bap"]:
            d["confidence"] = "high"
    if template == "bap_itci":
        d["site"] = ""            # Itci punya banyak site; pt_site/pengguna yang menentukan (aturan lama)
    d["catatan"] = "; ".join(catatan)
    return d

# ------------------------------------------------------------------ BAP m3 (KKS: Senyiur, MPS)

def baca_bap_kks(rows):
    """BAP satuan m3 (CV KKS): Senyiur ('Berat/Karung 8,00' = karung per m3, ada baris Total)
    dan MPS ('Karung/m3 0.125' = m3 per karung, satu baris tanpa Total).
    Pengecekan silang: karung x rasio (atau karung / rasio) harus = m3 di baris itu."""
    teks = " ".join(r["teks"] for r in rows)
    d = kosong("BAP", "medium", template="bap_kks")
    d["tanggal"] = tanggal_dari(teks)
    for s in SITES:
        if re.search(r"\b" + s + r"\b", teks, re.I):
            d["site"] = s
    if "MAHAKAM" in teks.upper():
        d["customer"] = "PT Mahakam Persada Sakti"; d["site"] = d["site"] or "MPS"
    total_karung, total_m3, cocok, baris_data = 0, 0.0, 0, 0
    for r in rows:
        if re.search(r"(?i)karung/m3|berat/karung|jenis|kendaraan", r["teks"]):
            continue                                   # baris judul kolom
        bersih = re.sub(r"\d{2}-\d{4,}", " ", r["teks"])                       # buang nomor PO '12-9675'
        bersih = re.sub(r"\b[A-Z]{1,2}[\s.]?\d{3,4}[\s.]?[A-Z]{1,3}\b", " ", bersih)
        token = re.findall(r"\d[\d.,]*", bersih)
        nums = [angka(x) for x in token]
        nums = [n for n in nums if n is not None]
        karung = next((n for n in nums if n >= 100 and float(n).is_integer()), None)
        # rasio ('0.125' atau '8,00') selalu ditulis dengan pemisah desimal -- nomor urut baris tidak
        rasio = next((angka(x) for x in token if re.search(r"[.,]", x) and angka(x) is not None and 0 < angka(x) <= 20), None)
        if re.search(r"(?i)\bTOTAL\b", r["teks"]) and karung is not None:      # baris Total: karung + m3
            karung = max(n for n in nums if n >= 100 and float(n).is_integer())  # total karung = yang terbesar
            calon = [n for n in nums if n != karung and 20 < n < karung and n != rasio]
            desimal = [n for n in calon if not float(n).is_integer()]         # m3 hampir selalu berdesimal
            if calon:
                total_karung, total_m3 = karung, max(desimal or calon)
            continue
        if karung is None or rasio is None:
            continue
        harapan = karung * rasio if rasio < 1 else karung / rasio
        m3 = next((n for n in nums if n not in (karung, rasio) and abs(n - harapan) <= max(0.02 * harapan, 0.5)), None)
        if m3 is None:
            continue
        baris_data += 1; cocok += 1
        if not total_karung:
            d["jumlah_sak"] += int(karung); d["qty_m3"] = round(d["qty_m3"] + m3, 2)
    if total_karung:
        d["jumlah_sak"], d["qty_m3"] = int(total_karung), total_m3
    if not d["qty_m3"]:
        d["confidence"] = "low"; d["catatan"] = "baris karung x rasio = m3 tidak ditemukan"
    elif cocok == baris_data and baris_data > 0:
        d["confidence"] = "high"
    d["nopol"] = ", ".join(plat_nomor(teks))
    return d

# ------------------------------------------------------------------ PO format SAP (Itci & Adindo)

def baca_po(rows):
    teks = " ".join(r["teks"] for r in rows)
    d = kosong("PO", "medium", template="po_sap")
    d["po_no"] = _cari(r"\b(45\d{8})\b", teks) or ""
    plant = _cari(r"Nursery\s*-\s*([A-Za-z]+)", teks) or ""
    d["site"] = KODE_PLANT.get(plant.upper()) or next((s for s in SITES if s.lower() == plant.lower()), "")
    up = teks.upper()
    d["customer"] = ("PT Adindo Hutani Lestari" if "ADINDO" in up else
                     "PT Itci Hutani Manunggal" if ("ITCI" in up or "ICHI" in up or "IHM" in up) else "")
    tgl = _cari(r"PO Date\s*:?\s*(\d{2})\.(\d{2})\.(20\d{2})", teks)
    m = re.search(r"PO Date\s*:?\s*(\d{2})\.(\d{2})\.(20\d{2})", teks, re.I)
    d["tanggal_iso"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
    catatan = []
    # baris item: memuat '<qty> KG', harga, amount
    item = next((r for r in rows if re.search(r"[\d.,]+\s*KG\b", r["teks"], re.I)), None)
    qty = harga = amount = None
    if item:
        qty = angka(_cari(r"([\d][\d.,]*)\s*KG\b", item["teks"]))
        # kolom Unit Price & Amount selalu berformat '4,400.00' (dua desimal) -- kode material tidak
        # (tanggal '31.12.2026' dikecualikan: diikuti '.', dan nilainya < 100)
        uang = sorted(n for n in (angka(x) for x in re.findall(r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b(?!\.)", item["teks"])) if n and n >= 100)
        harga = uang[0] if uang else None
        amount = uang[-1] if len(uang) >= 2 else None
    grand = angka(_cari(r"Grand Total\s*([\d][\d.,]*)", teks))
    d["harga"] = harga or 0
    if amount and harga and abs(amount / harga - round(amount / harga)) < 0.01:
        d["total_qty"] = round(amount / harga)             # kuantitas dikunci oleh amount/harga
        if qty and abs(qty - d["total_qty"]) > 1:
            catatan.append(f"qty terbaca {qty} diganti {d['total_qty']} (amount/harga)")
        if d["po_no"] and d["customer"]:
            d["confidence"] = "high"
    elif qty:
        d["total_qty"] = qty; catatan.append("qty tidak bisa dicek silang dengan amount/harga")
    else:
        d["confidence"] = "low"; catatan.append("baris item tidak ditemukan")
    if not d["po_no"]:
        d["confidence"] = "low"; catatan.append("nomor PO tidak ditemukan")
    d["items"] = [{"nama_item": rapikan(_cari(r"(Peat[^0-9]*?MC)", teks) or "COCO PEAT"),
                   "kuantitas": d["total_qty"] or None, "harga_satuan": harga,
                   "subtotal": amount}] if item else []
    d["satuan"] = "kg"
    d["harga_satuan"] = harga
    d["total_nilai"] = grand
    d["site_tebakan"] = d["site"] or None
    d["catatan"] = "; ".join(catatan)
    d["catatan_keraguan"] = d["catatan"] or None
    return d

# ------------------------------------------------------------------ pintu masuk

def baca_halaman(baris):
    """Satu halaman (daftar kotak dari ocr-paddle) -> dict field."""
    rows = susun_baris(baris)
    teks = " ".join(r["teks"] for r in rows)
    template = kenali(teks)
    if template == "po_sap":
        d = baca_po(rows)
    elif template in ("bap_itci", "bap_adindo"):
        d = baca_bap_kg(rows, template)
    elif template == "bap_kks":
        d = baca_bap_kks(rows)
    else:
        d = kosong(catatan="template tidak dikenal")
    skor_rendah = [r for r in rows if r["skor"] < 0.6]
    if d["confidence"] == "high" and len(skor_rendah) > len(rows) * 0.3:
        d["confidence"] = "medium"; d["catatan"] = (d["catatan"] + "; banyak baris skor rendah").strip("; ")
    return d


def baca_dokumen(halaman):
    """Beberapa halaman (PDF) -> satu dict, atau daftar dict kalau nomor BAP berbeda-beda.
    Halaman yang bukan BAP/PO (lampiran QC, coretan) diabaikan."""
    hasil = [baca_halaman(h) for h in halaman]
    sah = [d for d in hasil if d["jenis"] != "LAIN"]
    if not sah:
        return hasil[0] if hasil else kosong()
    unik = []
    for d in sah:
        kunci = d["no_bap"] or d["po_no"]
        if not any((x["no_bap"] or x["po_no"]) == kunci for x in unik) or not kunci:
            unik.append(d)
    return unik[0] if len(unik) == 1 else unik
