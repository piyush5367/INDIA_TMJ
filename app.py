import streamlit as st
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

# Function to extract numbers using regex
def extract_numbers(text, pattern):
    return re.findall(pattern, text)

# Function to extract Advertisement numbers
def extract_advertisement_numbers(text):
    advertisement_numbers = []
    lines = text.split("\n")  

    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line:
            break
        matches = re.findall(r'(\d{5,})\s+\d{2}/\d{2}/\d{4}', line)
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
        if "Following Trade Mark applications have been Registered" in line:
            break
        if found_corrigenda_section:
            matches = re.findall(r'(\d{5,})\s*[-–]', line)
            corrigenda_numbers.extend(matches)
    
    return corrigenda_numbers

# Function to extract RC numbers
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

# Function to extract Renewal numbers
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
            renewal_numbers.extend(extract_numbers(line, r'\b(\d{5,})\b'))  
            renewal_numbers.extend(extract_numbers(line, r'Application No\s*\(?(\d{5,})\)?'))  
    
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

# Extract numbers from PDF with progress bar
def extract_numbers_from_pdf(pdf_file, progress_bar):
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
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(process_page, page): i for i, page in enumerate(pdf.pages)}
                
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
            return extracted_data
    except Exception as e:
        st.error("❌ An error occurred while processing the PDF. Check the log file for details.")
        logging.error(f"Error processing PDF: {str(e)}")
        return None

# Save extracted data to an Excel file
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

# Streamlit App UI
def main():
    st.set_page_config(page_title="PDF Number Extractor", page_icon="📄", layout="wide")

    # Custom Styling with Hover Effect
    st.markdown(
        """
        <style>
            .stProgress > div > div > div > div {
                border-radius: 10px;
            }
            .stButton > button {
                border-radius: 12px;
                background-color: #007BFF;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                transition: 0.3s;
            }
            .stButton > button:hover {
                background-color: #0056b3;
                transform: scale(1.05);
            }
        </style>
        """, unsafe_allow_html=True
    )

    st.markdown("<h1 style='text-align: center; color: cyan;'>INDIA TMJ - Trademark Extractor</h1>", unsafe_allow_html=True)
    st.write("Extract numbers from a **PDF** and download them as an **Excel** file.")
    
    uploaded_file = st.file_uploader("📂 **Upload a PDF file**", type=["pdf"])
    
    if uploaded_file is not None:
        st.success(f"✅ **Selected File:** `{uploaded_file.name}`")
        
        progress_bar = st.progress(0)
        with st.spinner("🔄 **Processing PDF... Please wait...**"):
            extracted_data = extract_numbers_from_pdf(uploaded_file, progress_bar)
            
            if extracted_data is None:
                st.error("❌ **Processing failed. Check the log file for details.**")
            elif not any(extracted_data.values()):
                st.warning("⚠️ **No matching numbers found in the PDF.**")
            else:
                excel_file = save_to_excel(extracted_data)
                if excel_file:
                    st.success("✅ **Extraction Completed Successfully!** 🎉")
                    output_file_name = st.text_input("📄 **Enter output file name**", "extracted_numbers.xlsx")
                    st.download_button(
                        label="📥 **Download Excel File**",
                        data=excel_file,
                        file_name=output_file_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help="Click to download the extracted data."
                    )
        
        progress_bar.empty()

if __name__ == "__main__":
    main()
