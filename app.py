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
advertisement_pattern = re.compile(r'(\d{5,})\s+\d{2}/\d{2}/\d{4}')
corrigenda_pattern = re.compile(r'(\d{5,})\s*[ ]')
rc_pattern = re.compile(r'\b(\d{7})\b')
renewal_pattern_7_digits = re.compile(r'\b(\d{7})\b')
renewal_pattern_application_no = re.compile(r'Application No\s*\((\d+)\)\s*Class')

# Extraction functions
def extract_advertisement_numbers(text):
    advertisement_numbers = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line:  # Stop when Corrigenda section starts
            break
        matches = re.findall(r'(\d{5,})\s+\d{2}/\d{2}/\d{4}', line)
        advertisement_numbers.extend(matches)
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
            matches = re.findall(r'(\d{5,})\s*[--]', line)
            corrigenda_numbers.extend(matches)
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
            renewal_numbers.extend(re.findall(r'\b(\d{5,})\b', line))
            renewal_numbers.extend(re.findall(r'Application No\s+(\d{5,})', line))
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

# Extract numbers from PDF with chunked processing
def extract_numbers_from_pdf(pdf_file, progress_bar, chunk_size=50):
    extracted_data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []}
    try:
        logging.info(f"Processing uploaded PDF file: {pdf_file.name}")
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                raise ValueError("PDF file is empty")
            
            status_text = st.empty()
            processed_pages = 0
            
            for start in range(0, total_pages, chunk_size):
                end = min(start + chunk_size, total_pages)
                chunk_pages = pdf.pages[start:end]
                
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {executor.submit(process_page, page): i for i, page in enumerate(chunk_pages, start)}
                    
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            if result:
                                for key in extracted_data:
                                    extracted_data[key].extend(result[key])
                            processed_pages += 1
                            
                            progress_value = min(1.0, processed_pages / total_pages)
                            progress_bar.progress(progress_value)
                            status_text.markdown(f"✅ **Processed {processed_pages} of {total_pages} pages...**", unsafe_allow_html=True)
                        except Exception as e:
                            page_num = futures[future]
                            logging.error(f"Error processing page {page_num}: {str(e)}")

            logging.info(f"Completed processing {total_pages} pages")
            progress_bar.progress(1.0)
            status_text.markdown("✅ **Processing Completed!** 🎉", unsafe_allow_html=True)
            return extracted_data
    except Exception as e:
        st.error("❌ An error occurred while processing the PDF. Check the log file for details.")
        logging.error(f"Error processing PDF: {str(e)}")
        return None

# Save to Excel
def save_to_excel(data_dict):
    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for sheet_name, numbers in data_dict.items():
                if numbers:
                    cleaned_numbers = [int(num) for num in numbers if num.strip().isdigit()]
                    if cleaned_numbers:
                        df = pd.DataFrame(sorted(set(cleaned_numbers)), columns=["Numbers"])
                        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        output.seek(0)
        return output
    except Exception as e:
        st.error(f"❌ Error creating Excel file: {str(e)}")
        logging.error(f"Excel creation failed: {str(e)}")
        return None

# Streamlit app
def main():
    st.set_page_config(page_title="PDF Number Extractor", page_icon="📄", layout="wide")

    st.markdown("# INDIA TMJ")
    st.write("Extract numbers from PDF and download them as an Excel file.")

    if "processing_done" not in st.session_state:
        st.session_state.processing_done = False

    uploaded_file = st.file_uploader("Select a PDF file", type=["pdf"])

    if uploaded_file is not None:
        st.success(f"✅ Selected File: {uploaded_file.name}")

        if not st.session_state.processing_done:
            progress_bar = st.progress(0)
            with st.spinner("🔄 Processing PDF..."):
                extracted_data = extract_numbers_from_pdf(uploaded_file, progress_bar, chunk_size=50)

                if extracted_data and any(extracted_data.values()):
                    excel_file = save_to_excel(extracted_data)
                    if excel_file:
                        st.success("✅ Extraction Completed!")
                        output_file_name = st.text_input("📄 Enter output file name", "extracted_numbers.xlsx")
                        st.download_button("📥 Download Excel File", excel_file, output_file_name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            st.session_state.processing_done = True

    if st.button("🔄 Restart Processing"):
        st.session_state.processing_done = False
        st.rerun()

if __name__ == "__main__":
    main()
