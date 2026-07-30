#!/usr/bin/env python3
"""
Handler multi-BAP: simpan BAP ke state, generate invoice saat SELESAI
"""
import json, sys, os, subprocess
import os
import config

STATE_FILE = config.d("multi_bap_state.json")
BAP_INPUT  = config.d("bap_input.json")

def read_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {"active": False, "bap_list": [], "site": "", "inv_date": ""}

def write_state(s):
    with open(STATE_FILE, "w") as f: json.dump(s, f, indent=2)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"action":"error","message":"No input"}))
        sys.exit(1)

    cmd = sys.argv[1]
    ocr_json = sys.argv[2] if len(sys.argv) > 2 else "{}"

    try: ocr = json.loads(ocr_json)
    except: ocr = {}

    state = read_state()

    # Command TAMBAH - tambah BAP ke state
    if cmd == "TAMBAH":
        if not state["active"]:
            print(json.dumps({"action":"error","message":"Tidak ada sesi aktif"}))
            return

        site_ocr = ocr.get("site", state.get("site", ""))
        if site_ocr == "Senyiur":
            qty = float(ocr.get("qty_m3", 0))
            unit = "M3"
        else:
            qty = float(ocr.get("qty_kg", 0))
            unit = "KG"
        no_bap = ocr.get("no_bap", "")
        conf  = ocr.get("confidence", "low")

        if not qty or not no_bap:
            print(json.dumps({
                "action": "confirm",
                "message": f"⚠️ Data BAP tidak lengkap:\nNo BAP: {no_bap or 'tidak terbaca'}\nQTY: {qty or 'tidak terbaca'}\n\nKoreksi atau kirim ulang BAP"
            }))
            return

        state["bap_list"].append({"no_bap": no_bap, "qty_kg": qty, "confidence": conf})
        write_state(state)

        total_qty = sum(b.get("qty_m3", b.get("qty_kg",0)) for b in state["bap_list"])
        bap_nos   = ", ".join(b["no_bap"] for b in state["bap_list"])

        print(json.dumps({
            "action": "added",
            "message": f"✅ BAP {no_bap} ditambahkan ({qty:,.0f} KG)\n\nTotal sementara: {total_qty:,.0f} KG\nBAP: {bap_nos}\n\nKirim BAP lagi atau ketik SELESAI untuk generate invoice"
        }))
        return

    # Command SELESAI - generate invoice gabungan
    if cmd == "SELESAI":
        if not state["active"] or not state["bap_list"]:
            print(json.dumps({"action":"error","message":"Tidak ada BAP yang aktif"}))
            return

        total_qty = sum(b.get("qty_m3", b.get("qty_kg",0)) for b in state["bap_list"])
        bap_nos   = ", ".join(b["no_bap"] for b in state["bap_list"])
        site      = state["site"]
        inv_date  = state["inv_date"]

        # Tulis ke bap_input.json
        bap_input = {
            "site":     site,
            "qty_kg":   total_qty,
            "no_bap":   bap_nos,
            "inv_date": inv_date
        }
        with open(BAP_INPUT, "w") as f:
            json.dump(bap_input, f, ensure_ascii=False)

        # Generate invoice
        result = subprocess.run(
            ["python3", config.k("bap_to_invoice.py")],
            capture_output=True, text=True
        )
        stdout = result.stdout.strip()
        lines  = stdout.split("\n")
        json_line = next((l for l in lines if l.startswith("{")), "{}")

        try:
            inv_result = json.loads(json_line)
        except:
            inv_result = {"status": "error", "message": stdout[:200]}

        # Reset state
        write_state({"active": False, "bap_list": [], "site": "", "inv_date": ""})

        print(json.dumps({"action": "generated", "result": inv_result}))
        return

    # BAP pertama - mulai sesi baru
    if cmd == "NEW":
        site_ocr = ocr.get("site", "")
        if site_ocr == "Senyiur":
            qty = float(ocr.get("qty_m3", 0))
            unit = "M3"
        else:
            qty = float(ocr.get("qty_kg", 0))
            unit = "KG"
        no_bap = ocr.get("no_bap", "")
        site   = ocr.get("site", "")
        tanggal = ocr.get("tanggal", "")
        conf   = ocr.get("confidence", "low")

        if not qty or not site or (not no_bap and site != "Senyiur"):
            print(json.dumps({
                "action": "confirm",
                "message": f"⚠️ Data BAP:\nNo BAP: {no_bap or 'tidak terbaca'}\nTanggal: {tanggal or 'tidak terbaca'}\nSite: {site or 'tidak terbaca'}\nQTY: {qty or 'tidak terbaca'} {unit}\n\nKetik KONFIRM jika benar atau koreksi"
            }))
            return

        # Mulai state baru
        state = {
            "active":   True,
            "site":     site,
            "inv_date": tanggal,
            "bap_list": [{"no_bap": no_bap, "qty_kg": qty if unit=="KG" else 0, "qty_m3": qty if unit=="M3" else 0, "confidence": conf}]
        }
        write_state(state)

        print(json.dumps({
            "action": "started",
            "message": f"✅ BAP pertama diterima:\nNo BAP: {no_bap or '-'}\nSite: {site}\nQTY: {qty:,.0f} {unit}\nTanggal: {tanggal}\n\nKirim BAP berikutnya atau ketik SELESAI untuk generate invoice"
        }))

if __name__ == "__main__":
    main()
