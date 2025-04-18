import re
import pdfplumber
import pandas as pd
import streamlit as st
import logging
from io import BytesIO
from typing import Dict, List, Optional
import gc
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import os
import sys

# Configure environment before any imports
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"

# Initialize session state properly
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.progress = 0
    st.session_state.current_page = 0
    st.session_state.total_pages = 0
    st.session_state.extracted_data = None
    st.session_state.processing = False

# Configure logging
logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, 
                   format="%(asctime)s - %(message)s")

class TMJNumberExtractor:
    """Enhanced extractor with all original logic plus optimizations"""
    
    def __init__(self):
        # Original section markers as compiled regex
        self.section_markers = {
            'corrigenda': re.compile(r'CORRIGENDA', re.IGNORECASE),
            'renewal': re.compile(r'FOLLOWING TRADE MARKS REGISTRATION RENEWED', re.IGNORECASE),
            'registered': re.compile(r'FOLLOWING TRADE MARK APPLICATIONS HAVE BEEN REGISTERED', re.IGNORECASE),
            'pr_section': re.compile(r'PR SECTION', re.IGNORECASE)
        }
        
        # Original patterns pre-compiled
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
        
        # Original validation rules
        self.min_number_length = 5
        self.max_number_length = None
        
        # Optimization parameters
        self.batch_size = 3  # Reduced for better memory handling
        self.timeout_seconds = 30  # Timeout per batch
        self.logger = logging.getLogger(__name__)

    # Original cleaning function
    def _clean_number(self, number: str) -> str:
        """Original implementation preserved"""
        if not isinstance(number, str):
            return ""
        return re.sub(r"[^\d]", "", number)

    # Original validation function
    def _validate_number(self, number: str) -> bool:
        """Original implementation preserved"""
        clean_num = self._clean_number(number)
        if not clean_num:
            return False
        return (clean_num.isdigit() and 
                len(clean_num) >= self.min_number_length and
                (self.max_number_length is None or len(clean_num) <= self.max_number_length))

    # Original duplicate removal
    def _remove_duplicates(self, numbers: List[str]) -> List[str]:
        """Original implementation preserved"""
        seen = set()
        seen_add = seen.add
        return [n for n in numbers if not (n in seen or seen_add(n))]

    # Original extraction logic
    def extract_numbers(self, text: str, pattern: re.Pattern) -> List[str]:
        """Original implementation preserved"""
        if not text or not isinstance(text, str):
            return []
        matches = pattern.findall(text)
        return [m for m in matches if self._validate_number(m)]

    # All original section processors preserved exactly
    def extract_advertisement_numbers(self, text: str) -> List[str]:
        """Original implementation"""
        if not text: return []
        numbers = []
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if self.section_markers['corrigenda'].search(line): break
            numbers.extend(self.extract_numbers(line, self.patterns['advertisement']))
        return self._remove_duplicates(numbers)

    def extract_corrigenda_numbers(self, text: str) -> List[str]:
        """Original implementation"""
        if not text: return []
        numbers = []
        found_corrigenda = False
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if self.section_markers['corrigenda'].search(line):
                found_corrigenda = True
                continue
            if self.section_markers['registered'].search(line): break
            if found_corrigenda:
                numbers.extend(self.extract_numbers(line, self.patterns['corrigenda']))
        return self._remove_duplicates(numbers)

    def extract_rc_numbers(self, text: str) -> List[str]:
        """Original implementation"""
        if not text: return []
        numbers = []
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if self.section_markers['renewal'].search(line): break
            if len(cols := line.split()) == 5 and all(c.isdigit() for c in cols):
                numbers.extend(cols)
        return self._remove_duplicates(numbers)

    def extract_renewal_numbers(self, text: str) -> List[str]:
        """Original implementation"""
        if not text: return []
        numbers = []
        in_section = False
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if self.section_markers['renewal'].search(line):
                in_section = True
                continue
            if in_section:
                for pattern in self.patterns['renewal']:
                    numbers.extend(self.extract_numbers(line, pattern))
        return self._remove_duplicates(numbers)

    def extract_pr_section_numbers(self, text: str) -> List[str]:
        """Original implementation"""
        if not text: return []
        numbers = []
        in_section = False
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if self.section_markers['pr_section'].search(line):
                in_section = True
                continue
            if in_section:
                numbers.extend(self.extract_numbers(line, self.patterns['pr_section']))
        return self._remove_duplicates(numbers)

    def process_page(self, page) -> Dict[str, List[str]]:
        """Process single page with error handling"""
        try:
            text = page.extract_text() or ""
            return {
                'advertisement': self.extract_advertisement_numbers(text),
                'corrigenda': self.extract_corrigenda_numbers(text),
                'rc': self.extract_rc_numbers(text),
                'renewal': self.extract_renewal_numbers(text),
                'pr_section': self.extract_pr_section_numbers(text)
            }
        except Exception as e:
            self.logger.error(f"Page processing error: {str(e)}")
            return {k: [] for k in self.section_markers}

    def process_pdf(self, pdf_file) -> Dict[str, List[str]]:
        """Optimized PDF processing with timeout and memory management"""
        results = {k: [] for k in self.section_markers}
        results['advertisement'] = []
        
        try:
            with pdfplumber.open(pdf_file) as pdf:
                st.session_state.total_pages = len(pdf.pages)
                if not st.session_state.total_pages:
                    return results

                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Process in batches with timeout
                with ThreadPoolExecutor() as executor:
                    futures = []
                    for i in range(0, st.session_state.total_pages, self.batch_size):
                        batch = pdf.pages[i:i + self.batch_size]
                        futures.append(executor.submit(
                            lambda pages: [self.process_page(p) for p in pages], 
                            batch
                        ))
                    
                    for i, future in enumerate(futures):
                        try:
                            batch_results = future.result(timeout=self.timeout_seconds)
                            for result in batch_results:
                                for key in results:
                                    results[key].extend(result[key])
                            
                            # Update progress
                            progress = min((i + 1) * self.batch_size / st.session_state.total_pages, 1.0)
                            progress_bar.progress(progress)
                            st.session_state.current_page = min((i + 1) * self.batch_size, st.session_state.total_pages)
                            status_text.text(f"Processed {st.session_state.current_page}/{st.session_state.total_pages} pages ({(progress*100):.1f}%)")
                            
                            # Memory management
                            del batch_results
                            if i % 5 == 0:  # Clear cache periodically
                                if hasattr(pdf, 'flush_cache'):
                                    pdf.flush_cache()
                                gc.collect()
                                
                        except TimeoutError:
                            self.logger.warning(f"Batch {i} timed out after {self.timeout_seconds} seconds")
                            continue
                
                progress_bar.empty()
                status_text.empty()
                
        except Exception as e:
            self.logger.error(f"PDF processing failed: {str(e)}")
            st.error(f"Error processing PDF: {str(e)}")
        
        return {k: self._remove_duplicates(v) for k, v in results.items()}

    def save_to_excel(self, data_dict: Dict[str, List[str]]) -> Optional[bytes]:
        """Original Excel export preserved"""
        output = BytesIO()
        try:
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                for sheet_name, numbers in data_dict.items():
                    if numbers:
                        df = pd.DataFrame(
                            sorted({int(self._clean_number(n)) for n in numbers}),
                            columns=["Numbers"]
                        )
                        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
            output.seek(0)
            return output.getvalue()
        except Exception as e:
            self.logger.error(f"Excel export failed: {str(e)}")
            st.error(f"Excel generation error: {str(e)}")
            return None

