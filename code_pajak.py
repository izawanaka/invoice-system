# code_pajak.py
# Modul perhitungan pajak (PPN 12% skema DPP Nilai Lain, PMK 131/2024)
# Aturan Vault #6: SEMUA pembulatan pajak WAJIB ROUND_HALF_UP mengikuti Faktur Pajak/Coretax.
from decimal import Decimal, ROUND_HALF_UP


def round_half_up(nilai) -> int:
    return int(Decimal(str(nilai)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def dpp_nilai_lain(dpp) -> int:
    raw = Decimal(str(dpp)) * Decimal(11) / Decimal(12)
    return round_half_up(raw)


def ppn(dpp_nl) -> int:
    raw = Decimal(str(dpp_nl)) * Decimal(12) / Decimal(100)
    return round_half_up(raw)


def hitung_pajak(dpp) -> dict:
    dpp_i  = round_half_up(dpp)
    dpp_nl = dpp_nilai_lain(dpp_i)
    ppn_i  = ppn(dpp_nl)
    return {"dpp": dpp_i, "dpp_nilai_lain": dpp_nl, "ppn": ppn_i, "grand_total": dpp_i + ppn_i}


if __name__ == "__main__":
    hasil = hitung_pajak(124560450)
    assert hasil["dpp_nilai_lain"] == 114180413, hasil
    assert hasil["ppn"] == 13701650, hasil
    print("Inv 091:", hasil)
    print("Semua assertion PASS - cocok dengan Faktur Pajak.")
