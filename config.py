"""config.py -- SATU-SATUNYA tempat path & lingkungan ditentukan.

Kenapa ada file ini (14 Juli 2026):
Semua path dulu di-HARDCODE di tiap script (/home/izawa/invoice-system/..., mount CIFS,
nama database). Akibatnya tidak ada cara menguji perubahan tanpa menyentuh produksi --
setiap percobaan langsung mengenai invoice, saldo PO, dan Excel yang asli. Itulah kenapa
hari ini berkali-kali harus koreksi & hapus data di produksi.

Sekarang: KODE SAMA PERSIS di sandbox dan produksi. Yang membedakan hanya ENV VAR.
Deploy = git merge, BUKAN mengedit path (mengedit path saat deploy = sumber bug baru).

  INVOICE_ENV   : 'produksi' (default) | 'sandbox'   -- label saja, untuk pesan/log
  INVOICE_DATA  : folder file runtime (po_tracker, counter, state, Excel).
                  Default = folder kode ini  -> perilaku produksi TIDAK berubah.
  INVOICE_OUT   : folder PDF DKP.  Default = mount CIFS ke PC (seperti sekarang).
  INVOICE_OUT_KKS: folder PDF KKS. Default = mount CIFS ke PC.
  INVOICE_DB    : nama database.   Default = bisnis_izawa (produksi).
  INVOICE_SMB   : 1 = salin Excel ke share PC (produksi). 0 = jangan (sandbox).
"""
import os

ENV  = os.environ.get("INVOICE_ENV", "produksi")
BASE = os.path.dirname(os.path.abspath(__file__))          # folder KODE
DATA = os.environ.get("INVOICE_DATA", BASE)                 # folder DATA runtime

_PC = "/mnt/media/D/SynologyDrive/PT/PT. Deliandra Karya Pratama"
OUTPUT_DIR_DKP = os.environ.get("INVOICE_OUT",     f"{_PC}/Inv-AI")
OUTPUT_DIR_KKS = os.environ.get("INVOICE_OUT_KKS", f"{_PC}/Inv-AI-KKS")
SMB_DKP        = f"{_PC}/PO_Tracker_DKP.xlsx"
SMB_KKS        = f"{_PC}/Inv-AI-KKS/PO_Tracker_KKS.xlsx"
SMB_AKTIF      = os.environ.get("INVOICE_SMB", "1") == "1"

DB_NAME = os.environ.get("INVOICE_DB", "")   # kosong = pakai isi file kredensial


def d(nama):
    """Path file runtime (data)."""
    return os.path.join(DATA, nama)


def k(nama):
    """Path file kode."""
    return os.path.join(BASE, nama)


# --- file runtime ---
PO_FILE          = d("po_tracker.json")
PO_FILE_KKS      = d("po_tracker_kks.json")
INV_NO_FILE      = d("last_invoice_no.txt")
INV_NO_FILE_KKS  = d("last_invoice_no_kks.txt")
ADDPO_STATE      = d("addpo_state.json")
ADDPO_INPUT      = d("addpo_input.txt")
BAP_STATE        = d("multi_bap_state.json")
BAP_INPUT        = d("bap_input.json")
BAP_INPUT_KKS    = d("bap_input_kks.json")
EXCEL_DKP        = d("PO_Tracker_DKP.xlsx")
EXCEL_KKS        = d("PO_Tracker_KKS.xlsx")
CRED_FILE        = d(".bisnis_db_credentials")
ANTHROPIC_KEY    = d("anthropic_key.txt")
TG_TOKEN_FILE    = d("telegram_token.txt")

# --- file kode ---
INVOICE_DKP = k("invoice_dkp.py")
INVOICE_KKS = k("invoice_kks.py")


def tg_token():
    """Token bot Telegram dibaca dari file (TIDAK di-hardcode, TIDAK masuk git -- I6).
    Sandbox memakai bot berbeda, jadi tokennya WAJIB datang dari lingkungan, bukan kode."""
    with open(TG_TOKEN_FILE) as f:
        return f.read().strip()


def ringkas():
    return (f"ENV={ENV} DATA={DATA} DB={DB_NAME or '(dari file kredensial)'} "
            f"OUT={OUTPUT_DIR_DKP} SMB={'ya' if SMB_AKTIF else 'TIDAK'}")
