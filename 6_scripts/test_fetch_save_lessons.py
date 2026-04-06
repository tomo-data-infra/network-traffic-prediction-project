# test

import pdfplumber
import pprint

pdf_path = "/mnt/c/Users/user/Documents/projects/ping_rtt_prediction/1_data/calendar/【配布用】NDY_講座スケジュール2月分.pdf"

# in wsl, a windows style path with backslashes is invalid!
# pdf_path = r"C:\Users\user\Documents\projects\ping_rtt_prediction\1_data\calendar\【配布用】NDY_講座スケジュール2月分.pdf"
# pdf_path = r"C:\Users\user\Documents\projects\ping_rtt_prediction\1_data\calendar\NDY_schedule_202602.pdf"

def fetch_save_lessons(pdf_path, output_txt):
    all_lessons = []
    
    with pdfplumber.open(pdf_path) as pdf:
        # We start with the first page of the calendar
        table = pdf.pages[0].extract_table()
        
        if table:
            for row in table:
                # Remove None values so the text file isn't cluttered
                clean_row = [cell.replace('\n', ' ') for cell in row if cell]
                if any(clean_row): # Only add rows that aren't empty
                    all_lessons.append(clean_row)

    # Write the data structure to a .txt file
    with open(output_txt, "w", encoding="utf-8") as f:
        # Using pprint makes the list-of-lists look like a grid in the text file
        pprint.pprint(all_lessons, stream=f, width=100)
    
    print(f"Extraction complete. Check {output_txt} for the data structure.")

# Run it
fetch_save_lessons(pdf_path, "debug_structure.txt")
