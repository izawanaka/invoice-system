#!/bin/bash
SITE=$(python3 -c "import json; d=json.load(open('/home/izawa/invoice-system/bap_input.json')); print(d.get('site',''))" 2>/dev/null)
if [ "$SITE" = "Senyiur" ]; then
    python3 /home/izawa/invoice-system/bap_to_invoice_kks.py
else
    python3 /home/izawa/invoice-system/bap_to_invoice.py
fi
