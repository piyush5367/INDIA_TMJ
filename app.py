import streamlit as st
import re
import pdfplumber
import pandas as pd
import logging
from io import BytesIO
from typing import Dict, List

# Configure logging
logging.basicConfig(
    filename="pdf_extraction.log", 
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def extract_advertisement_numbers(text: str) -> List[str]:
    """Extract advertisement numbers from text."""
    advertisement_numbers = []
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line.upper():  # Stop when Corrigenda section starts
            break
        # More precise pattern matching
        matches = re.findall(r'(?:^|\s)(\d{5,})\s+\d{2}/\d{2}/\d{4}(?:\s|$)', line)
        advertisement_numbers.extend(matches)
    
    return advertisement_numbers

def extract_corrigenda_numbers(text: str) -> List[str]:
    """Extract corrigenda numbers from text."""
    corrigenda_numbers = []
    in_corrigenda_section = False
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        upper_line = line.upper()
        
        if "CORRIGENDA" in upper_line:
            in_corrigenda_section = True
            continue
        if "FOLLOWING TRADE MARK APPLICATIONS HAVE BEEN REGISTERED" in upper_line:
            break
        if in_corrigenda_section:
            # More robust pattern that handles various spacings
            matches = re.findall(r'(?:^|\s)(\d{5,})(?:\s|$)', line)
            corrigenda_numbers.extend(matches)
    
    return corrigenda_numbers

def extract_rc_numbers(text: str) -> List[str]:
    """Extract RC numbers from text."""
    rc_numbers = []
    in_rc_section = False
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        upper_line = line.upper()
        
        if "FOLLOWING TRADE MARKS REGISTRATION RENEWED FOR A PERIOD OF TEN YEARS" in upper_line:
            in_rc_section = True
            continue
            
        if in_rc_section:
            # Skip lines that might be section headers
            if any(word in upper_line for word in ["PAGE", "SECTION", "VOLUME"]):
                continue
            # Extract all 5+ digit numbers in this section
            matches = re.findall(r'\b\d{5,}\b', line)
            rc_numbers.extend(matches)
    
    return rc_numbers

def extract_renewal_numbers(text: str) -> List[str]:
    """Extract renewal numbers from text."""
    renewal_numbers = []
    in_renewal_section = False
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        upper_line = line.upper()
        
        if "FOLLOWING TRADE MARKS REGISTRATION RENEWED FOR A PERIOD OF TEN YEARS" in upper_line:
            in_renewal_section = True
            continue
        if in_renewal_section:
            # Skip lines that might be section headers
            if any(word in upper_line for word in ["PAGE", "SECTION", "VOLUME"]):
                continue
            matches = re.findall(r'\b\d{5,}\b', line)
            renewal_numbers.extend(matches)
    
    return renewal_numbers

def extract_numbers_from_pdf(pdf_file) -> Dict[str, List[str]]:
    """Main function to extract numbers from PDF."""
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
            full_text = ""
            
            # First pass: accumulate all text for context
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"
                progress_bar.progress((i + 1) / total_pages)
            
            progress_bar.empty()
            
            # Extract from full text
            extracted_data["Advertisement"] = extract_advertisement_numbers(full_text)
            extracted_data["Corrigenda"] = extract_corrigenda_numbers(full_text)
            extracted_data["RC"] = extract_rc_numbers(full_text)
            extracted_data["Renewal"] = extract_renewal_numbers(full_text)
            
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        logging.error(f"Error processing {pdf_file.name}: {str(e)}", exc_info=True)
        
    return extracted_data

def create_excel_file(data_dict: Dict[str, List[str]]) -> BytesIO:
    """Create Excel file in memory from extracted data."""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, numbers in data_dict.items():
            if numbers:
                # Remove duplicates and sort
                unique_numbers = sorted({int(num) for num in numbers if num.isdigit()})
                df = pd.DataFrame(unique_numbers, columns=["Numbers"])
                df.to_excel(
                    writer, 
                    index=False, 
                    sheet_name=sheet_name[:31]  # Excel sheet name limit
                )
    
    output.seek(0)
    return output

def validate_pdf(file) -> bool:
    """Basic validation to check if the PDF might be a TMJ file."""
    try:
        with pdfplumber.open(file) as pdf:
            first_page = pdf.pages[0].extract_text() or ""
            return any(
                keyword in first_page.upper() 
                for keyword in ["TRADE MARK", "JOURNAL", "ADVERTISEMENT", "CORRIGENDA"]
            )
    except:
        return False

def main():
    """Streamlit UI and main application logic."""
    st.set_page_config(
        page_title="TMJ PDF Extractor",
        page_icon="📄",
        layout="centered"
    )
    
    st.title("India TMJ PDF Extractor")

    uploaded_file = st.file_uploader(
        "Upload a Trade Marks Journal PDF file", 
        type="pdf",
        help="Upload a PDF file from the India Trade Marks Journal"
    )
    
    if uploaded_file is not None:
        if not validate_pdf(uploaded_file):
            st.warning("This doesn't appear to be a valid Trade Marks Journal PDF. Continue at your own risk.")
        
        if st.button("Extract Numbers", type="primary"):
            with st.spinner("Processing PDF... This may take a few moments for large files."):
                extracted_data = extract_numbers_from_pdf(uploaded_file)
                
                if not any(extracted_data.values()):
                    st.warning("No matching numbers found in the PDF.")
                    return
                
                st.success("Extraction completed!")
                
                # Show summary
                st.subheader("📊 Extraction Summary")
                cols = st.columns(4)
                metrics = {
                    "Advertisement": "📢",
                    "Corrigenda": "✏️",
                    "RC": "📄",
                    "Renewal": "🔄"
                }
                
                for i, (category, numbers) in enumerate(extracted_data.items()):
                    unique_count = len(set(numbers)) if numbers else 0
                    cols[i].metric(
                        label=f"{metrics[category]} {category}",
                        value=unique_count
                    )
                
                # Create and download Excel file
                excel_file = create_excel_file(extracted_data)
                st.download_button(
                    label="⬇️ Download Excel File",
                    data=excel_file,
                    file_name=f"TMJ_Numbers_{uploaded_file.name[:20]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="Download the extracted numbers in Excel format"
                )
                
                # Show raw data in expandable sections
                with st.expander("🔍 View Extracted Numbers Details"):
                    for category, numbers in extracted_data.items():
                        if numbers:
                            unique_numbers = sorted({int(num) for num in numbers})
                            st.write(f"#### {category} ({len(unique_numbers)} unique)")
                            st.code("\n".join(map(str, unique_numbers)), language="text")

if __name__ == "__main__":
    main()
