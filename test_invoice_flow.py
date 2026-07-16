#!/usr/bin/env python3
"""
Test suite untuk transaksi invoice_dkp.py (generate PDF + update PO + catat invoice/BAP
di Postgres, satu transaksi atomik). Pakai PO & invoice DUMMY (prefix TEST-), TIDAK PERNAH
menyentuh data produksi asli.

Jalankan: python3 test_invoice_flow.py
Exit 0 kalau semua skenario lolos, exit 1 kalau ada yang gagal (dan detail dicetak).
"""
import json, os, re, shutil, subprocess, sys
import db_helper

# WAJIB folder sendiri -- kalau menunjuk produksi, test di sandbox justru
# menguji kode produksi dan sandbox jadi tidak ada gunanya.
BASE = os.path.dirname(os.path.abspath(__file__))
SRC_INVOICE_DKP = os.path.join(BASE, "invoice_dkp.py")
SRC_INVOICE_KKS = os.path.join(BASE, "invoice_kks.py")
TEST_DIR = "/tmp/test_invoice_flow"

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS: {name}")
    else:
        FAIL.append((name, detail))
        print(f"  FAIL: {name}  -- {detail}")


def make_test_script(dest, inv_no, inv_date, no_bap, site, no_po, customer, po_splits, items, output_dir, src_file=None):
    with open(src_file or SRC_INVOICE_DKP) as f:
        src = f.read()

    def replace_var(s, var, new_val):
        return re.sub(rf'^({var}\s*=\s*).*$', rf'\g<1>{new_val}', s, flags=re.MULTILINE)

    src = replace_var(src, 'INV_NO', f'"{inv_no}"')
    src = replace_var(src, 'INV_DATE', f'"{inv_date}"')
    src = replace_var(src, 'NO_BAP', f'"{no_bap}"')
    src = replace_var(src, 'SITE', f'"{site}"')
    src = replace_var(src, 'NO_PO', f'"{no_po}"')
    src = replace_var(src, 'CUSTOMER', f'"{customer}"')
    src = replace_var(src, 'OUTPUT_DIR', f'"{output_dir}"')
    splits_str = "[" + ", ".join(f'("{p}", {q})' for p, q in po_splits) + "]"
    src = replace_var(src, 'PO_SPLITS', splits_str)
    def _fmt_item(i):
        parts = [str(i[0]), f'"{i[1]}"', str(i[2]), str(i[3])]
        if len(i) > 4: parts.append(f'"{i[4]}"')
        if len(i) > 5: parts.append(f'"{i[5]}"')
        return "    (" + ", ".join(parts) + "),"
    items_str = "[\n" + "\n".join(_fmt_item(i) for i in items) + "\n]"
    src = re.sub(r'^ITEMS\s*=\s*\[.*?\]', f'ITEMS = {items_str}', src, flags=re.MULTILINE | re.DOTALL)
    # PO_FILE dialihkan ke file tracker dummy supaya tidak menimpa po_tracker.json asli
    src = replace_var(src, 'PO_FILE', f'"{TEST_DIR}/po_tracker_test.json"')
    src = replace_var(src, 'INV_NO_FILE', f'"{TEST_DIR}/last_invoice_no_test.txt"')

    with open(dest, "w") as f:
        f.write(src)


def run_script(path):
    # Script salinan dijalankan dari /tmp -- beri tahu di mana config.py & db_helper.py
    # berada, kalau tidak ia akan mencarinya di /tmp dan gagal impor.
    env = {**os.environ, "INVOICE_CODE": BASE}
    return subprocess.run(["python3", path], capture_output=True, text=True, cwd=BASE, env=env)


def db_get_po(cur, po_no, bu_id=4):
    cur.execute("SELECT total_qty, used_qty FROM purchase_orders WHERE po_no=%s AND badan_usaha_id=%s", (po_no, bu_id))
    return cur.fetchone()


def db_invoice_exists(cur, no_invoice):
    cur.execute("SELECT 1 FROM invoices WHERE no_invoice=%s", (no_invoice,))
    return cur.fetchone() is not None


