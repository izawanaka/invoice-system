import openpyxl
from openpyxl.styles import Alignment
import os
import config

EXCEL = config.d("PO_Tracker_KKS.xlsx")
wb = openpyxl.load_workbook(EXCEL)
print("Sheets:", wb.sheetnames)
wb.close()
