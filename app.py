import streamlit as st
import os
import re
import pdfplumber
import pandas as pd
import logging
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up logging
logging.basicConfig(
    filename="pdf_extraction.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(message)s"
)

# Precompile regex patterns
advertisement_pattern = re.compile(r' (\d{5,})\s+\d{2}/\d{2}/\d{4}')
corrigenda_pattern = re.compile(r' (\d{5,})\s*[--]')
rc_pattern = re.compile(r'\b(\d{7})\b')
renewal_pattern_7_digits = re.compile(r'\b(\d{7})\b')
renewal_pattern_application_no = re.compile(r'Application No\s*(\d{5,})')

# Function to extract numbers
def extract_numbers(text, pattern):
    return pattern.findall(text)

def extract_advertisement_numbers(text):
    advertisement_numbers = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line:
            break
        advertisement_numbers.extend(extract_numbers(line, advertisement_pattern))
    return advertisement_numbers

def extract_corrigenda_numbers(text):
    corrigenda_numbers = []
    found_corrigenda_section = False
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line:
            found_corrigenda_section = True
            continue
        if "Following Trade Mark applications have been Registered" in line:
            break
        if found_corrigenda_section:
            corrigenda_numbers.extend(extract_numbers(line, corrigenda_pattern))
    return corrigenda_numbers

def extract_rc_numbers(text):
    rc_numbers = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "Following Trade Marks Registration Renewed" in line:
            break
        columns = line.split()
        if len(columns) == 5 and all(col.isdigit() for col in columns):
            rc_numbers.extend(columns)
    return rc_numbers

def extract_renewal_numbers(text):
    renewal_numbers = []
    found_renewal_section = False
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "Following Trade Marks Registration Renewed" in line:
            found_renewal_section = True
            continue
        if found_renewal_section:
            renewal_numbers.extend(extract_numbers(line, renewal_pattern_7_digits))
            renewal_numbers.extend(extract_numbers(line, renewal_pattern_application_no))
    return renewal_numbers

# Extract numbers from a single page
def process_page(page):
    text = page.extract_text()
    if not text:
        return None
    return {
        "Advertisement": extract_advertisement_numbers(text),
        "Corrigenda": extract_corrigenda_numbers(text),
        "RC": extract_rc_numbers(text),
        "Renewal": extract_renewal_numbers(text),
    }

def extract_numbers_from_pdf(pdf_file, progress_bar):
    extracted_data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []}
    try:
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            status_text = st.empty()
            processed_pages = 0
            progress_bar.progress(0)
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(process_page, page): i for i, page in enumerate(pdf.pages)}
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result:
                            for key in extracted_data:
                                extracted_data[key].extend(result[key])
                        processed_pages += 1
                        progress_bar.progress(processed_pages / total_pages)
                        status_text.markdown(f"<h4 style='text-align: center;'>Processed {processed_pages}/{total_pages} pages...</h4>", unsafe_allow_html=True)
                    except Exception as e:
                        logging.error(f"Error processing page {futures[future]}: {str(e)}")
        progress_bar.empty()
        return extracted_data
    except Exception as e:
        st.error("❌ Error processing PDF. Check logs.")
        logging.error(f"PDF processing failed: {str(e)}")
        return None

def main():
    st.set_page_config(page_title="PDF Extractor", page_icon="📄", layout="wide")
    st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>INDIA TMJ</h1>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center; color: #4CAF50;'>Extract Numbers from PDFs</h2>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("📄 Upload a PDF", type=["pdf"])
    if uploaded_file:
        progress_bar = st.progress(0)
        extracted_data = extract_numbers_from_pdf(uploaded_file, progress_bar)
        if extracted_data and any(extracted_data.values()):
            st.success("✅ Extraction Completed!")
            st.markdown("<h3 style='text-align: center; color: #4CAF50;'>Preview Extracted Data</h3>", unsafe_allow_html=True)
            selected_section = st.selectbox("Select a Section", list(extracted_data.keys()))
            st.dataframe(pd.DataFrame(sorted(set(extracted_data[selected_section])), columns=["Numbers"]))
        else:
            st.warning("⚠️ No matching numbers found.")
        progress_bar.empty()

if __name__ == "__main__":
    main()
