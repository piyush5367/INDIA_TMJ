import re
import pdfplumber
import pandas as pd
import streamlit as st
import logging
from io import BytesIO
from typing import Dict, List

# Configure logging
logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Constants for section markers
SECTION_MARKERS = {
    "CORRIGENDA": "CORRIGENDA",
    "RENEWAL": "Following Trade Marks Registration Renewed",
    "REGISTERED": "Following Trade Mark applications have been Registered"
}

# Number extraction functions
def extract_numbers(text: str, pattern: str) -> List[str]:
    try:
        return re.findall(pattern, text) if isinstance(text, str) else []
    except Exception as e:
        logging.error(f"Regex error: {e}")
        return []

def extract_advertisement_numbers(text: str) -> List[str]:
    advertisement_numbers = []
    try:
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if SECTION_MARKERS["CORRIGENDA"] in line:
                break
            matches = extract_numbers(line, r'(\d{5,})\s+\d{2}/\d{2}/\d{4}')
            advertisement_numbers.extend(matches)
    except Exception as e:
        logging.error(f"Advertisement extraction error: {e}")
    return advertisement_numbers

def extract_corrigenda_numbers(text: str) -> List[str]:
    corrigenda_numbers = []
    found_corrigenda_section = False
    try:
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if SECTION_MARKERS["CORRIGENDA"] in line:
                found_corrigenda_section = True
                continue
            if SECTION_MARKERS["REGISTERED"] in line:
                break
            if found_corrigenda_section:
                matches = extract_numbers(line, r'(\d{5,})')
                corrigenda_numbers.extend(matches)
    except Exception as e:
        logging.error(f"Corrigenda extraction error: {e}")
    return corrigenda_numbers

def extract_rc_numbers(text: str) -> List[str]:
    return extract_numbers_from_section(text, SECTION_MARKERS["RENEWAL"], r'\b\d{5,}\b')

def extract_renewal_numbers(text: str) -> List[str]:
    return extract_numbers_from_section(text, SECTION_MARKERS["RENEWAL"], r'\b(\d{5,})\b', start_after_section=True)

def extract_numbers_from_section(text: str, section_marker: str, pattern: str, start_after_section=False) -> List[str]:
    numbers = []
    found_section = False
    try:
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if section_marker in line:
                found_section = True
                if not start_after_section:
                    continue
            if found_section:
                matches = extract_numbers(line, pattern)
                numbers.extend(matches)
    except Exception as e:
        logging.error(f"Extraction error for section {section_marker}: {e}")
    return numbers

# PDF extraction with enhanced stability
def extract_numbers_from_pdf(pdf_file) -> Dict[str, List[str]]:
    extracted_data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []}
    
    if not pdf_file:
        st.error("No file uploaded.")
        return extracted_data

    try:
        pdf_file.seek(0)
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                st.warning("PDF is empty.")
                return extracted_data

            progress_bar = st.progress(0)
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text() or ""
                    extracted_data["Advertisement"].extend(extract_advertisement_numbers(text))
                    extracted_data["Corrigenda"].extend(extract_corrigenda_numbers(text))
                    extracted_data["RC"].extend(extract_rc_numbers(text))
                    extracted_data["Renewal"].extend(extract_renewal_numbers(text))
                    progress_bar.progress(min((i + 1) / total_pages, 1.0))
                except Exception as e:
                    logging.error(f"Page {i+1} processing error: {e}")
                    continue  # Skip problematic pages
    except Exception as e:
        st.error(f"Failed to process PDF: {e}")
        logging.error(f"PDF processing error: {e}")
    
    return extracted_data

# Excel generation with error handling
def save_to_excel(data_dict: Dict[str, List[str]]) -> bytes:
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for sheet_name, numbers in data_dict.items():
                if numbers:
                    valid_numbers = [num for num in numbers if num.isdigit()]
                    if valid_numbers:
                        df = pd.DataFrame(sorted(set(map(int, valid_numbers))), columns=["Numbers"])
                        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        output.seek(0)
        return output.getvalue() if any(data_dict.values()) else None
    except Exception as e:
        st.error(f"Failed to create Excel file: {e}")
        logging.error(f"Excel error: {e}")
        return None

# Streamlit app with robust UI
def main():
    try:
        st.set_page_config(page_title="INDIA TMJ", layout="wide")
        st.title("INDIA TMJ - PDF Extraction")

        # Sidebar for file upload
        with st.sidebar:
            uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"], help="Upload a PDF to extract numbers")

        if uploaded_file:
            st.write(f"Processing: **{uploaded_file.name}**")
            with st.spinner("Extracting numbers from PDF..."):
                extracted_data = extract_numbers_from_pdf(uploaded_file)
                excel_data = save_to_excel(extracted_data)

            if any(extracted_data.values()):
                st.success("Extraction completed successfully!")

                # Display results in tabs
                tabs = st.tabs(extracted_data.keys())
                for tab, (category, numbers) in zip(tabs, extracted_data.items()):
                    with tab:
                        if numbers:
                            st.write(f"Found {len(numbers)} numbers")
                            valid_numbers = [num for num in numbers if num.isdigit()]
                            if valid_numbers:
                                df = pd.DataFrame(sorted(set(map(int, valid_numbers))), columns=["Numbers"])
                                st.dataframe(df, use_container_width=True, height=300)
                            else:
                                st.info(f"No valid {category} numbers found.")
                        else:
                            st.info(f"No {category} numbers found.")

                # Download button
                if excel_data:
                    st.download_button(
                        label="📥 Download Excel File",
                        data=excel_data,
                        file_name=f"extracted_numbers_{uploaded_file.name.split('.')[0]}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download-btn"
                    )
            else:
                st.warning("No data extracted from the PDF.")
                
    except Exception as e:
        st.error(f"Application failed to start: {e}")
        logging.error(f"Main app error: {e}")

if __name__ == "__main__":
    main()
