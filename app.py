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
        self.max_number_length = None 
        
        # Configure logging
        self.logger = logging.getLogger(__name__)

    def _clean_number(self, number: str) -> str:
        """Clean extracted number by removing non-digit characters"""
        if not isinstance(number, str):
            return ""
        return re.sub(r"[^\d]", "", number)

    def _validate_number(self, number: str) -> bool:
        """Validate extracted number meets criteria"""
        clean_num = self._clean_number(number)
        if not clean_num:
            return False
        return (clean_num.isdigit() and 
                len(clean_num) >= self.min_number_length and
                (self.max_number_length is None or len(clean_num) <= self.max_number_length))

    def _remove_duplicates(self, numbers: List[str]) -> List[str]:
        """Remove duplicates while preserving order"""
        seen = set()
        return [n for n in numbers if not (n in seen or seen.add(n))]

    def extract_numbers(self, text: str, pattern: str) -> List[str]:
        """Generic number extractor with validation"""
        if not text or not isinstance(text, str):
            return []
        matches = re.findall(pattern, text)
        return [m for m in matches if self._validate_number(m)]

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
        found_corrigenda_section = False
        lines = text.split("\n")
        
        for line in lines:
            line = line.strip()
            if self.section_markers['corrigenda'].upper() in line.upper():
                found_corrigenda_section = True
                continue
                
            if self.section_markers['registered'].upper() in line.upper():
                break
                
            if found_corrigenda_section:
                matches = re.findall(r'(\d{5,})\s*[ ]', line)
                numbers.extend(matches)
                
        return self._remove_duplicates(numbers)

    def extract_rc_numbers(self, text: str) -> List[str]:
        """Extract RC numbers before renewal section"""
        if not text:
            return []

        numbers = []
        lines = text.split("\n")
        
        for line in lines:
            line = line.strip()
            if self.section_markers['renewal'].upper() in line.upper():
                break
                
            columns = line.split()
            if len(columns) == 5 and all(col.isdigit() for col in columns):
                numbers.extend(columns)
                
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
            return extracted_data

        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                return extracted_data

            progress_bar = st.progress(0)
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                extracted_data['advertisement'].extend(self.extract_advertisement_numbers(text))
                extracted_data['corrigenda'].extend(self.extract_corrigenda_numbers(text))
                extracted_data['rc'].extend(self.extract_rc_numbers(text))
                extracted_data['renewal'].extend(self.extract_renewal_numbers(text))
                extracted_data['pr_section'].extend(self.extract_pr_section_numbers(text))
                progress_bar.progress((i + 1) / total_pages)

        for key in extracted_data:
            extracted_data[key] = self._remove_duplicates(extracted_data[key])
            
        return extracted_data

    def save_to_excel(self, data_dict: Dict[str, List[str]]) -> Optional[bytes]:
        """Generate Excel file from extracted data"""
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for sheet_name, numbers in data_dict.items():
                if numbers:
                    clean_numbers = [int(self._clean_number(n)) for n in numbers]
                    df = pd.DataFrame(sorted(set(clean_numbers)), columns=["Numbers"])
                    df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        output.seek(0)
        return output.getvalue()

def main():
    """Streamlit application"""
    st.set_page_config(page_title="Number Extractor")

    # Apply custom styling with black background
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Zen+Antique+Soft&display=swap');

        /* Set black background for the entire app */
        body {
            background-color: #00008B;
            color: #FFFFFF;
        }
        .stApp {
            background-color: #00008B;
            color: #FFFFFF;
        }

        .custom-title {
            font-family: 'Zen Antique Soft', serif;
            text-align: center;
            font-size: 3em;
            font-weight: bold;
            background: linear-gradient(to right, #FF9933, #FFFFFF, #138808);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-top: -20px;
        }

        /* Ensure text and elements are visible on black background */
        p, h1, h2, h3, h4, h5, h6, div, span, label {
            color: #FFFFFF;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Display the title
    st.markdown('<p class="custom-title">INDIA TMJ</p>', unsafe_allow_html=True)

    # File upload
    uploaded_file = st.file_uploader("Upload PDF", type=["pdf"], 
                                   help="Upload Trade Marks Journal PDF")
    
    if uploaded_file is not None:
        st.write(f"Processing: **{uploaded_file.name}**")
        
        # Initialize extractor
        extractor = TMJNumberExtractor()
        
        with st.spinner("Analyze your document..."):
            extracted_data = extractor.process_pdf(uploaded_file)
            excel_data = extractor.save_to_excel(extracted_data)
        
        if any(extracted_data.values()):
            st.success("Extraction completed successfully!")
            
            # Display results in tabs
            tabs = st.tabs(list(extracted_data.keys()))
            for tab, (category, numbers) in zip(tabs, extracted_data.items()):
                with tab:
                    if numbers:
                        st.write(f"Found {len(numbers):.0f} {category} numbers")  
                        clean_numbers = [int(extractor._clean_number(n)) for n in numbers]
                        df = pd.DataFrame(sorted(set(clean_numbers)), 
                                        columns=["Numbers"])
                        st.dataframe(df, use_container_width=True, height=200)
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

if __name__ == "__main__":
    main()