def main():
    """Original UI with all enhancements preserved"""
    st.set_page_config(page_title="TMJ Extractor", layout="wide")
    
    # Your original CSS
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Zen+Antique+Soft&display=swap');
    body {
        background-color: #0a1128;
        color: #FFFFFF;
    }
    .stApp {
        background-color: #0a1128;
        color: #FFFFFF;
    }
    .custom-title {
        font-family: 'Zen Antique Soft', serif;
        text-align: center;
        font-size: 3.5em;
        font-weight: bold;
        background: linear-gradient(to right, #FF5733, #FFC300, #DAF7A6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 20px 0;
        padding: 15px;
        border: 3px solid #2a5c9c;
        border-radius: 10px;
        box-shadow: 0 0 20px rgba(42, 92, 156, 0.8);
        display: inline-block;
        width: 100%;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
    }
    .title-container {
        display: flex;
        justify-content: center;
        width: 100%;
        margin-bottom: 30px;
        background: rgba(10, 17, 40, 0.7);
        padding: 10px;
        border-radius: 10px;
    }
    .stProgress > div > div > div {
        background-color: #90EE90 !important;
    }
    .stDataFrame {
        max-height: 400px;
        overflow: auto;
        border: 1px solid #2a5c9c;
        border-radius: 5px;
        background-color: #0a1128;
    }
    .stDownloadButton>button {
        background: linear-gradient(to right, #1a4b8c, #2a5c9c);
        color: white !important;
        border: 1px solid #3d7bb3;
        border-radius: 5px;
        padding: 8px 16px;
        font-weight: bold;
    }
    .stFileUploader>div>div {
        border: 2px dashed #2a5c9c;
        border-radius: 5px;
        background-color: rgba(42, 92, 156, 0.2);
        color: white !important;
    }
    .stFileUploader label {
        color: white !important;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

    # Your original title with enhanced border
    st.markdown(
        '''
        <div class="title-container">
            <div class="custom-title">INDIA TMJ</div>
        </div>
        ''',
        unsafe_allow_html=True
    )

    # Original file uploader
    uploaded_file = st.file_uploader(
        "Upload Trade Marks Journal PDF", 
        type=["pdf"],
        help="Upload PDF files (up to 200MB). Processing may take time for large files."
    )
    
    if uploaded_file is not None and not st.session_state.processing:
        if st.button("Process PDF"):
            st.session_state.processing = True
            try:
                with st.spinner("Analyzing document..."):
                    extractor = TMJNumberExtractor()
                    st.session_state.extracted_data = extractor.process_pdf(uploaded_file)
            finally:
                st.session_state.processing = False
            st.experimental_rerun()
    
    if st.session_state.extracted_data:
        data = st.session_state.extracted_data
        if any(data.values()):
            st.success("Extraction completed successfully!")
            
            # Original tabs display
            tabs = st.tabs(list(data.keys()))
            for tab, (category, numbers) in zip(tabs, data.items()):
                with tab:
                    if numbers:
                        st.write(f"Found {len(numbers):,} {category} numbers")  
                        clean_numbers = [int(extractor._clean_number(n)) for n in numbers]
                        df = pd.DataFrame(sorted(set(clean_numbers)), columns=["Numbers"])
                        st.dataframe(df, use_container_width=True, height=400)
                    else:
                        st.info(f"No {category} numbers found.")
            
            # Original download button
            if excel_data := extractor.save_to_excel(data):
                excel_size = len(excel_data) / (1024 * 1024)
                st.download_button(
                    label=f"📥 Download Excel File ({excel_size:.2f} MB)",
                    data=excel_data,
                    file_name=f"tmj_numbers_{uploaded_file.name.split('.')[0]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("No numbers extracted from the PDF. The file may not contain recognizable patterns.")

if __name__ == "__main__":
    gc.collect()
    main()
