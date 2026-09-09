"""
cuaca_pasangkayu.py -- K10: tarik cuaca harian Pasangkayu (Sulawesi Barat) dari Open-Meteo
(tanpa API key) dan simpan ke ops_cuaca (sumber='api'). Idempoten: upsert per tanggal.

Dijalankan n8n tiap pagi:  docker exec -i invoice-api-prod python /app/webapp/cuaca_pasangkayu.py
Mengambil 3 hari terakhir (termasuk hari ini) supaya hari yang terlewat ikut terisi.
Log cuaca = satu-satunya rujukan alasan cuaca (SOP-CP-001 §4).
"""
import json
import sys
import urllib.request
from datetime import date, timedelta

sys.path[:0] = ["/app/webapp", "/app"]
import settings  # noqa: E402,F401
import db_helper  # noqa: E402

LAT, LON = -1.18, 119.36  # Pasangkayu, Sulawesi Barat
TZ = "Asia/Makassar"
KODE = {0: "cerah", 1: "cerah berawan", 2: "berawan", 3: "mendung", 45: "kabut", 48: "kabut",
        51: "gerimis", 53: "gerimis", 55: "gerimis lebat", 61: "hujan ringan", 63: "hujan sedang", 65: "hujan lebat",
        80: "hujan lokal", 81: "hujan lokal sedang", 82: "hujan lokal lebat", 95: "badai petir", 96: "badai petir es",
        99: "badai petir es"}


def main():
    mulai = date.today() - timedelta(days=2)
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
           f"&daily=precipitation_sum,temperature_2m_max,weather_code&timezone={TZ}"
           f"&start_date={mulai}&end_date={date.today()}")
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.loads(r.read())["daily"]
    conn = db_helper.get_conn()
    cur = conn.cursor()
    n = 0
    for tgl, hujan, suhu, kode in zip(d["time"], d["precipitation_sum"], d["temperature_2m_max"], d["weather_code"]):
        cur.execute(
            "INSERT INTO ops_cuaca (tanggal, sumber, hujan_mm, suhu_max_c, cuaca_teks) VALUES (%s,'api',%s,%s,%s) "
            "ON CONFLICT (tanggal, sumber) DO UPDATE SET hujan_mm=EXCLUDED.hujan_mm, suhu_max_c=EXCLUDED.suhu_max_c, "
            "cuaca_teks=EXCLUDED.cuaca_teks",
            (tgl, hujan, suhu, KODE.get(kode, f"kode {kode}")))
        n += 1
    conn.commit()
    conn.close()
    print(f"CUACA_OK {n} hari ({d['time'][0]}..{d['time'][-1]})")


if __name__ == "__main__":
    main()
