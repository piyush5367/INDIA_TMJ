import streamlit as st
import os
import re
import pdfplumber
import pandas as pd
import logging
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Set up logging
logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Precompile regex patterns
advertisement_pattern = re.compile(r'(\d{5,})\s+\d{2}/\d{2}/\d{4}')
corrigenda_pattern = re.compile(r'(\d{5,})\s*[ ]')
rc_pattern = re.compile(r'\b(\d{7})\b')
renewal_pattern_7_digits = re.compile(r'\b(\d{7})\b')  # Matches 7-digit numbers
renewal_pattern_application_no = re.compile(r'Application No\s*\((\d+)\)\s*Class')  # Matches "Application No (number) Class"

# Extraction functions
def extract_advertisement_numbers(text):
    return advertisement_pattern.findall(text)

def extract_corrigenda_numbers(text):
    return corrigenda_pattern.findall(text)

def extract_rc_numbers(text):
    return rc_pattern.findall(text)

def extract_renewal_numbers(text):
    # Extract 7-digit numbers
    renewal_7_digits = renewal_pattern_7_digits.findall(text)
    # Extract numbers in "Application No (number) Class" format
    renewal_application_no = renewal_pattern_application_no.findall(text)
    return {
        "7_Digit_Numbers": renewal_7_digits,
        "Application_No_Numbers": renewal_application_no,
    }

# Extract numbers from a single page
def process_page(page):
    text = page.extract_text()
    if not text:
        return None
    renewal_numbers = extract_renewal_numbers(text)
    return {
        "Advertisement": extract_advertisement_numbers(text),
        "Corrigenda": extract_corrigenda_numbers(text),
        "RC": extract_rc_numbers(text),
        "Renewal_7_Digit": renewal_numbers["7_Digit_Numbers"],
        "Renewal_Application_No": renewal_numbers["Application_No_Numbers"],
    }

# Extract numbers from PDF in parallel
def extract_numbers_from_pdf(pdf_file, progress_bar):
    extracted_data = {
        "Advertisement": [],
        "Corrigenda": [],
        "RC": [],
        "Renewal_7_Digit": [],
        "Renewal_Application_No": [],
    }
    try:
        logging.info(f"Processing uploaded PDF file")
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            with ThreadPoolExecutor(max_workers=4) as executor:  # Limit threads
                futures = {executor.submit(process_page, page): i for i, page in enumerate(pdf.pages)}
                
                results = [future.result() for future in as_completed(futures)]
                for i, result in enumerate(results):
                    if result:
                        for key in extracted_data:
                            extracted_data[key].extend(result[key])
                    
                    # Update progress bar every 10 pages
                    if (i + 1) % 10 == 0 or i == total_pages - 1:
                        progress_bar.progress((i + 1) / total_pages)
                        st.text(f"Processing page {i + 1} of {total_pages}...")
    except Exception as e:
        st.error("❌ An error occurred while processing the PDF. Please try again.")
        logging.error(f"Error processing PDF: {str(e)}")
        return None
    return extracted_data

# Function to save extracted numbers to Excel and return as a downloadable file
def save_to_excel(data_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, numbers in data_dict.items():
            if numbers:
                numbers = sorted(set(map(int, numbers)))
                df = pd.DataFrame(numbers, columns=["Numbers"])
                df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)
    return output

# Streamlit app
def main():
    st.set_page_config(page_title="PDF Number Extractor", page_icon="📄", layout="wide", initial_sidebar_state="expanded")
    
    # Header
    st.markdown(
        """
        <div style='background-color: #f0f2f6; padding: 10px; border-radius: 5px;'>
            <h1 style='text-align: center; color: #ff4b4b;'>INDIA TMJ</h1>
            <p style='text-align: center; font-size: 18px;'>Extract numbers from PDF and download them as an Excel file.</p>
        </div>
        <hr>
        """,
        unsafe_allow_html=True,
    )
    
    # Sidebar for File Upload
    with st.sidebar:
        st.markdown("## Welcome to India TMJ 📄")
        st.markdown(
            """
            This app helps you extract numbers from PDF files and download them as an Excel file.
            1. Upload a PDF file.
            2. Wait for the extraction process to complete.
            3. Download the results as an Excel file.
            """
        )
        st.markdown("### 📂 Upload File")
        uploaded_file = st.file_uploader("Select a PDF file", type=["pdf"], label_visibility="collapsed")
        
        theme = st.sidebar.radio("🌗 Select Theme", ["Light", "Dark"])
        if theme == "Dark":
            st.markdown(
                """
                <style>
                body { background-color: #121212; color: #ffffff; }
                .stButton>button { background-color: #333; color: white; }
                </style>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <style>
                body { background-color: #ffffff; color: #000000; }
                </style>
                """,
                unsafe_allow_html=True,
            )
        
    if uploaded_file is not None:
        st.success(f"✅ Selected File: {uploaded_file.name}")
        
        progress_bar = st.progress(0)
        with st.spinner("🔄 Processing PDF..."):
            extracted_data = extract_numbers_from_pdf(uploaded_file, progress_bar)
            
            if extracted_data is not None and any(extracted_data.values()):
                excel_file = save_to_excel(extracted_data)
                st.success("✅ Extraction Completed!")
                st.markdown("### 📊 Results")
                output_file_name = st.text_input("📄 Enter output file name", "extracted_numbers.xlsx")
                st.download_button(
                    label="📥 Download Excel File",
                    data=excel_file,
                    file_name=output_file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                st.experimental_rerun()
            elif extracted_data is not None:
                st.warning("⚠️ No matching numbers found in the PDF.")
        
        # Reset progress bar
        progress_bar.empty()
    
    if st.button("🔄 Reset"):
        st.experimental_rerun()
    
    # Footer
    st.markdown(
        """
        <hr>
        <p style='text-align: center; font-size: 12px; color: gray;'>Developed by Piyush</p>
        """,
        unsafe_allow_html=True,
    )

if __name__ == "__main__":
    main()
