
import pandas as pd
import os

file_path = "Data/Function cost allocation analysis to IT 20260104.xlsx"
if os.path.exists(file_path):
    try:
        xl = pd.ExcelFile(file_path)
        print(f"Sheet names: {xl.sheet_names}")
    except Exception as e:
        print(f"Error reading excel: {e}")
else:
    print(f"File not found: {file_path}")