def setup():
    os.makedirs(TEST_DIR, exist_ok=True)
    conn = db_helper.get_conn()
    cur = conn.cursor()
    for po_no, total in [("TEST-PO-DKP-1", 1000), ("TEST-PO-DKP-2", 1000)]:
        cur.execute(
            "INSERT INTO purchase_orders (badan_usaha_id, po_no, site, customer, total_qty, used_qty, satuan, harga_satuan, status) "
            "VALUES (4, %s, 'TestSite', 'Test Customer', %s, 0, 'kg', 1000, 'aktif') "
            "ON CONFLICT DO NOTHING", (po_no, total)
        )
    cur.execute(
        "INSERT INTO purchase_orders (badan_usaha_id, po_no, site, customer, total_qty, used_qty, satuan, harga_satuan, status) "
        "VALUES (5, 'TEST-PO-KKS-1', 'TestSenyiur', 'Test Customer KKS', 100, 0, 'm3', 500000, 'aktif') "
        "ON CONFLICT DO NOTHING"
    )
    conn.commit()
    cur.close(); conn.close()


def cleanup():
    conn = db_helper.get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM invoice_items WHERE invoice_id IN (SELECT id FROM invoices WHERE no_po LIKE 'TEST-PO-%%')")
    cur.execute("DELETE FROM invoices WHERE no_po LIKE 'TEST-PO-%%'")
    cur.execute("DELETE FROM bap WHERE no_bap LIKE 'TESTBAP%%'")
    cur.execute("DELETE FROM purchase_orders WHERE po_no LIKE 'TEST-PO-%%'")
    conn.commit()
    cur.close(); conn.close()
    shutil.rmtree(TEST_DIR, ignore_errors=True)


def scenario_a_sukses_normal():
    print("\n[Skenario A] Generate sukses normal, 1 PO")
    out_dir = f"{TEST_DIR}/output_ok"
    script = f"{TEST_DIR}/run_a.py"
    make_test_script(script, "901/VII/TestSite/2026", "13 Juli 2026", "TESTBAP-001",
                      "TestSite", "TEST-PO-DKP-1", "Test Customer",
                      [("TEST-PO-DKP-1", 500)], [(1, "Cocopeat", 500, 1000)], out_dir)
    r = run_script(script)
    check("A: script exit 0", r.returncode == 0, r.stderr[-300:])
    check("A: PDF fisik dibuat", os.path.exists(f"{out_dir}/Inv_901_VII_TestSite_2026.pdf"))

    conn = db_helper.get_conn(); cur = conn.cursor()
    row = db_get_po(cur, "TEST-PO-DKP-1")
    check("A: saldo PO-1 bertambah 500", row is not None and float(row[1]) == 500, str(row))
    check("A: invoice tercatat di Postgres", db_invoice_exists(cur, "901/VII/TestSite/2026"))
    cur.close(); conn.close()


def scenario_b_pdf_gagal_rollback():
    print("\n[Skenario B] PDF gagal ditulis -> HARUS rollback total")
    # Bikin OUTPUT_DIR yang pasti gagal: buat sebagai FILE biasa, bukan folder,
    # supaya os.makedirs(OUTPUT_DIR/..., exist_ok=True) meledak (NotADirectoryError)
    blocked = f"{TEST_DIR}/blocked_file"
    with open(blocked, "w") as f:
        f.write("ini file biasa, bukan folder")
    out_dir = f"{blocked}/subfolder"  # gagal karena parent-nya file, bukan direktori

    conn = db_helper.get_conn(); cur = conn.cursor()
    before = db_get_po(cur, "TEST-PO-DKP-1")
    cur.close(); conn.close()

    script = f"{TEST_DIR}/run_b.py"
    make_test_script(script, "902/VII/TestSite/2026", "13 Juli 2026", "TESTBAP-002",
                      "TestSite", "TEST-PO-DKP-1", "Test Customer",
                      [("TEST-PO-DKP-1", 300)], [(1, "Cocopeat", 300, 1000)], out_dir)
    r = run_script(script)
    check("B: script exit BUKAN 0 (harus gagal)", r.returncode != 0)

    conn = db_helper.get_conn(); cur = conn.cursor()
    after = db_get_po(cur, "TEST-PO-DKP-1")
    check("B: saldo PO-1 TIDAK berubah (rollback)", before == after, f"before={before} after={after}")
    check("B: invoice TIDAK tercatat (rollback)", not db_invoice_exists(cur, "902/VII/TestSite/2026"))
    cur.close(); conn.close()


