import streamlit as st
import os
import re
import pdfplumber
import pandas as pd
import logging
from io import BytesIO

# Set up logging
logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Function to extract numbers using regex
def extract_numbers(text, pattern):
    return list(map(int, re.findall(pattern, text)))

# Function to extract advertisement numbers
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

# Function to extract corrigenda numbers
def extract_corrigenda_numbers(text):
    corrigenda_numbers = []
    found_corrigenda_section = False
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line:
            found_corrigenda_section = True
            continue
        if "Following Trade Mark applications have been Registered and registration certificates are available on the official website" in line:
            break
        if found_corrigenda_section:
            matches = re.findall(r'(\d{5,})\s*[ ]', line)
            corrigenda_numbers.extend(matches)
    return corrigenda_numbers

# Function to extract RC numbers
def extract_rc_numbers(text):
    rc_numbers = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "Following Trade Marks Registration Renewed for a Period Of Ten Years" in line:
            break
        columns = line.split()
        if len(columns) == 5 and all(col.isdigit() for col in columns):
            rc_numbers.extend(columns)
    return rc_numbers

# Function to extract renewal numbers (Only 7-digit numbers)
def extract_renewal_numbers(text):
    renewal_numbers = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        matches = re.findall(r'\b(\d{7})\b', line)  # Extract only 7-digit numbers
        renewal_numbers.extend(matches)
    return renewal_numbers

# Function to extract numbers from PDF
def extract_numbers_from_pdf(pdf_file, progress_bar):
    extracted_data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []}
    try:
        logging.info(f"Processing uploaded PDF file")
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    extracted_data["Advertisement"].extend(extract_advertisement_numbers(text))
                    extracted_data["Corrigenda"].extend(extract_corrigenda_numbers(text))
                    extracted_data["RC"].extend(extract_rc_numbers(text))
                    extracted_data["Renewal"].extend(extract_renewal_numbers(text))
                progress_bar.progress((i + 1) / total_pages)
    except Exception as e:
        logging.error(f"Error processing PDF: {str(e)}")
        st.error(f"An unexpected error occurred while processing the PDF: {str(e)}")
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
    st.set_page_config(page_title="PDF Number Extractor", page_icon="📄", layout="wide")
    
    # Header
    st.markdown("""
        <h1 style='text-align: center; color: #ff4b4b;'>INDIA TMJ</h1>
        <p style='text-align: center; font-size: 18px;'>Extract numbers from PDF and download them as an Excel file.</p>
        <hr>
    """, unsafe_allow_html=True)
    
    # File uploader
    uploaded_file = st.file_uploader("📂 Select a PDF file", type=["pdf"], label_visibility="collapsed")
    
    if uploaded_file is not None:
        st.success(f"✅ Selected File: {uploaded_file.name}")
        
        progress_bar = st.progress(0)
        with st.spinner("🔄 Processing PDF..."):
            extracted_data = extract_numbers_from_pdf(uploaded_file, progress_bar)
            
            if extracted_data is not None and any(extracted_data.values()):
                excel_file = save_to_excel(extracted_data)
                st.success("✅ Extraction Completed!")
                st.download_button(
                    label="📥 Download Excel File",
                    data=excel_file,
                    file_name="extracted_numbers.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="Click to download extracted numbers"
                )
            elif extracted_data is not None:
                st.warning("⚠️ No matching numbers found in the PDF.")
    
    # Footer
    st.markdown("""
        <hr>
        <p style='text-align: center; font-size: 12px; color: gray;'>Developed by Piyush</p>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
