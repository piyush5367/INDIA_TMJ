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
    'Corrigenda': re.compile(r' (\d{5,})\s*[-—–]'),  # Handles different dash types
    'RC': re.compile(r'^(\d+\s+){4}\d+$', re.MULTILINE),
    'Renewal': re.compile(r'(?:Application No\s*(\d{5,})|(?<!\d)(\d{5,})(?!\d))')
}

def extract_section(text, start_marker, end_marker=None):
    """Efficiently extract text section between markers"""
    start = text.find(start_marker)
    if start == -1:
        return ""
    if end_marker:
        end = text.find(end_marker, start)
        return text[start:end] if end != -1 else text[start:]
    return text[start:]

def extract_numbers(text, pattern, validation_func=None):
    """Generic number extraction with optional validation"""
    numbers = []
    for match in pattern.finditer(text):
        num = match.group(1) if len(match.groups()) >= 1 else match.group(0)
        if not validation_func or validation_func(num):
            numbers.append(num)
    return list(dict.fromkeys(numbers))  # Deduplicate while preserving order

def extract_advertisement_numbers(text):
    """Extract advertisement numbers with validation"""
    section = extract_section(text, "", "CORRIGENDA")
    return extract_numbers(section, PATTERNS['Advertisement'], lambda x: len(x) >= 5)

def extract_corrigenda_numbers(text):
    """Robust Corrigenda numbers extraction with multiple patterns"""
    section = extract_section(text, "CORRIGENDA", "Following Trade Mark applications have been Registered")
    numbers = []
    for line in section.split('\n'):
        line = line.strip()
        # Try multiple patterns
        for pattern in [
            r' (\d{5,})\s*[-—–]\s*',  # Standard pattern
            r' (\d{5,})\s*$'           # Fallback for numbers at line end
        ]:
            if match := re.search(pattern, line):
                numbers.append(match.group(1))
                break  # Use first match only
    return list(dict.fromkeys(numbers))

def extract_rc_numbers(text):
    """Extract RC numbers with validation"""
    section = extract_section(text, "", "Following Trade Marks Registration Renewed")
    numbers = []
    for line in section.split('\n'):
        cols = line.split()
        if len(cols) == 5 and all(col.isdigit() for col in cols):
            numbers.extend(cols)
    return list(dict.fromkeys(numbers))

def extract_renewal_numbers(text):
    """Extract renewal numbers with validation"""
    section = extract_section(text, "Following Trade Marks Registration Renewed")
    numbers = []
    for match in PATTERNS['Renewal'].finditer(section):
        for group in match.groups():
            if group and len(group) >= 5:
                numbers.append(group)
    return list(dict.fromkeys(numbers))

def process_page(page):
    """Process a single PDF page with error handling"""
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
    """Main PDF processing function with parallel execution"""
    results = {category: [] for category in PATTERNS.keys()}
    
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            total_pages = len(pdf.pages)
            start_time = time.time()
            
            # Dynamic worker count based on document size
            workers = min(8, max(4, total_pages // 10))
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(process_page, page) for page in pdf.pages]
                
                for i, future in enumerate(as_completed(futures), 1):
                    if (page_result := future.result()):
                        for category, numbers in page_result.items():
                            results[category].extend(numbers)
                    
                    # Update progress every 5 pages or on last page
                    if i % 5 == 0 or i == total_pages:
                        elapsed = time.time() - start_time
                        progress = i / total_pages
                        speed = i / elapsed
                        eta = (total_pages - i) / speed if speed > 0 else 0
                        
                        progress_bar.progress(progress)
                        status_text.markdown(
                            f"**Progress:** {progress:.1%} | "
                            f"**Pages:** {i}/{total_pages} | "
                            f"**Speed:** {speed:.1f} pages/sec | "
                            f"**ETA:** {eta:.1f} sec"
                        )
            
            # Final processing and validation
            final_results = {}
            for category, numbers in results.items():
                try:
                    # Clean and sort numbers
                    cleaned = [str(n).strip() for n in numbers if str(n).strip()]
                    final_results[category] = sorted(
                        list(set(cleaned)),
                        key=lambda x: int(x) if x.isdigit() else x
                    )
                except Exception as e:
                    st.error(f"Error processing {category}: {str(e)}")
                    final_results[category] = []
            
            return final_results
    
    except Exception as e:
        st.error(f"PDF processing failed: {str(e)}")
        return None

def generate_excel(data):
    """Generate Excel file with multiple sheets"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for category, numbers in data.items():
            df = pd.DataFrame(numbers, columns=['Numbers'])
            df.to_excel(
                writer,
                sheet_name=category[:31],  # Excel sheet name limit
                index=False
            )
            
            # Auto-adjust column width
            worksheet = writer.sheets[category[:31]]
            worksheet.set_column('A:A', max(15, len(category) + 5))
    
    return output.getvalue()

# Streamlit UI Configuration
st.set_page_config(
    page_title="TMJ Excel Extractor",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Custom CSS for better appearance
st.markdown("""
    <style>
        .stProgress > div > div > div > div {
            background-color: #1f77b4;
        }
        .stDownloadButton button {
            width: 100%;
            justify-content: center;
        }
        .st-emotion-cache-1v0mbdj img {
            margin: auto;
        }
    </style>
""", unsafe_allow_html=True)

# Main App Interface
st.title("📊 India TMJ to Excel Converter")
st.markdown("""
    Extract **Advertisement**, **Corrigenda**, **RC**, and **Renewal** numbers  
    from Trade Marks Journal PDFs and download as Excel file.
""")

uploaded_file = st.file_uploader(
    "Upload TMJ PDF file",
    type=["pdf"],
    help="For best results, use original PDF files (not scanned documents)"
)

if uploaded_file:
    # Display file info
    file_size = len(uploaded_file.getvalue()) / (1024 * 1024)  # in MB
    st.info(f"**File:** {uploaded_file.name} | **Size:** {file_size:.2f} MB")
    
    # Initialize processing
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_area = st.empty()
    
    with st.spinner("Analyzing document..."):
        start_time = time.time()
        results = process_pdf(uploaded_file, progress_bar, status_text)
        processing_time = time.time() - start_time
    
    if results:
        progress_bar.empty()
        status_text.empty()
        
        with results_area.container():
            st.success(f"✅ Extraction completed in {processing_time:.2f} seconds!")
            st.balloons()
            
            # Show preview in tabs
            tabs = st.tabs(list(results.keys()))
            for tab, (category, numbers) in zip(tabs, results.items()):
                with tab:
                    if numbers:
                        st.dataframe(
                            pd.DataFrame(numbers, columns=[category]),
                            height=300,
                            use_container_width=True
                        )
                        st.caption(f"Found {len(numbers)} {category} numbers")
                    else:
                        st.warning(f"No {category} numbers found")
            
            # Generate and download Excel
            st.markdown("---")
            st.subheader("Download Results")
            
            excel_file = generate_excel(results)
            st.download_button(
                label="⬇️ Download Excel File",
                data=excel_file,
                file_name="tmj_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Click to download all extracted numbers in Excel format"
            )

# Footer
st.markdown("---")
st.caption("Trade Marks Journal Data Extractor | v1.0")
