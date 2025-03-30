import streamlit as st
import os
import re
import pdfplumber
import pandas as pd
import logging
from io import BytesIO

# Configure logging
logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, format="%(asctime)s - %(message)s")

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
        if "CORRIGENDA" in line.upper():  # Case-insensitive check
            found_corrigenda_section = True
            continue
        if "Following Trade Mark applications have been Registered" in line:
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

# Function to extract renewal numbers
def extract_renewal_numbers(text):
    renewal_numbers = []
    renewal_section = False
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        
        if "Following Trade Marks Registration Renewed for a Period Of Ten Years" in line:
            renewal_section = True
            continue
            
        if renewal_section:
            matches = re.findall(r'\b\d{5,}\b', line)
            renewal_numbers.extend(matches)
            
    return renewal_numbers

# Main extraction function
def extract_numbers_from_pdf(pdf_file):
    extracted_data = {
        "Advertisement": [], 
        "Corrigenda": [], 
        "RC": [], 
        "Renewal": []
    }
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            progress_bar = st.progress(0)
            total_pages = len(pdf.pages)
            
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue
                
                extracted_data["Advertisement"].extend(extract_advertisement_numbers(text))
                extracted_data["Corrigenda"].extend(extract_corrigenda_numbers(text))
                extracted_data["RC"].extend(extract_rc_numbers(text))
                extracted_data["Renewal"].extend(extract_renewal_numbers(text))
                
                progress_bar.progress((i + 1) / total_pages)
                
            progress_bar.empty()
            
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        logging.error(f"Error processing PDF: {str(e)}")
        
    return extracted_data

# Function to create Excel file in memory
def create_excel_file(data_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, numbers in data_dict.items():
            if numbers:
                numbers = sorted(set(map(int, numbers)))
                df = pd.DataFrame(numbers, columns=["Numbers"])
                df.to_excel(writer, index=False, sheet_name=sheet_name[:31])  # Excel sheet name limit
    output.seek(0)
    return output

# Streamlit UI
def main():
    st.set_page_config(
        page_title="PDF Number Extractor",
        page_icon="📄",
        layout="centered"
    )
    
    st.title("INDIA TMJ PDF Extractor")
    st.markdown("Extract numbers from PDF and save them to Excel.")
    
    uploaded_file = st.file_uploader("Upload PDF file", type="pdf")
    
    if uploaded_file is not None:
        st.success(f"File uploaded: {uploaded_file.name}")
        
        if st.button("Extract Numbers"):
            with st.spinner("Processing PDF..."):
                extracted_data = extract_numbers_from_pdf(uploaded_file)
                
                if any(extracted_data.values()):
                    st.success("Extraction completed!")
                    
                    # Show summary
                    st.subheader("Extracted Numbers Summary")
                    cols = st.columns(4)
                    for i, (category, numbers) in enumerate(extracted_data.items()):
                        cols[i].metric(
                            label=category,
                            value=len(set(numbers)) if numbers else 0
                        )
                    
                    # Create and download Excel file
                    excel_file = create_excel_file(extracted_data)
                    st.download_button(
                        label="Download Excel File",
                        data=excel_file,
                        file_name="Extracted_Numbers.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                    # Show raw data
                    with st.expander("View Extracted Numbers"):
                        for category, numbers in extracted_data.items():
                            if numbers:
                                st.write(f"**{category}** ({len(set(numbers))} unique numbers):")
                                st.write(sorted(set(map(int, numbers))))
                else:
                    st.warning("No matching numbers found in the PDF.")

if __name__ == "__main__":
    main()
