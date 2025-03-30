import streamlit as st
import re
import pdfplumber
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

# ===== Embedded CSS =====
def load_css():
    st.markdown("""
    <style>
        /* ===== Modern UI Theme ===== */
        :root {
            --primary: #4F46E5;        /* Indigo */
            --primary-light: #818CF8;
            --primary-dark: #4338CA;
            --secondary: #10B981;        /* Emerald */
            --danger: #EF4444;          /* Red */
            --warning: #F59E0B;         /* Amber */
            --background: #F9FAFB;      /* Gray-50 */
            --card: #FFFFFF;            /* White */
            --text: #111827;            /* Gray-900 */
            --border: #E5E7EB;          /* Gray-200 */
        }

        /* ===== Base Styles ===== */
        body {
            background-color: var(--background);
            color: var(--text);
            font-family: 'Inter', system-ui, sans-serif;
        }

        /* ===== Main Container ===== */
        .stApp {
            background-color: var(--background);
            padding: 1rem;
        }

        /* ===== Header Styles ===== */
        .main-title {
            font-size: 2.5rem;
            font-weight: 800;
            background: linear-gradient(90deg, var(--primary), var(--primary-light));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            text-align: center;
            margin-bottom: 0.5rem;
        }

        .sub-title {
            font-size: 1.1rem;
            color: var(--text);
            opacity: 0.8;
            text-align: center;
            margin-bottom: 2rem;
        }

        /* ===== Card & Container Styles ===== */
        .custom-card {
            background: var(--card);
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            margin-bottom: 1.5rem;
            border: 1px solid var(--border);
        }

        /* ===== Uploader Styles ===== */
        .stFileUploader > div {
            border: 2px dashed var(--primary) !important;
            border-radius: 12px !important;
            background-color: rgba(79, 70, 229, 0.05) !important;
            transition: all 0.3s ease !important;
        }

        .stFileUploader > div:hover {
            border-color: var(--primary-dark) !important;
            background-color: rgba(79, 70, 229, 0.1) !important;
        }

        /* ===== Button Styles ===== */
        .stButton > button {
            background-color: var(--primary) !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 0.5rem 1.5rem !important;
            font-weight: 500 !important;
            transition: all 0.2s ease !important;
        }

        .stButton > button:hover {
            background-color: var(--primary-dark) !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        /* ===== Progress Bar ===== */
        .stProgress > div > div > div {
            background-color: var(--primary) !important;
        }

        /* ===== Tab Styles ===== */
        .stTabs [aria-selected="true"] {
            color: var(--primary) !important;
            font-weight: 600 !important;
            border-bottom: 3px solid var(--primary) !important;
        }

        /* ===== Alert/Message Styles ===== */
        .stAlert {
            border-radius: 8px !important;
            border-left: 4px solid var(--primary) !important;
        }

        .stAlert.success {
            border-left-color: var(--secondary) !important;
            background-color: rgba(16, 185, 129, 0.1) !important;
        }

        .stAlert.error {
            border-left-color: var(--danger) !important;
            background-color: rgba(239, 68, 68, 0.1) !important;
        }

        .stAlert.info {
            border-left-color: var(--primary-light) !important;
            background-color: rgba(129, 140, 248, 0.1) !important;
        }

        /* ===== Data Table Styles ===== */
        .stDataFrame {
            border-radius: 8px !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
        }

        /* ===== Spinner Styles ===== */
        .stSpinner > div {
            border-color: var(--primary) !important;
            border-right-color: transparent !important;
        }
    </style>
    """, unsafe_allow_html=True)

# ===== Core Processing Functions (Unchanged) =====
PATTERNS = {
    'Advertisement': re.compile(r' (\d{5,})\s+\d{2}/\d{2}/\d{4}'),
    'Corrigenda': re.compile(r' (\d{5,})\s*[-—–]'),
    'RC': re.compile(r'^(\d+\s+){4}\d+$', re.MULTILINE),
    'Renewal': re.compile(r'(Application No\s*(\d{5,})|(?<!\d)(\d{5,})(?!\d))')
}

def extract_section(text, start_marker, end_marker=None):
    start = text.find(start_marker)
    if start == -1: return ""
    if end_marker:
        end = text.find(end_marker, start)
        return text[start:end] if end != -1 else text[start:]
    return text[start:]

def extract_numbers(text, pattern, validation_func=None):
    numbers = []
    for match in pattern.finditer(text):
        num = match.group(1) if len(match.groups()) >= 1 else match.group(0)
        if not validation_func or validation_func(num):
            numbers.append(num)
    return list(dict.fromkeys(numbers))

def extract_advertisement_numbers(text):
    advertisement_numbers = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line: break
        matches = re.findall(r'(\d{5,})\s+\d{2}/\d{2}/\d{4}', line)
        advertisement_numbers.extend(matches)
    return advertisement_numbers

