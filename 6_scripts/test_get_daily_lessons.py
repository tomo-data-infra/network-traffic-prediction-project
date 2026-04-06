# test
import pdfplumber
import pandas as pd

pdf_path = "C:\Users\user\Documents\projects\ping_rtt_prediction\1_data\calendar\【配布用】NDY_講座スケジュール2月分.pdf"

def get_daily_lessons(pdf_path):
    all_lessons = []
    with pdfplumber.open(pdf_path) as pdf:
        table = pdf.pages[0].extract_table()
        df = pd.DataFrame(table) # Raw grid
        
        # We iterate through the 'Grid' to find lesson titles
        for row in table:
            # Clean the row of 'None' values (empty cells)
            clean_row = [cell for cell in row if cell]
            if clean_row:
                all_lessons.append(clean_row)
                
    return all_lessons
