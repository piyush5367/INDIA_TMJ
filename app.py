import re
import pdfplumber
import pandas as pd
import streamlit as st
import logging
from io import BytesIO
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, 
                   format="%(asctime)s - %(message)s")

class TMJNumberExtractor:
    """Extracts numbers from Trade Marks Journal PDFs"""
    
    def __init__(self):
        # Configure section markers (case insensitive)
        self.section_markers = {
            'corrigenda': 'CORRIGENDA',
            'renewal': 'FOLLOWING TRADE MARKS REGISTRATION RENEWED',
            'registered': 'FOLLOWING TRADE MARK APPLICATIONS HAVE BEEN REGISTERED',
            'pr_section': 'PR SECTION'
        }
        
        # Configure patterns
        self.patterns = {
            'advertisement': r'(\d{5,})\s+\d{2}/\d{2}/\d{4}',
            'corrigenda': r'(\d{5,})',
            'rc': r'\b\d{5,}\b',
            'renewal': [
                r'\b(\d{5,})\b',
                r'Application No\s+(\d{5,})'
            ],
            'pr_section': r'(\d{5,})\s*-'
        }
        
        # Validation rules
        self.min_number_length = 5
        self.max_number_length = 7
        
        # Configure logging
        self.logger = logging.getLogger(__name__)

    def _clean_number(self, number: str) -> str:
        """Remove commas and whitespace from numbers"""
        return number.replace(',', '').strip()

    def _validate_number(self, number: str) -> bool:
        """Validate extracted number meets criteria"""
        clean_num = self._clean_number(number)
        if not isinstance(clean_num, str):
            return False
        return (clean_num.isdigit() and 
                self.min_number_length <= len(clean_num) <= self.max_number_length)

    def _remove_duplicates(self, numbers: List[str]) -> List[str]:
        """Remove duplicates while preserving order"""
        seen = set()
        return [n for n in numbers if not (n in seen or seen.add(n))]

    def extract_numbers(self, text: str, pattern: str) -> List[str]:
        """Generic number extractor with validation"""
        if not text or not isinstance(text, str):
            return []
            
        try:
            matches = re.findall(pattern, text)
            return [self._clean_number(m) for m in matches if self._validate_number(m)]
        except Exception as e:
            self.logger.error(f"Regex error with pattern {pattern}: {e}")
            return []

    def extract_advertisement_numbers(self, text: str) -> List[str]:
        """Extract advertisement numbers before corrigenda section"""
        if not text:
            return []

        numbers = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if self.section_markers['corrigenda'].upper() in line.upper():
                break
            numbers.extend(self.extract_numbers(line, self.patterns['advertisement']))
            
        return self._remove_duplicates(numbers)

    def extract_corrigenda_numbers(self, text: str) -> List[str]:
        """Extract corrigenda numbers between corrigenda and registered sections"""
        if not text:
            return []

        numbers = []
        in_section = False
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            upper_line = line.upper()
            
            if self.section_markers['corrigenda'].upper() in upper_line:
                in_section = True
                continue
                
            if self.section_markers['registered'].upper() in upper_line:
                break
                
            if in_section:
                numbers.extend(self.extract_numbers(line, self.patterns['corrigenda']))
                
        return self._remove_duplicates(numbers)

    def extract_rc_numbers(self, text: str) -> List[str]:
        """Extract RC numbers before renewal section - Original logic with comma handling"""
        if not text:
            return []

        numbers = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if self.section_markers['renewal'].upper() in line.upper():
                break
                
            # Original RC extraction logic with comma handling
            columns = line.split()
            if len(columns) == 5:
                valid_numbers = []
                for col in columns:
                    clean_num = self._clean_number(col)
                    if clean_num.isdigit() and len(clean_num) >= 5:
                        valid_numbers.append(clean_num)
                if len(valid_numbers) == 5:  # All 5 columns valid
                    numbers.extend(valid_numbers)
                    
        return self._remove_duplicates(numbers)

    def extract_renewal_numbers(self, text: str) -> List[str]:
        """Extract renewal numbers after renewal section header"""
        if not text:
            return []

        numbers = []
        in_section = False
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if self.section_markers['renewal'].upper() in line.upper():
                in_section = True
                continue
                
            if in_section:
                for pattern in self.patterns['renewal']:
                    numbers.extend(self.extract_numbers(line, pattern))
                    
        return self._remove_duplicates(numbers)

    def extract_pr_section_numbers(self, text: str) -> List[str]:
        """Extract PR Section numbers (format: '123456 -') from text"""
        if not text:
            return []

        numbers = []
        in_section = False
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            upper_line = line.upper()
            
            if self.section_markers['pr_section'].upper() in upper_line:
                in_section = True
                continue
                
            if in_section:
                matches = self.extract_numbers(line, self.patterns['pr_section'])
                numbers.extend(matches)
                
        return self._remove_duplicates(numbers)

    def process_pdf(self, pdf_file) -> Dict[str, List[str]]:
        """Process PDF and return all extracted numbers"""
        extracted_data = {
            'advertisement': [],
            'corrigenda': [],
            'rc': [],
            'renewal': [],
            'pr_section': []
        }
        
        if not pdf_file:
            st.error("No file uploaded.")
            return extracted_data

        try:
            with pdfplumber.open(pdf_file) as pdf:
                total_pages = len(pdf.pages)
                if total_pages == 0:
                    st.warning("PDF is empty.")
                    return extracted_data

                progress_bar = st.progress(0)
                for i, page in enumerate(pdf.pages):
                    try:
                        text = page.extract_text() or ""
                        extracted_data['advertisement'].extend(self.extract_advertisement_numbers(text))
                        extracted_data['corrigenda'].extend(self.extract_corrigenda_numbers(text))
                        extracted_data['rc'].extend(self.extract_rc_numbers(text))
                        extracted_data['renewal'].extend(self.extract_renewal_numbers(text))
                        extracted_data['pr_section'].extend(self.extract_pr_section_numbers(text))
                        progress_bar.progress((i + 1) / total_pages)
                    except Exception as e:
                        logging.error(f"Page {i+1} processing error: {e}")
                        continue
        except Exception as e:
            st.error(f"Failed to process PDF: {e}")
            logging.error(f"PDF processing error: {e}")
        
        # Deduplicate across all pages
        for key in extracted_data:
            extracted_data[key] = self._remove_duplicates(extracted_data[key])
            
        return extracted_data

