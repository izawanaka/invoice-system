"""
validation.py -- Lapisan validasi TAMBAHAN (Fase 1 cross-check) di ATAS skrip
kalkulasi yang sudah teruji (bap_to_invoice.py, bap_to_invoice_kks.py,
invoice_dkp.py, invoice_kks.py, code_pajak.py).

ATURAN: modul ini TIDAK PERNAH menghitung ulang invoice/pajak yang sesungguhnya
-- ia hanya membandingkan angka yang SUDAH dihasilkan pihak lain (input
pengguna, atau keluaran subprocess bap_to_invoice*.py) dengan hitungan
qty x harga, lalu melaporkan selisihnya dalam Bahasa Indonesia. Dipakai oleh
routers/po.py, routers/bap.py, routers/invoices.py.
"""
from typing import Iterable, Tuple


def check_calc_consistency(
    qty: float, harga_satuan: float, total: float, tolerance_rupiah: float = 10,
) -> Tuple[bool, float, float, str]:
    """Bandingkan qty x harga_satuan dengan `total` yang tertulis/tersimpan.

    tolerance_rupiah: selisih dalam Rupiah yang masih dianggap wajar (mis.
    pembulatan pecahan). Toleransi efektif yang dipakai = MAKS(tolerance_rupiah,
    0.5% dari nilai expected) -- supaya nilai besar (ratusan juta) tidak
    terlalu ketat ditolak hanya karena pembulatan desimal kecil, tapi nilai
    kecil tetap diawasi ketat oleh angka Rupiah mutlaknya.

    Mengembalikan tuple (ok, expected, diff, pesan_indonesia).
    """
    expected = float(qty) * float(harga_satuan)
    total = float(total)
    diff = abs(expected - total)
    tol = max(float(tolerance_rupiah), abs(expected) * 0.005)
    ok = diff <= tol
    pesan = (
        f"Selisih hitungan: qty x harga = Rp {expected:,.0f}, tetapi total tertulis "
        f"Rp {total:,.0f} (selisih Rp {diff:,.0f})"
    ).replace(",", ".")
    return ok, expected, diff, pesan


def check_items_total_consistency(
    items: Iterable[Tuple[float, float]], total: float, tolerance_rupiah: float = 10,
) -> Tuple[bool, float, float, str]:
    """Sama seperti check_calc_consistency, tapi `items` adalah daftar
    (qty, harga_satuan) per baris -- dipakai utk cross-check total gabungan
    (mis. sub_total invoice) terhadap jumlah tiap baris item."""
    expected_total = sum(float(q) * float(h) for q, h in items)
    return check_calc_consistency(1.0, expected_total, total, tolerance_rupiah)
