#!/usr/bin/env python3
import subprocess, json, urllib.request, sys, os, base64
import os
import config

TG_TOKEN = config.tg_token()
ANTHROPIC_KEY_FILE = config.d("anthropic_key.txt")
STATE_FILE = config.d("multi_bap_state.json")


def save_to_state(ocr_result):
    import json as _json
    STATE_FILE = config.d("multi_bap_state.json")
    try:
        with open(STATE_FILE) as f:
            state = _json.load(f)
    except:
        state = {"active": False, "bap_list": [], "site": "", "inv_date": ""}
    if not state.get("active"):
        state = {
            "active": True,
            "site": ocr_result.get("site",""),
            "inv_date": ocr_result.get("tanggal",""),
            "bap_list": [{"no_bap": ocr_result.get("no_bap",""), "qty_kg": float(ocr_result.get("qty_kg",0) or 0), "qty_m3": float(ocr_result.get("qty_m3",0) or 0)}]
        }
    else:
        state["bap_list"].append({
            "no_bap": ocr_result.get("no_bap",""),
            "qty_kg": float(ocr_result.get("qty_kg",0) or 0),
            "qty_m3": float(ocr_result.get("qty_m3",0) or 0)
        })
    with open(STATE_FILE, "w") as f:
        _json.dump(state, f, indent=2)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status":"error","message":"No file_id"}))
        sys.exit(1)

    file_id = sys.argv[1]

    with open(ANTHROPIC_KEY_FILE) as f:
        ant_key = f.read().strip()

    # Download file (PDF atau foto)
    r = urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/getFile?file_id={file_id}")
    file_info = json.loads(r.read())["result"]
    file_path = file_info["file_path"]
    file_data = urllib.request.urlopen(f"https://api.telegram.org/file/bot{TG_TOKEN}/{file_path}").read()

    # Deteksi tipe file
    is_photo = any(file_path.lower().endswith(ext) for ext in [".jpg",".jpeg",".png",".webp"])

    content_parts = []

    if is_photo:
        # Foto langsung encode ke base64
        ext = file_path.split(".")[-1].lower()
        mime = "image/jpeg" if ext in ["jpg","jpeg"] else f"image/{ext}"
        png_b64 = base64.b64encode(file_data).decode()
        content_parts.append({"type":"image","source":{"type":"base64","media_type":mime,"data":png_b64}})
    else:
        # PDF - convert ke PNG
        with open("/tmp/bap.pdf","wb") as f: f.write(file_data)
        subprocess.run(["pdftoppm","-r","120","-png","-l","2","/tmp/bap.pdf","/tmp/bap_p"],
                       check=True, capture_output=True)
        for page in ["1", "2"]:
            png_file = f"/tmp/bap_p-{page}.png"
            if os.path.exists(png_file):
                png_b64 = base64.b64encode(open(png_file,"rb").read()).decode()
                content_parts.append({"type":"image","source":{"type":"base64","media_type":"image/png","data":png_b64}})

    body = json.dumps({
        "model": "claude-opus-4-6",
        "max_tokens": 512,
        "messages": [{"role":"user","content": content_parts + [
            {"type":"text","text":"Ini foto BAP Cocopeat. Jawab HANYA JSON tanpa teks lain:\n{\"no_bap\":\"nomor BAP\",\"tanggal\":\"DD Bulan YYYY contoh 15 Juni 2026\",\"site\":\"Senyiur atau Jembayan atau Suring atau Sebakis atau Sesayap\",\"qty_kg\":angka_berat_bersih_KG_jika_ada_kolom_KG_atau_0,\"qty_m3\":angka_total_m3_jika_ada_kolom_Total_m3_atau_0,\"jumlah_sak\":angka_sak_yang_diterima,\"confidence\":\"high atau medium atau low\"}\n\nCatatan: BAP Senyiur pakai kolom Total (m3) bukan KG. BAP lain pakai Berat Bersih KG."}
        ]}]
    }).encode()

    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body)
    req.add_header("x-api-key", ant_key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")
    resp = json.loads(urllib.request.urlopen(req).read())
    text = resp["content"][0]["text"]
    clean = text.replace("```json","").replace("```","").strip()
    result = json.loads(clean)
    save_to_state(result)
    print(json.dumps(result))

if __name__ == "__main__":
    main()

def save_to_state(ocr_result):
    """Simpan hasil OCR ke multi_bap_state untuk multi-BAP"""
    STATE_FILE = config.d("multi_bap_state.json")
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except:
        state = {"active": False, "bap_list": [], "site": "", "inv_date": ""}

    if not state.get("active"):
        # Mulai sesi baru
        state = {
            "active": True,
            "site": ocr_result.get("site",""),
            "inv_date": ocr_result.get("tanggal",""),
            "bap_list": [{
                "no_bap": ocr_result.get("no_bap",""),
                "qty_kg": float(ocr_result.get("qty_kg",0)),
                "confidence": ocr_result.get("confidence","low")
            }]
        }
    else:
        # Tambah ke sesi yang ada
        state["bap_list"].append({
            "no_bap": ocr_result.get("no_bap",""),
            "qty_kg": float(ocr_result.get("qty_kg",0)),
            "confidence": ocr_result.get("confidence","low")
        })

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