def save_to_excel(data_dict: Dict[str, List[str]]) -> Optional[bytes]:
    """Generate Excel file from extracted data"""
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for sheet_name, numbers in data_dict.items():
                if numbers:
                    try:
                        # Convert to integers after cleaning
                        clean_numbers = [int(n) for n in numbers if n.isdigit()]
                        df = pd.DataFrame(sorted(set(clean_numbers)), columns=["Numbers"])
                        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
                    except Exception as e:
                        logging.error(f"Error writing {sheet_name} to Excel: {e}")
                        continue
        output.seek(0)
        return output.getvalue()
    except Exception as e:
        st.error(f"Failed to create Excel file: {e}")
        logging.error(f"Excel error: {e}")
        return None

def main():
    """Streamlit application"""
    try:
        st.set_page_config(page_title="INDIA TMJ Extractor", layout="wide")
        st.title("INDIA Trade Marks Journal Number Extractor")
        
        # File upload
        uploaded_file = st.file_uploader("Upload PDF", type=["pdf"], 
                                       help="Upload Trade Marks Journal PDF")
        
        if uploaded_file is not None:
            st.write(f"Processing: **{uploaded_file.name}**")
            
            # Initialize extractor
            extractor = TMJNumberExtractor()
            
            with st.spinner("Extracting numbers from PDF..."):
                extracted_data = extractor.process_pdf(uploaded_file)
                excel_data = save_to_excel(extracted_data)
            
            if any(extracted_data.values()):
                st.success("Extraction completed successfully!")
                
                # Display results in tabs
                tabs = st.tabs(list(extracted_data.keys()))
                for tab, (category, numbers) in zip(tabs, extracted_data.items()):
                    with tab:
                        if numbers:
                            st.write(f"Found {len(numbers)} {category} numbers")
                            try:
                                # Display as integers
                                clean_numbers = [int(n) for n in numbers if n.isdigit()]
                                df = pd.DataFrame(sorted(set(clean_numbers)), 
                                                columns=["Numbers"])
                                st.dataframe(df, use_container_width=True, height=300)
                            except Exception as e:
                                st.warning(f"Error displaying {category} data: {e}")
                        else:
                            st.info(f"No {category} numbers found.")
                
                # Download button
                if excel_data:
                    st.download_button(
                        label="📥 Download Excel File",
                        data=excel_data,
                        file_name=f"tmj_numbers_{uploaded_file.name.split('.')[0]}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.warning("No numbers extracted from the PDF.")
                
    except Exception as e:
        st.error(f"Application error: {e}")
        logging.error(f"Application error: {e}")

if __name__ == "__main__":
    main()
