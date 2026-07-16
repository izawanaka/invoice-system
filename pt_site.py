#!/usr/bin/env python3
"""
pt_site.py -- Pemetaan nama Customer/PT -> Site.

Kenapa ada (15 Juli 2026): OCR PO membaca NAMA PT dengan andal, tapi SITE sering
ditebak salah (mis. PO PT Mahakam Persada Sakti kebaca 'Senyiur' karena dokumen
tidak memuat kata 'MPS'). Nama PT = sinyal andal, jadi site ditentukan dari PT.

Aturan:
  - PT dikenal & 1 site  -> site OTOMATIS diisi (mengalahkan tebakan OCR).
  - PT dikenal & >1 site -> tebakan OCR dipertahankan bila termasuk daftar site PT
                            itu; kalau tidak, dikosongkan supaya bot bertanya.
  - PT TIDAK dikenal      -> site dikosongkan; bot WAJIB bertanya. Setelah PO
                            tersimpan, pemetaan PT->site diingat permanen (remember()).

SEED = pengetahuan awal (dalam kode, ikut git, bisa diuji). File overlay
pt_site_map.json = memori runtime yang tumbuh sendiri tiap PO baru tersimpan.
"""
import json, os, config

MAP_FILE = config.d("pt_site_map.json")

# Diturunkan dari purchase_orders di bisnis-db (15 Juli 2026).
SEED = {
    "pt mahakam persada sakti": ["MPS"],
    "pt permata borneo abadi": ["Senyiur"],
    "pt itci hutani manunggal": ["Jembayan", "Suring"],
    "pt ichi hutani manunggal": ["Jembayan", "Suring"],
    "pt adindo hutani lestari": ["Sebakis", "Sesayap"],
}


def norm_pt(name):
    """Samakan bentuk nama PT: huruf kecil, buang titik/koma, rapatkan spasi."""
    if not name:
        return ""
    s = str(name).lower()
    for ch in ".,":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def _load_overlay():
    try:
        with open(MAP_FILE) as f:
            d = json.load(f)
        return {norm_pt(k): v for k, v in d.items()} if isinstance(d, dict) else {}
    except Exception:
        return {}


def _merged():
    m = {k: list(v) for k, v in SEED.items()}
    for k, v in _load_overlay().items():
        cur = m.get(k, [])
        for s in (v if isinstance(v, list) else [v]):
            if s and s not in cur:
                cur.append(s)
        m[k] = cur
    return m


def sites_for(customer):
    return _merged().get(norm_pt(customer), [])


def resolve_site(customer, guess):
    """Kembalikan (site, status). status: 'autofill' | 'kept' | 'ask'."""
    sites = sites_for(customer)
    if len(sites) == 1:
        return sites[0], "autofill"
    if len(sites) > 1:
        if guess and guess in sites:
            return guess, "kept"
        return "", "ask"
    return "", "ask"


def remember(customer, site):
    """Simpan PT->site ke overlay permanen. Aman dipanggil berkali-kali."""
    key = norm_pt(customer)
    if not key or not site:
        return
    overlay = _load_overlay()
    cur = overlay.get(key, [])
    if not isinstance(cur, list):
        cur = [cur]
    if site not in cur:
        cur.append(site)
    overlay[key] = cur
    tmp = MAP_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(overlay, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MAP_FILE)
