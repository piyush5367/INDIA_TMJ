import re
import pdfplumber
import pandas as pd
import streamlit as st
import logging
from io import BytesIO
from typing import Dict, List, Optional
import gc

# Configure logging
logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, 
                   format="%(asctime)s - %(message)s")

class TMJNumberExtractor:
    """Extracts numbers from Trade Marks Journal PDFs with optimized memory usage"""
    
    def __init__(self):
        # Configure section markers (case insensitive)
        self.section_markers = {
            'corrigenda': 'CORRIGENDA',
            'renewal': 'FOLLOWING TRADE MARKS REGISTRATION RENEWED',
            'registered': 'FOLLOWING TRADE MARK APPLICATIONS HAVE BEEN REGISTERED',
            'pr_section': 'PR SECTION'
        }
        
        # Pre-compile all regex patterns for better performance
        self.patterns = {
            'advertisement': re.compile(r'(\d{5,})\s+\d{2}/\d{2}/\d{4}'),
            'corrigenda': re.compile(r'(\d{5,})'),
            'rc': re.compile(r'\b\d{5,}\b'),
            'renewal': [
                re.compile(r'\b(\d{5,})\b'),
                re.compile(r'Application No\s+(\d{5,})')
            ],
            'pr_section': re.compile(r'(\d{5,})\s*-')
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
        """Remove duplicates while preserving order using more efficient method"""
        seen = set()
        seen_add = seen.add
        return [n for n in numbers if not (n in seen or seen_add(n))]

    def extract_numbers(self, text: str, pattern: re.Pattern) -> List[str]:
        """Generic number extractor with validation using pre-compiled patterns"""
        if not text or not isinstance(text, str):
            return []
        matches = pattern.findall(text)
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
                matches = self.patterns['corrigenda'].findall(line)
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
        """Process PDF with memory optimization and return all extracted numbers"""
        extracted_data = {
            'advertisement': [],
            'corrigenda': [],
            'rc': [],
            'renewal': [],
            'pr_section': []
        }
        
        if not pdf_file:
            return extracted_data

        try:
            # Use context manager and process pages one by one to save memory
            with pdfplumber.open(pdf_file) as pdf:
                total_pages = len(pdf.pages)
                if total_pages == 0:
                    return extracted_data

                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, page in enumerate(pdf.pages):
                    # Process page and immediately release memory
                    text = page.extract_text() or ""
                    
                    # Process each section with error handling
                    try:
                        extracted_data['advertisement'].extend(self.extract_advertisement_numbers(text))
                        extracted_data['corrigenda'].extend(self.extract_corrigenda_numbers(text))
                        extracted_data['rc'].extend(self.extract_rc_numbers(text))
                        extracted_data['renewal'].extend(self.extract_renewal_numbers(text))
                        extracted_data['pr_section'].extend(self.extract_pr_section_numbers(text))
                    except Exception as e:
                        self.logger.error(f"Error processing page {i+1}: {str(e)}")
                        continue
                    
                    # Update progress and clean memory
                    progress = (i + 1) / total_pages
                    progress_bar.progress(progress)
                    status_text.text(f"Processed page {i+1}/{total_pages} ({(progress*100):.1f}%)")
                    
                    # Explicitly clean up
                    del text
                    gc.collect()

                # Final cleanup
                progress_bar.empty()
                status_text.empty()

        except Exception as e:
            self.logger.error(f"PDF processing error: {str(e)}")
            st.error(f"Error processing PDF: {str(e)}")
            return extracted_data

        # Remove duplicates from final results
        for key in extracted_data:
            extracted_data[key] = self._remove_duplicates(extracted_data[key])
            
        return extracted_data

    def save_to_excel(self, data_dict: Dict[str, List[str]]) -> Optional[bytes]:
        """Generate Excel file from extracted data with memory optimization"""
        output = BytesIO()
        try:
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                for sheet_name, numbers in data_dict.items():
                    if numbers:
                        clean_numbers = [int(self._clean_number(n)) for n in numbers]
                        df = pd.DataFrame(sorted(set(clean_numbers)), columns=["Numbers"])
                        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
            output.seek(0)
            return output.getvalue()
        except Exception as e:
            self.logger.error(f"Excel generation error: {str(e)}")
            st.error(f"Error generating Excel file: {str(e)}")
            return None
        finally:
            # Ensure resources are cleaned up
            gc.collect()

def main():
    """Streamlit application with enhanced UI"""
    st.set_page_config(page_title="Number Extractor", layout="wide")

    # Apply custom styling with improved dark blue theme
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Zen+Antique+Soft&display=swap');

        /* Dark blue background for the entire app */
        body {
            background-color: #0a1128;
            color: #FFFFFF;
        }
        .stApp {
            background-color: #0a1128;
            color: #FFFFFF;
        }

        /* Enhanced title with border and glow effect */
        .custom-title {
            font-family: 'Zen Antique Soft', serif;
            text-align: center;
            font-size: 3.5em;
            font-weight: bold;
            background: linear-gradient(to right, #FF9933, #FFFFFF, #138808);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 20px 0;
            padding: 15px;
            border: 3px solid #1a4b8c;
            border-radius: 10px;
            box-shadow: 0 0 15px rgba(26, 75, 140, 0.7);
            display: inline-block;
            width: 100%;
        }

        /* Container for centering the title */
        .title-container {
            display: flex;
            justify-content: center;
            width: 100%;
            margin-bottom: 30px;
        }

        /* Improved visibility for all text elements */
        p, h1, h2, h3, h4, h5, h6, div, span, label {
            color: #FFFFFF;
        }
        
        /* Enhanced dataframe styling */
        .stDataFrame {
            max-height: 400px;
            overflow: auto;
            border: 1px solid #1a4b8c;
            border-radius: 5px;
        }
        
        /* Better button styling */
        .stDownloadButton>button {
            background: linear-gradient(to right, #1a4b8c, #2a5c9c);
            color: white;
            border: 1px solid #3d7bb3;
            border-radius: 5px;
            padding: 8px 16px;
        }
        
        /* File uploader styling */
        .stFileUploader>div>div {
            border: 2px dashed #1a4b8c;
            border-radius: 5px;
            background-color: rgba(26, 75, 140, 0.1);
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Display the title with enhanced container
    st.markdown(
        '''
        <div class="title-container">
            <div class="custom-title">INDIA TMJ</div>
        </div>
        ''',
        unsafe_allow_html=True
    )

    # File upload with clear instructions
    with st.expander("Upload PDF File", expanded=True):
        uploaded_file = st.file_uploader(
            "Choose a Trade Marks Journal PDF file", 
            type=["pdf"],
            help="Upload large PDF files (up to 200MB). Processing may take several minutes for very large files."
        )
    
    if uploaded_file is not None:
        # Show file info and size
        file_size = len(uploaded_file.getvalue()) / (1024 * 1024)  # in MB
        st.info(f"File: {uploaded_file.name} ({file_size:.2f} MB) - Processing may take time for large files")
        
        # Initialize extractor with a status container
        status_container = st.empty()
        status_container.info("Initializing PDF processor...")
        
        extractor = TMJNumberExtractor()
        
        # Process with a spinner and status updates
        with st.spinner("Analyzing document... This may take several minutes for large files"):
            status_container.info("Extracting data from PDF pages...")
            extracted_data = extractor.process_pdf(uploaded_file)
            
            status_container.info("Generating Excel file...")
            excel_data = extractor.save_to_excel(extracted_data)
        
        status_container.empty()
        
        if any(extracted_data.values()):
            st.success("Extraction completed successfully!")
            
            # Display results in tabs with optimized rendering
            tabs = st.tabs(list(extracted_data.keys()))
            for tab, (category, numbers) in zip(tabs, extracted_data.items()):
                with tab:
                    if numbers:
                        st.write(f"Found {len(numbers):,} {category} numbers")  
                        clean_numbers = [int(extractor._clean_number(n)) for n in numbers]
                        df = pd.DataFrame(sorted(set(clean_numbers)), 
                                        columns=["Numbers"])
                        st.dataframe(df, use_container_width=True, height=400)
                    else:
                        st.info(f"No {category} numbers found.")
            
            # Download button with size information
            if excel_data:
                excel_size = len(excel_data) / (1024 * 1024)  # in MB
                st.download_button(
                    label=f"📥 Download Excel File ({excel_size:.2f} MB)",
                    data=excel_data,
                    file_name=f"tmj_numbers_{uploaded_file.name.split('.')[0]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                # Clean up memory
                del excel_data
                gc.collect()
        else:
            st.warning("No numbers extracted from the PDF. The file may not contain recognizable patterns.")

if __name__ == "__main__":
    # Add memory cleanup on script rerun
    gc.collect()
    main()
