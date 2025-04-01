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

# Number extraction functions (unchanged logic)
def extract_numbers(text: str, pattern: str) -> List[str]:
    try:
        if not isinstance(text, str):
            return []
        return re.findall(pattern, text)
    except Exception as e:
        logging.error(f"Regex error: {e}")
        return []

def extract_advertisement_numbers(text: str) -> List[str]:
    advertisement_numbers = []
    try:
        if not isinstance(text, str):
            return []
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
        if not isinstance(text, str):
            return []
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
    rc_numbers = []
    try:
        ifз not isinstance(text, str):
            return []
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if SECTION_MARKERS["RENEWAL"] in line:
                break
            matches = extract_numbers(line, r'\b\d{5,}\b')
            rc_numbers.extend(matches)
    except Exception as e:
        logging.error(f"RC extraction error: {e}")
    return rc_numbers

def extract_renewal_numbers(text: str) -> List[str]:
    renewal_numbers = []
    found_renewal_section = False
    try:
        if not isinstance(text, str):
            return []
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if SECTION_MARKERS["RENEWAL"] in line:
                found_renewal_section = True
                continue
            if found_renewal_section:
                matches = extract_numbers(line, r'\b(\d{5,})\b')
                renewal_numbers.extend(matches)
    except Exception as e:
        logging.error(f"Renewal extraction error: {e}")
    return renewal_numbers

# PDF extraction with enhanced stability
def extract_numbers_from_pdf(pdf_file) -> Dict[str, List[str]]:
    extracted_data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []}
    
    if not pdf_file:
        st.error("No file uploaded.")
        return extracted_data

    try:
        # Ensure file is readable
        pdf_file.seek(0)
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                st.warning("PDF is empty.")
                return extracted_data

            progress_bar = st.progress(0)
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text()
                    if text is None:  # Handle cases where extract_text returns None
                        text = ""
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
                    try:
                        # Filter and convert numbers safely
                        valid_numbers = [num for num in numbers if isinstance(num, str) and num.isdigit()]
                        if valid_numbers:
                            df = pd.DataFrame(sorted(set(map(int, valid_numbers))), columns=["Numbers"])
                            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
                    except Exception as e:
                        logging.error(f"Error writing {sheet_name} to Excel: {e}")
                        continue
        output.seek(0)
        excel_data = output.getvalue()
        return excel_data if excel_data and any(data_dict.values()) else None
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

        if uploaded_file is not None:
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
                            try:
                                valid_numbers = [num for num in numbers if isinstance(num, str) and num.isdigit()]
                                if valid_numbers:
                                    df = pd.DataFrame(sorted(set(map(int, valid_numbers))), columns=["Numbers"])
                                    st.dataframe(df, use_container_width=True, height=300)
                                else:
                                    st.info(f"No valid {category} numbers found.")
                            except Exception as e:
                                st.warning(f"Error displaying {category} data: {e}")
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