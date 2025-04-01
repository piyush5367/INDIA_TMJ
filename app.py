import os
import re
import pdfplumber
import pandas as pd
import streamlit as st
import openpyxl
import logging
from io import BytesIO

# Configure logging
logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Function to extract numbers using regex
def extract_numbers(text, pattern):
    return list(map(int, re.findall(pattern, text)))

# Function to extract Advertisement numbers
def extract_advertisement_numbers(text):
    advertisement_numbers = []
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()  # Clean up the line
        
        if "CORRIGENDA" in line:
            break  # Stop if "CORRIGENDA" section is reached
        
        # Corrected regex extraction of advertisement numbers
        matches = re.findall(r' (\d{5,})\s+\d{2}/\d{2}/\d{4} ', line)  
        advertisement_numbers.extend(matches)  # Add found numbers to the list
    
    return advertisement_numbers  

# Function to extract Corrigenda numbers
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
            matches = re.findall(r' (\d{5,})\s*', line)
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

# Function to extract Renewal numbers
def extract_renewal_numbers(text):
    renewal_numbers = []
    found_renewal_section = False
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "Following Trade Marks Registration Renewed for a Period Of Ten Years" in line:
            found_renewal_section = True
            continue
        if found_renewal_section:
            renewal_numbers.extend(extract_numbers(line, r'\b(\d{5,})\b'))
            renewal_numbers.extend(extract_numbers(line, r'Application No\s+(\d{5,}) '))
    return renewal_numbers

# Optimized PDF extraction with progress feedback
def extract_numbers_from_pdf(pdf_file):
    extracted_data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []}
    try:
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                st.warning("PDF is empty.")
                return extracted_data
            progress_bar = st.progress(0)
            chunk_size = 10
            for start in range(0, total_pages, chunk_size):
                end = min(start + chunk_size, total_pages)
                for i in range(start, end):
                    page = pdf.pages[i]
                    text = page.extract_text() or ""  # Handle None case
                    extracted_data["Advertisement"].extend(extract_advertisement_numbers(text))
                    extracted_data["Corrigenda"].extend(extract_corrigenda_numbers(text))
                    extracted_data["RC"].extend(extract_rc_numbers(text))
                    extracted_data["Renewal"].extend(extract_renewal_numbers(text))
                    progress_bar.progress((i + 1) / total_pages)
    except Exception as e:
        st.error(f"Failed to process PDF: {str(e)}")
        logging.error(f"PDF processing error: {str(e)}")
    return extracted_data

# Optimized Excel saving
def save_to_excel(data_dict):
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for sheet_name, numbers in data_dict.items():
                if numbers:
                    numbers = sorted(set(map(int, numbers)))
                    df = pd.DataFrame(numbers, columns=["Numbers"])
                    df.to_excel(writer, index=False, sheet_name=sheet_name)
        output.seek(0)
        return output.getvalue() if any(data_dict.values()) else None
    except Exception as e:
        st.error(f"Failed to create Excel file: {str(e)}")
        logging.error(f"Excel creation error: {str(e)}")
        return None

# Streamlit app with optimizations
def main():
    st.title("INDIA TMJ")

    # Initialize session state
    if "extracted_data" not in st.session_state:
        st.session_state.extracted_data = None
    if "excel_data" not in st.session_state:
        st.session_state.excel_data = None
    if "file_name" not in st.session_state:
        st.session_state.file_name = None

    # File uploader
    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"], key="pdf_uploader")

    if uploaded_file is not None:
        file_name = uploaded_file.name
        st.write(f"Selected file: {file_name}")

        # Process button
        if st.button("Extract Numbers") or (st.session_state.file_name != file_name):
            st.session_state.file_name = file_name
            with st.spinner("Processing PDF..."):
                st.session_state.extracted_data = extract_numbers_from_pdf(uploaded_file)
                st.session_state.excel_data = save_to_excel(st.session_state.extracted_data)

        # Display results if available
        if st.session_state.extracted_data is not None:
            if st.session_state.excel_data:
                st.success("Extraction completed successfully!")
                
                # Preview extracted data
                st.subheader("Extracted Numbers Preview:")
                for category, numbers in st.session_state.extracted_data.items():
                    if numbers:
                        st.write(f"{category}: {len(numbers)} numbers found")
                        df = pd.DataFrame(sorted(set(map(int, numbers))), columns=["Numbers"])
                        st.dataframe(df, height=200)

                # Download button
                st.download_button(
                    label="Download Excel File",
                    data=st.session_state.excel_data,
                    file_name=f"extracted_numbers_{file_name.split('.')[0]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_button"
                )
            else:
                st.warning("No numbers found matching the specified patterns.")

if __name__ == "__main__":
    main()
