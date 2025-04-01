import re
import pdfplumber
import pandas as pd
import streamlit as st
import logging
from io import BytesIO
from typing import Dict, List, Optional

# ================== STREAMLIT CONFIG (MUST BE FIRST) ================== #
st.set_page_config(
    page_title="TMJ Number Extractor",
    layout="wide",
    page_icon="📄"
)

# ================== CUSTOM UI STYLES ================== #
# 1. Custom Fonts
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&family=Playfair+Display:wght@700&display=swap');

html, body, [class*="css"] {
    font-family: 'Roboto', sans-serif;
}
h1, h2, h3 {
    font-family: 'Playfair Display', serif;
    color: #2F4F4F !important;
}
</style>
""", unsafe_allow_html=True)

# 2. Gradient Header
st.markdown("""
<style>
[data-testid="stHeader"] {
    background: linear-gradient(90deg, #1E3A8A, #4B8BBE);
    color: white;
}
</style>
""", unsafe_allow_html=True)

# ================== CORE LOGIC (UNCHANGED) ================== #
class TMJNumberExtractor:
    def __init__(self):
        self.section_markers = {
            'corrigenda': 'CORRIGENDA',
            'renewal': 'FOLLOWING TRADE MARKS REGISTRATION RENEWED',
            'registered': 'FOLLOWING TRADE MARK APPLICATIONS HAVE BEEN REGISTERED',
            'pr_section': 'PR SECTION'
        }
        
        self.patterns = {
            'advertisement': r'(\d{5,})\s+\d{2}/\d{2}/\d{4}',
            'corrigenda': r'(\d{5,})',
            'rc': r'\b\d{5,}\b',
            'renewal': [r'\b(\d{5,})\b', r'Application No\s+(\d{5,})'],
            'pr_section': r'(\d{5,})\s*-'
        }
        
        self.min_number_length = 5
        self.max_number_length = None 
        self.logger = logging.getLogger(__name__)

    def _clean_number(self, number: str) -> str:
        return re.sub(r"[^\d]", "", str(number))

    def _validate_number(self, number: str) -> bool:
        clean_num = self._clean_number(number)
        return (clean_num.isdigit() and 
                len(clean_num) >= self.min_number_length and
                (self.max_number_length is None or len(clean_num) <= self.max_number_length))

    def _remove_duplicates(self, numbers: List[str]) -> List[str]:
        seen = set()
        return [n for n in numbers if not (n in seen or seen.add(n))]

    def extract_numbers(self, text: str, pattern: str) -> List[str]:
        if not text: return []
        try:
            return [m for m in re.findall(pattern, text) if self._validate_number(m)]
        except Exception as e:
            self.logger.error(f"Regex error: {e}")
            return []

    def extract_advertisement_numbers(self, text: str) -> List[str]:
        numbers = []
        for line in text.split('\n'):
            if self.section_markers['corrigenda'].upper() in line.upper(): break
            numbers.extend(self.extract_numbers(line, self.patterns['advertisement']))
        return self._remove_duplicates(numbers)

    def extract_corrigenda_numbers(self, text: str) -> List[str]:
        numbers = []
        found_section = False
        for line in text.split('\n'):
            if self.section_markers['corrigenda'].upper() in line.upper():
                found_section = True
                continue
            if self.section_markers['registered'].upper() in line.upper(): break
            if found_section:
                numbers.extend(re.findall(r'(\d{5,})\s*[ ]', line))
        return self._remove_duplicates(numbers)

    def extract_rc_numbers(self, text: str) -> List[str]:
        numbers = []
        for line in text.split('\n'):
            if self.section_markers['renewal'].upper() in line.upper(): break
            if len(cols := line.split()) == 5 and all(col.isdigit() for col in cols):
                numbers.extend(cols)
        return self._remove_duplicates(numbers)

    def extract_renewal_numbers(self, text: str) -> List[str]:
        numbers = []
        in_section = False
        for line in text.split('\n'):
            if self.section_markers['renewal'].upper() in line.upper():
                in_section = True
                continue
            if in_section:
                for pattern in self.patterns['renewal']:
                    numbers.extend(self.extract_numbers(line, pattern))
        return self._remove_duplicates(numbers)

    def extract_pr_section_numbers(self, text: str) -> List[str]:
        numbers = []
        in_section = False
        for line in text.split('\n'):
            if self.section_markers['pr_section'].upper() in line.upper():
                in_section = True
                continue
            if in_section:
                numbers.extend(self.extract_numbers(line, self.patterns['pr_section']))
        return self._remove_duplicates(numbers)

    def process_pdf(self, pdf_file) -> Dict[str, List[str]]:
        extracted_data = {k: [] for k in self.section_markers}
        if not pdf_file:
            st.error("No file uploaded.")
            return extracted_data

        try:
            with pdfplumber.open(pdf_file) as pdf:
                progress_bar = st.progress(0)
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    extracted_data['advertisement'].extend(self.extract_advertisement_numbers(text))
                    extracted_data['corrigenda'].extend(self.extract_corrigenda_numbers(text))
                    extracted_data['rc'].extend(self.extract_rc_numbers(text))
                    extracted_data['renewal'].extend(self.extract_renewal_numbers(text))
                    extracted_data['pr_section'].extend(self.extract_pr_section_numbers(text))
                    progress_bar.progress((i + 1) / len(pdf.pages))
        except Exception as e:
            st.error(f"PDF processing error: {e}")
            logging.error(f"PDF error: {e}")
        
        return {k: self._remove_duplicates(v) for k, v in extracted_data.items()}

    def save_to_excel(self, data_dict: Dict[str, List[str]]) -> Optional[bytes]:
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                for sheet_name, numbers in data_dict.items():
                    if numbers:
                        df = pd.DataFrame(
                            sorted({int(self._clean_number(n)) for n in numbers}),
                            columns=["Trade Mark Number"]
                        )
                        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
            output.seek(0)
            return output.getvalue()
        except Exception as e:
            st.error(f"Excel error: {e}")
            return None

def main():
    try:
        st.title("INDIA TMJ Number Extractor")
        uploaded_file = st.file_uploader("Upload Trade Marks Journal PDF", type=["pdf"])
        
        if uploaded_file:
            extractor = TMJNumberExtractor()
            with st.spinner("Extracting numbers..."):
                extracted_data = extractor.process_pdf(uploaded_file)
                excel_data = extractor.save_to_excel(extracted_data)
            
            if any(extracted_data.values()):
                st.success("Extraction completed!")
                tabs = st.tabs([f"📰 {k.replace('_', ' ').title()}" for k in extracted_data.keys()])
                
                for tab, (category, numbers) in zip(tabs, extracted_data.items()):
                    with tab:
                        if numbers:
                            st.write(f"Found {len(numbers)} {category.replace('_', ' ')} numbers")
                            df = pd.DataFrame(
                                sorted({int(extractor._clean_number(n)) for n in numbers}),
                                columns=["Trade Mark Number"]
                            )
                            st.dataframe(df, height=400, use_container_width=True)
                        else:
                            st.info(f"No {category.replace('_', ' ')} numbers found")
                
                if excel_data:
                    st.download_button(
                        "📥 Download Excel",
                        excel_data,
                        file_name=f"tmj_numbers_{uploaded_file.name.split('.')[0]}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.warning("No numbers found in PDF")
                
    except Exception as e:
        st.error(f"Error: {e}")

if __name__ == "__main__":
    logging.basicConfig(filename="app.log", level=logging.ERROR)
    main()
