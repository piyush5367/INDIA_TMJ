import re
import pdfplumber
import pandas as pd
import streamlit as st
import openpyxl
import logging
from io import BytesIO

# Configure logging
logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, format="%(asctime)s - %(message)s")

def extract_numbers(text, pattern):
    """Extracts numbers using regex and filters valid ones."""
    return list(set(re.findall(pattern, text)))

def extract_advertisement_numbers(text):
    """Extract Advertisement numbers with improved accuracy."""
    return extract_numbers(text, r'\b(\d{5,7})\b\s+\d{2}/\d{2}/\d{4}')

def extract_corrigenda_numbers(text):
    """Extract Corrigenda numbers dynamically."""
    corrigenda_numbers = []
    found_section = False
    for line in text.split("\n"):
        if "CORRIGENDA" in line:
            found_section = True
            continue
        if "Following Trade Mark applications have been Registered" in line:
            break
        if found_section:
            corrigenda_numbers.extend(extract_numbers(line, r'\b(\d{5,7})\b'))
    return corrigenda_numbers

def extract_rc_numbers(text):
    """Extract RC numbers based on structured formatting."""
    return extract_numbers(text, r'\b(\d{5,7})\b')

def extract_renewal_numbers(text):
    """Extract Renewal numbers more effectively."""
    return extract_numbers(text, r'\b(\d{5,7})\b')

def extract_numbers_from_pdf(pdf_file):
    extracted_data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []}
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    extracted_data["Advertisement"].extend(extract_advertisement_numbers(text))
                    extracted_data["Corrigenda"].extend(extract_corrigenda_numbers(text))
                    extracted_data["RC"].extend(extract_rc_numbers(text))
                    extracted_data["Renewal"].extend(extract_renewal_numbers(text))
    except Exception as e:
        logging.error(f"Error processing PDF: {e}")
        st.error(f"Error processing PDF: {e}")
    return extracted_data

def save_to_excel(data_dict):
    """Save extracted numbers to an Excel file."""
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for sheet_name, numbers in data_dict.items():
                if numbers:
                    df = pd.DataFrame(sorted(set(map(int, numbers))), columns=["Numbers"])
                    df.to_excel(writer, index=False, sheet_name=sheet_name)
        output.seek(0)
        return output if any(data_dict.values()) else None
    except Exception as e:
        logging.error(f"Error saving to Excel: {e}")
        st.error(f"Error saving to Excel: {e}")
        return None

def main():
    st.title("Enhanced PDF Number Extractor")
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    if uploaded_file is not None:
        with st.spinner("Extracting numbers..."):
            extracted_data = extract_numbers_from_pdf(uploaded_file)
            excel_file = save_to_excel(extracted_data)
        if excel_file:
            st.success("Extraction Completed!")
            st.download_button("Download Excel File", excel_file, "extracted_numbers.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        for category, numbers in extracted_data.items():
            st.write(f"{category}: {len(numbers)} numbers found")

if __name__ == "__main__":
    main()
