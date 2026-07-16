import json, sys
data = {
    'site': sys.argv[1],
    'qty_kg': float(sys.argv[2]),
    'qty_m3': float(sys.argv[3]),
    'no_bap': sys.argv[4],
    'inv_date': sys.argv[5],
    'next_seq': int(sys.argv[6]) if len(sys.argv) > 6 else 0,
    'items': []
}
with open('/home/izawa/invoice-system/bap_input_kks.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False)
print('ok')