def scenario_c_split_2_po():
    print("\n[Skenario C] 1 BAP kepotong ke 2 PO sekaligus")
    out_dir = f"{TEST_DIR}/output_split"
    script = f"{TEST_DIR}/run_c.py"
    # PO-1 sisa 500 (dari skenario A), diminta total 700 -> 500 dari PO-1, 200 dari PO-2
    make_test_script(script, "903/VII/TestSite/2026", "13 Juli 2026", "TESTBAP-003",
                      "TestSite", "TEST-PO-DKP-1", "Test Customer",
                      [("TEST-PO-DKP-1", 500), ("TEST-PO-DKP-2", 200)],
                      [(1, "Cocopeat", 500, 1000), (2, "Cocopeat", 200, 1000)], out_dir)
    r = run_script(script)
    check("C: script exit 0", r.returncode == 0, r.stderr[-300:])

    conn = db_helper.get_conn(); cur = conn.cursor()
    row1 = db_get_po(cur, "TEST-PO-DKP-1")
    row2 = db_get_po(cur, "TEST-PO-DKP-2")
    check("C: PO-1 total used = 1000 (500+500)", row1 is not None and float(row1[1]) == 1000, str(row1))
    check("C: PO-2 used = 200", row2 is not None and float(row2[1]) == 200, str(row2))
    cur.close(); conn.close()


def scenario_d_po_tidak_ada():
    print("\n[Skenario D] PO yang direferensikan tidak ada di DB -> harus gagal SEBELUM generate PDF")
    out_dir = f"{TEST_DIR}/output_d"
    script = f"{TEST_DIR}/run_d.py"
    make_test_script(script, "904/VII/TestSite/2026", "13 Juli 2026", "TESTBAP-004",
                      "TestSite", "TEST-PO-DKP-999", "Test Customer",
                      [("TEST-PO-DKP-999", 100)], [(1, "Cocopeat", 100, 1000)], out_dir)
    r = run_script(script)
    check("D: script exit BUKAN 0", r.returncode != 0)
    check("D: PDF TIDAK dibuat sama sekali", not os.path.exists(out_dir) or len(os.listdir(out_dir)) == 0)


def scenario_e_kks_non_pkp():
    print("\n[Skenario E] KKS (Non-PKP): generate sukses, PPN & DPP harus 0")
    out_dir = f"{TEST_DIR}/output_kks"
    script = f"{TEST_DIR}/run_e.py"
    make_test_script(script, "905/VII/TestSenyiur/2026", "13 Juli 2026", "TESTBAP-005",
                      "TestSenyiur", "TEST-PO-KKS-1", "Test Customer KKS",
                      [("TEST-PO-KKS-1", 20)], [(1, "Cocopeat", 20, 500000)], out_dir,
                      src_file=SRC_INVOICE_KKS)
    r = run_script(script)
    check("E: script exit 0", r.returncode == 0, r.stderr[-300:] + r.stdout[-300:])
    check("E: PDF fisik dibuat", os.path.exists(f"{out_dir}/Inv_905_VII_TestSenyiur_2026.pdf"))

    conn = db_helper.get_conn(); cur = conn.cursor()
    row = db_get_po(cur, "TEST-PO-KKS-1", bu_id=5)
    check("E: saldo PO KKS bertambah 20 m3", row is not None and float(row[1]) == 20, str(row))
    cur.execute("SELECT dpp, ppn, sub_total, grand_total, satuan FROM invoices WHERE no_invoice=%s", ("905/VII/TestSenyiur/2026",))
    inv = cur.fetchone()
    check("E: invoice KKS tercatat", inv is not None)
    if inv:
        dpp, ppn, sub, grand, satuan = inv
        check("E: DPP = 0 (non-PKP)", float(dpp) == 0, str(dpp))
        check("E: PPN = 0 (non-PKP)", float(ppn) == 0, str(ppn))
        check("E: grand_total == sub_total (no PPN)", float(grand) == float(sub), f"grand={grand} sub={sub}")
        check("E: satuan = m3", satuan == "m3", str(satuan))
    cur.close(); conn.close()


