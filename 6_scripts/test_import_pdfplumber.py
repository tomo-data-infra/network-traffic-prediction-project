import pdfplumber
import pandas as pd
import re

def extract_zoom_schedule(pdf_path):
    sessions = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue
                
            # Convert to DataFrame for easier architect-level handling
            df = pd.DataFrame(table[1:], columns=table[0])
            
            for index, row in df.iterrows():
                # Logic: Look for "Zoom" or "10:00" in the text
                # We use .join to search the whole row if columns aren't aligned
                row_text = " ".join([str(val) for val in row if val])
                
                if "Zoom" in row_text or "10:00" in row_text:
                    # Professional Regex to find the date (e.g., Feb 18)
                    date_match = re.search(r'(\d{1,2})', row_text)
                    
                    sessions.append({
                        "raw_data": row_text,
                        "potential_date": date_match.group(1) if date_match else "Unknown"
                    })
    
    return sessions

# Test it on one of your /data files
# results = extract_zoom_schedule("data/Feb_Schedule.pdf")
# print(results)
