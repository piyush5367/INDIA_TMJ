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

# Helper function to extract numbers based on regex
def extract_numbers(text, pattern):
    return re.findall(pattern, text)

# Function to extract Advertisement numbers
def extract_advertisement_numbers(text):
    advertisement_numbers = []
    lines = text.split("\n")  # Split text into lines

    for line in lines:
        line = line.strip()  # Remove extra spaces
        
        if "CORRIGENDA" in line:  # Stop when Corrigenda section starts
            break
        
        matches = extract_numbers(line, r'(\d{5,})\s+\d{2}/\d{2}/\d{4}')  # Extracting numbers
        advertisement_numbers.extend(matches)
    
    return advertisement_numbers

# Function to extract Corrigenda numbers
def extract_corrigenda_numbers(text):
    corrigenda_numbers = []
    found_corrigenda_section = False
    lines = text.split("\n")  # Split text into lines

    for line in lines:
        line = line.strip()  # Remove extra spaces

        if "CORRIGENDA" in line:  # Start extraction from Corrigenda section
            found_corrigenda_section = True
            continue

        if "Following Trade Mark applications have been Registered and registration certificates are available on the official website" in line:
            break  # Stop extraction when RC section starts

        if found_corrigenda_section:
            matches = extract_numbers(line, r'(\d{5,})\s*[-–]')  # Extract numbers followed by "-"
            corrigenda_numbers.extend(matches)

    return corrigenda_numbers

# Function to extract RC numbers
def extract_rc_numbers(text):
    rc_numbers = []
    lines = text.split("\n")  # Split text into lines

    for line in lines:
        line = line.strip()  # Remove extra spaces

        if "Following Trade Marks Registration Renewed for a Period Of Ten Years" in line:
            break  # Stop extraction when Renewal section starts

        columns = line.split()  # Splitting the line into words

        if len(columns) == 5 and all(col.isdigit() for col in columns):  # Check if the line contains exactly 5 numeric columns
            rc_numbers.extend(columns)  # Add extracted numbers

    return rc_numbers

# Function to extract Renewal numbers
def extract_renewal_numbers(text):
    renewal_numbers = []
    found_renewal_section = False
    lines = text.split("\n")  # Split text into lines

    for line in lines:
        line = line.strip()  # Remove extra spaces
        
        if "Following Trade Marks Registration Renewed for a Period Of Ten Years" in line:
            found_renewal_section = True
            continue  # Start extraction after this line
        
        if found_renewal_section:
            renewal_numbers.extend(extract_numbers(line, r'\b(\d{5,})\b'))  # Extracting general 5+ digit numbers
            renewal_numbers.extend(extract_numbers(line, r'Application No\s+(\d{5,})'))  # Extracting application numbers
    
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
    extracted_data = {
        "Advertisement": [],
        "Corrigenda": [],
        "RC": [],
        "Renewal": [],
    }
    try:
        logging.info(f"Processing uploaded PDF file: {pdf_file.name}")
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                raise ValueError("PDF file is empty")
            
            status_text = st.empty()
            processed_pages = 0
            
            # Process pages in chunks
            for start in range(0, total_pages, chunk_size):
                end = min(start + chunk_size, total_pages)
                chunk_pages = pdf.pages[start:end]
                
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {executor.submit(process_page, page): i for i, page in enumerate(chunk_pages, start)}
                    
                    # Collect results for this chunk
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            if result:
                                for key in extracted_data:
                                    extracted_data[key].extend(result[key])
                            processed_pages += 1
                            
                            # Update progress
                            progress_value = min(1.0, processed_pages / total_pages)
                            progress_bar.progress(progress_value)
                            status_text.text(f"Processed {processed_pages} of {total_pages} pages...")
                        except Exception as e:
                            page_num = futures[future]
                            logging.error(f"Error processing page {page_num}: {str(e)}")
            
            logging.info(f"Completed processing {total_pages} pages")
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
    
    uploaded_file = st.file_uploader("Select a PDF file", type=["pdf"])
    
    if uploaded_file is not None:
        st.success(f"✅ Selected File: {uploaded_file.name}")
        
        progress_bar = st.progress(0)
        with st.spinner("🔄 Processing PDF..."):
            extracted_data = extract_numbers_from_pdf(uploaded_file, progress_bar, chunk_size=50)
            
            if extracted_data is None:
                st.error("❌ Processing failed. Check the log file for details.")
            elif not any(extracted_data.values()):
                st.warning("⚠️ No matching numbers found in the PDF.")
            else:
                excel_file = save_to_excel(extracted_data)
                if excel_file:
                    st.success("✅ Extraction Completed!")
                    output_file_name = st.text_input("📄 Enter output file name", "extracted_numbers.xlsx")
                    st.download_button(
                        label="📥 Download Excel File",
                        data=excel_file,
                        file_name=output_file_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
        
        progress_bar.empty()

if __name__ == "__main__":
    main()
