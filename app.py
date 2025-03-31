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
        line = line.strip()
        if "CORRIGENDA" in line:  # Stop when Corrigenda section starts
            break
        matches = re.findall(r' (\d{5,})\s+\d{2}/\d{2}/\d{4} ', line)
        advertisement_numbers.extend(matches)
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
            matches = re.findall(r' (\d{5,})\s*[ ]', line)
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
            renewal_numbers.extend(extract_numbers(line, r' \b(\d{5j})\b'))
            renewal_numbers.extend(extract_numbers(line, r'Application No\s+(\d{5,}) '))
    return renewal_numbers

# Modify the extract_numbers_from_pdf function to process pages in chunks
def extract_numbers_from_pdf(pdf_file):
    extracted_data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []}
    try:
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            chunk_size = 10  # Process 10 pages at a time
            for start in range(0, total_pages, chunk_size):
                end = min(start + chunk_size, total_pages)
                for i in range(start, end):
                    page = pdf.pages[i]
                    text = page.extract_text()
                    if not text:
                        continue
                    extracted_data["Advertisement"].extend(extract_advertisement_numbers(text))
                    extracted_data["Corrigenda"].extend(extract_corrigenda_numbers(text))
                    extracted_data["RC"].extend(extract_rc_numbers(text))
                    extracted_data["Renewal"].extend(extract_renewal_numbers(text))
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
    return extracted_data

# Function to save extracted numbers to an Excel file
def save_to_excel(data_dict):
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for sheet_name, numbers in data_dict.items():
                if numbers:
                    numbers = sorted(set(map(int, numbers)))
                    df = pd.DataFrame(numbers, columns=["Numbers"])
                    df.to_excel(writer, index=False, sheet_name=sheet_name)
        
        if any(data_dict.values()):
            output.seek(0)
            return output
        else:
            st.warning("No matching numbers found.")
            return None
    except Exception as e:
        st.error(f"Error saving to Excel: {str(e)}")
        return None

# Main Streamlit app
def main():
    st.title("PDF Number Extractor")
    st.write("Upload a PDF file to extract numbers into an Excel file")
    
    # File uploader
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    
    if uploaded_file is not None:
        st.write(f"Processing file: {uploaded_file.name}")
        
        # Process the PDF
        with st.spinner("Extracting numbers..."):
            extracted_data = extract_numbers_from_pdf(uploaded_file)
            excel_file = save_to_excel(extracted_data)
        
        if excel_file:
            st.success("Extraction Completed!")
            # Provide download button
            st.download_button(
                label="Download Excel File",
                data=excel_file,
                file_name=f"extracted_numbers_{uploaded_file.name.split('.')[0]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # Display summary
            st.write("Extracted Numbers Summary:")
            for category, numbers in extracted_data.items():
                st.write(f"{category}: {len(numbers)} numbers found")

if __name__ == "__main__":
    main()
