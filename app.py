import streamlit as st
import re
import pdfplumber
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

# Precompile all regex patterns for performance
PATTERNS = {
    'Advertisement': re.compile(r' (\d{5,})\s+\d{2}/\d{2}/\d{4}'),
    'Corrigenda': re.compile(r' (\d{5,})\s*[-—–]'),
    'RC': re.compile(r'^(\d+\s+){4}\d+$', re.MULTILINE),
    'Renewal': re.compile(r'(Application No\s*(\d{5,})|(?<!\d)(\d{5,})(?!\d))')  # Updated pattern
}

def extract_section(text, start_marker, end_marker=None):
    start = text.find(start_marker)
    if start == -1:
        return ""
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
        if "CORRIGENDA" in line:
            break
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
        if "Following Trade Mark applications have been Registered and registration certificates are available on the official website" in line:
            break
        if found_corrigenda_section:
            matches = re.findall(r'(\d{5,})\s*[-–—]', line)
            corrigenda_numbers.extend(matches)
    return list(set(corrigenda_numbers))

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
    return list(set(rc_numbers))

def extract_renewal_numbers(text):
    renewal_numbers = []
    found_renewal_section = False
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "Following Trade Marks Registration Renewed for a Period Of Ten Years" in line:
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
                        status_text.markdown(f"**Progress:** {progress:.1%}")
            final_results = {}
            for category, numbers in results.items():
                try:
                    cleaned = [str(n).strip() for n in numbers if str(n).strip()]
                    numeric_strings = [n for n in cleaned if n.isdigit()]
                    non_numeric_strings = [n for n in cleaned if not n.isdigit()]
                    sorted_numeric = sorted(numeric_strings, key=int)
                    sorted_non_numeric = sorted(non_numeric_strings)
                    final_results[category] = sorted_numeric + sorted_non_numeric
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

st.set_page_config(
    page_title="INDIA TMJ Extractor",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
        :root {
            --saffron: #FF9933;
            --saffron-light: #FFB366;
            --saffron-dark: #E68A2E;
            --green: #138808;
            --green-light: #16A309;
            --green-dark: #0D6600;
            --white: #FFFFFF;
            --text: #333333;
            --bg: #F5F5F5;
        }
        .main-title {
            text-align: center;
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--saffron-dark);
            margin-bottom: 0.5rem;
            padding-top: 1rem;
        }
        .sub-title {
            text-align: center;
            font-size: 1.1rem;
            color: var(--text);
            margin-bottom: 2rem;
        }
        .stProgress > div > div > div > div {
            background-color: var(--saffron) !important;
        }
        .stDownloadButton button {
            background-color: var(--green) !important;
            color: white !important;
            border: none !important;
            transition: all 0.3s !important;
        }
        .stDownloadButton button:hover {
            background-color: var(--green-dark) !important;
            transform: translateY(-2px);
        }
        .stTab button[aria-selected="true"] {
            color: var(--saffron-dark) !important;
            border-bottom: 3px solid var(--saffron) !important;
        }
        div.stFileUploader > div > div {
            border: 2px dashed var(--saffron) !important;
            border-radius: 8px;
        }
        .stAlert {
            border-left: 4px solid var(--saffron) !important;
        }
        .stSuccess {
            border-left: 4px solid var(--green) !important;
        }
        .stSpinner > div > div {
            border-color: var(--saffron) !important;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-title">TRADEMARK JOURNAL EXTRACTOR</h1>', unsafe_allow_html=True)
st.markdown("""
    <p class="sub-title">
        Extract Application Numbers from TMJ PDFs in Excel
    </p>
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "📄 Upload TMJ PDF File",
    type=["pdf"],
    help="Upload the Trademark Journal PDF file to extract application numbers"
)

if uploaded_file:
    progress_bar = st.progress(0)
    status_text = st.empty()
    with st.spinner("🔍 Processing PDF"):
        start_time = time.time()
        results = process_pdf(uploaded_file, progress_bar, status_text)
        processing_time = time.time() - start_time
    if results:
        progress_bar.empty()
        status_text.empty()
        st.success(f"✅ **Extraction Complete** ⏱️ Processed in {processing_time:.2f} seconds")
