import streamlit as st
import re
import pdfplumber
import pandas as pd
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Logging setup
logging.basicConfig(filename="pdf_extraction.log", level=logging.DEBUG, format="%(asctime)s - %(message)s")

# Regex patterns
advertisement_pattern = re.compile(r' (\d{5,})\s+\d{2}/\d{2}/\d{4}')
corrigenda_pattern = re.compile(r' (\d{5,})\s*[--]')
rc_pattern = re.compile(r'\b(\d{7})\b')
renewal_pattern_7_digits = re.compile(r'\b(\d{7})\b')
renewal_pattern_application_no = re.compile(r'Application No\s*(\d{5,})')

def extract_numbers(text, pattern):
    return pattern.findall(text)

def extract_advertisement_numbers(text):
    numbers = []
    for line in text.splitlines():
        if "CORRIGENDA" in line:
            break
        numbers.extend(extract_numbers(line, advertisement_pattern))
    return numbers

def extract_corrigenda_numbers(text):
    numbers = []
    found = False
    for line in text.splitlines():
        if "CORRIGENDA" in line:
            found = True
            continue
        if "Following Trade Mark applications have been Registered" in line:
            break
        if found:
            numbers.extend(extract_numbers(line, corrigenda_pattern))
    return numbers

def extract_rc_numbers(text):
    numbers = []
    for line in text.splitlines():
        if "Following Trade Marks Registration Renewed" in line:
            break
        columns = line.split()
        if len(columns) == 5 and all(col.isdigit() for col in columns):
            numbers.extend(columns)
    return numbers

def extract_renewal_numbers(text):
    numbers = []
    found = False
    for line in text.splitlines():
        if "Following Trade Marks Registration Renewed" in line:
            found = True
            continue
        if found:
            numbers.extend(extract_numbers(line, renewal_pattern_7_digits))
            numbers.extend(extract_numbers(line, renewal_pattern_application_no))
    return numbers

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

def extract_from_pdf(pdf_file, progress_bar, status_text):
    data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []}
    try:
        with pdfplumber.open(pdf_file) as pdf:
            pages = pdf.pages
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {executor.submit(process_page, page): i for i, page in enumerate(pages)}
                for i, future in enumerate(as_completed(futures)):
                    result = future.result()
                    if result:
                        for key, values in result.items():
                            data[key].extend(values)
                    progress_bar.progress((i + 1) / len(pages))
                    status_text.markdown(f"<h4 style='text-align: center; color: #FFA500;'>Processed {i + 1}/{len(pages)} pages...</h4>", unsafe_allow_html=True)
            progress_bar.progress(1.0)
            return data
    except Exception as e:
        st.error(f"Error processing PDF: {e}")
        logging.error(f"PDF processing error: {e}")
        return None

def main():
    st.set_page_config(page_title="PDF Extractor", page_icon="📄", layout="wide")
    st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>INDIA TMJ PDF Extractor</h1>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center; color: #4CAF50;'>Extract Numbers from PDF</h2>", unsafe_allow_html=True)

    uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])

    if uploaded_file:
        progress_bar = st.progress(0)
        status_text = st.empty()
        with st.spinner("Processing PDF..."):
            extracted_data = extract_from_pdf(uploaded_file, progress_bar, status_text)

        if extracted_data and any(extracted_data.values()):
            st.success("Extraction complete!")
            st.markdown("<h3 style='text-align: center; color: #4CAF50;'>Extracted Data</h3>", unsafe_allow_html=True)

            tabs = st.tabs(["Advertisement", "Corrigenda", "RC", "Renewal"])
            for tab, (section, numbers) in zip(tabs, extracted_data.items()):
                with tab:
                    if numbers:
                        st.dataframe(pd.DataFrame(sorted(set(numbers)), columns=["Numbers"]))
                    else:
                        st.write(f"No {section} numbers found.")
        else:
            st.warning("No matching numbers found in the PDF.")

if __name__ == "__main__":
    main()