def extract_corrigenda_numbers(text):
    corrigenda_numbers = []
    found_corrigenda_section = False
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line:
            found_corrigenda_section = True
            continue
        if "Following Trade Mark applications have been Registered" in line: break
        if found_corrigenda_section:
            matches = re.findall(r'(\d{5,})\s*[-–—]', line)
            corrigenda_numbers.extend(matches)
    return list(set(corrigenda_numbers))

def extract_rc_numbers(text):
    rc_numbers = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "Following Trade Marks Registration Renewed" in line: break
        columns = line.split()
        if len(columns) == 5 and all(col.isdigit() for col in columns):
            rc_numbers.extend(columns)
    return list(set(rc_numbers))

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
            renewal_numbers.extend(extract_numbers(line, re.compile(r'\b(\d{5,})\b')))
            renewal_numbers.extend(extract_numbers(line, re.compile(r'Application No\s+(\d{5,})')))
    return list(set(renewal_numbers))

def process_page(page):
    try:
        text = page.extract_text() or ""
        return {
            'Advertisement': extract_advertisement_numbers(text),
            'Corrigenda': extract_corrigenda_numbers(text),
            'RC': extract_rc_numbers(text),
            'Renewal': extract_renewal_numbers(text)
        }
    except Exception as e:
        st.error(f"Error processing page: {str(e)}")
        return None

def process_pdf(uploaded_file, progress_bar, status_text):
    results = {category: [] for category in PATTERNS.keys()}
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            total_pages = len(pdf.pages)
            start_time = time.time()
            workers = min(8, max(4, total_pages // 10))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(process_page, page) for page in pdf.pages]
                for i, future in enumerate(as_completed(futures), 1):
                    if (page_result := future.result()):
                        for category, numbers in page_result.items():
                            results[category].extend(numbers)
                    if i % 5 == 0 or i == total_pages:
                        progress = i / total_pages
                        progress_bar.progress(progress)
                        status_text.markdown(f"**Progress:** {progress:.1%} ({i}/{total_pages} pages)")
                
                # Clean and sort results
                final_results = {}
                for category, numbers in results.items():
                    try:
                        cleaned = [str(n).strip() for n in numbers if str(n).strip()]
                        numeric_strings = [n for n in cleaned if n.isdigit()]
                        non_numeric_strings = [n for n in cleaned if not n.isdigit()]
                        final_results[category] = sorted(numeric_strings, key=int) + sorted(non_numeric_strings)
                    except Exception as e:
                        st.error(f"Error processing {category}: {str(e)}")
                        final_results[category] = []
                return final_results
    except Exception as e:
        st.error(f"PDF processing failed: {str(e)}")
        return None

def generate_excel(data):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for category, numbers in data.items():
            df = pd.DataFrame(numbers, columns=['Numbers'])
            df.to_excel(writer, sheet_name=category[:31], index=False)
            worksheet = writer.sheets[category[:31]]
            worksheet.set_column('A:A', max(15, len(category) + 5))
    return output.getvalue()

def display_results(data):
    if not data:
        st.error("No data was extracted from the PDF.")
        return
    
    st.success("✅ Extraction completed successfully!")
    
    tabs = st.tabs(list(data.keys()))
    for tab, (category, numbers) in zip(tabs, data.items()):
        with tab:
            if numbers:
                st.subheader(f"{category} Numbers ({len(numbers)} found)")
                st.dataframe(numbers, height=300)
            else:
                st.info(f"No {category} numbers found")

# ===== Main App =====
def main():
    st.set_page_config(
        page_title="INDIA TMJ Extractor",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    load_css()

    with st.container():
        st.markdown('<h1 class="main-title">TRADEMARK JOURNAL EXTRACTOR</h1>', unsafe_allow_html=True)
        st.markdown('<p class="sub-title">Extract Application Numbers from TMJ PDFs in Excel</p>', unsafe_allow_html=True)

    with st.container():
        uploaded_file = st.file_uploader(
            "📄 Upload TMJ PDF File",
            type=["pdf"],
            help="Upload the Trademark Journal PDF file to extract application numbers"
        )

    if uploaded_file:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("🔍 Processing PDF..."):
            results = process_pdf(uploaded_file, progress_bar, status_text)
        
        progress_bar.empty()
        status_text.empty()
        
        if results:
            with st.container():
                st.markdown('<div class="custom-card">', unsafe_allow_html=True)
                display_results(results)
                
                excel_data = generate_excel(results)
                st.download_button(
                    label="📥 Download Excel File",
                    data=excel_data,
                    file_name="tmj_extracted_numbers.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("No data could be extracted. Please check the file format.")

if __name__ == "__main__":
    main()