def scenario_f_kks_rollback():
    print("\n[Skenario F] KKS: PDF gagal -> rollback total")
    blocked = f"{TEST_DIR}/blocked_kks"
    with open(blocked, "w") as f:
        f.write("file biasa")
    out_dir = f"{blocked}/sub"

    conn = db_helper.get_conn(); cur = conn.cursor()
    before = db_get_po(cur, "TEST-PO-KKS-1", bu_id=5)
    cur.close(); conn.close()

    script = f"{TEST_DIR}/run_f.py"
    make_test_script(script, "906/VII/TestSenyiur/2026", "13 Juli 2026", "TESTBAP-006",
                      "TestSenyiur", "TEST-PO-KKS-1", "Test Customer KKS",
                      [("TEST-PO-KKS-1", 30)], [(1, "Cocopeat", 30, 500000)], out_dir,
                      src_file=SRC_INVOICE_KKS)
    r = run_script(script)
    check("F: script exit BUKAN 0", r.returncode != 0)

    conn = db_helper.get_conn(); cur = conn.cursor()
    after = db_get_po(cur, "TEST-PO-KKS-1", bu_id=5)
    check("F: saldo PO KKS TIDAK berubah (rollback)", before == after, f"before={before} after={after}")
    cur.close(); conn.close()


def scenario_g_multi_bap_satu_po():
    print("\n[Skenario G] 3 BAP dari 1 PO -> 3 baris invoice_items, no_bap masing-masing")
    out_dir = f"{TEST_DIR}/output_g"
    script = f"{TEST_DIR}/run_g.py"
    make_test_script(script, "907/VII/TestSite/2026", "13 Juli 2026",
                      "TESTBAP-G1, TESTBAP-G2, TESTBAP-G3",
                      "TestSite", "TEST-PO-DKP-2", "Test Customer",
                      [("TEST-PO-DKP-2", 300)],
                      [(1, "Cocopeat - PO.TEST-PO-DKP-2", 100, 1000, "TEST-PO-DKP-2", "TESTBAP-G1"),
                       (2, "Cocopeat - PO.TEST-PO-DKP-2", 100, 1000, "TEST-PO-DKP-2", "TESTBAP-G2"),
                       (3, "Cocopeat - PO.TEST-PO-DKP-2", 100, 1000, "TEST-PO-DKP-2", "TESTBAP-G3")],
                      out_dir)
    r = run_script(script)
    check("G: script exit 0", r.returncode == 0, r.stderr[-300:] + r.stdout[-300:])
    conn = db_helper.get_conn(); cur = conn.cursor()
    cur.execute("SELECT id FROM invoices WHERE no_invoice=%s", ("907/VII/TestSite/2026",))
    inv = cur.fetchone()
    check("G: invoice tercatat", inv is not None)
    if inv:
        cur.execute("SELECT urutan, no_bap, qty, po_id FROM invoice_items WHERE invoice_id=%s ORDER BY urutan", (inv[0],))
        rows = cur.fetchall()
        check("G: 3 baris invoice_items (bukan 1 gabungan)", len(rows) == 3, str(rows))
        baps = {row[1] for row in rows}
        check("G: no_bap tiap baris berbeda & benar",
              baps == {"TESTBAP-G1", "TESTBAP-G2", "TESTBAP-G3"}, str(baps))
        cur.execute("SELECT id FROM purchase_orders WHERE po_no='TEST-PO-DKP-2' AND badan_usaha_id=4")
        po2 = cur.fetchone()[0]
        check("G: semua baris po_id = PO-2 (dikelompokkan per PO)", all(row[3] == po2 for row in rows), str(rows))
    cur.close(); conn.close()


def main():
    print("=" * 60)
    print("TEST SUITE: invoice_dkp.py transaksi atomik")
    print("=" * 60)
    setup()
    try:
        scenario_a_sukses_normal()
        scenario_b_pdf_gagal_rollback()
        scenario_c_split_2_po()
        scenario_g_multi_bap_satu_po()
        scenario_d_po_tidak_ada()
        scenario_e_kks_non_pkp()
        scenario_f_kks_rollback()
    finally:
        cleanup()

    print("\n" + "=" * 60)
    print(f"HASIL: {len(PASS)} PASS, {len(FAIL)} FAIL")
    if FAIL:
        print("Detail yang gagal:")
        for name, detail in FAIL:
            print(f"  - {name}: {detail}")
        sys.exit(1)
    else:
        print("SEMUA SKENARIO LOLOS.")
        sys.exit(0)


if __name__ == "__main__":
    main()
