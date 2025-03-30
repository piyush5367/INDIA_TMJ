import streamlit as st
import re
import pdfplumber
import pandas as pd
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import io

# Configure logging
logging.basicConfig(
    filename="pdf_extraction.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode='w'
)

# Precompile all regex patterns
PATTERNS = {
    'advertisement': re.compile(r' (\d{5,})\s+\d{2}/\d{2}/\d{4}'),
    'corrigenda': re.compile(r' (\d{5,})\s*[--]'),
    'rc': re.compile(r'\b(\d{7})\b'),
    'renewal': {
        '7digits': re.compile(r'\b(\d{7})\b'),
        'app_no': re.compile(r'Application No\s*(\d{5,})')
    }
}

def fast_extract(text, pattern):
    """Optimized number extraction using precompiled patterns."""
    return pattern.findall(text) if text else []

def process_page(page):
    """Optimized page processing with bulk text extraction."""
    try:
        text = page.extract_text()
        if not text:
            return None
        
        # Fast parallel extraction
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                'Advertisement': executor.submit(
                    lambda t: list(set(fast_extract(t.split('CORRIGENDA')[0], PATTERNS['advertisement']))),
                    text
                ),
                'Corrigenda': executor.submit(
                    lambda t: list(set(fast_extract(
                        t.split('Following Trade Mark applications have been Registered')[0].split('CORRIGENDA')[-1],
                        PATTERNS['corrigenda']
                    ))),
                    text
                ),
                'RC': executor.submit(
                    lambda t: list(set(
                        [col for line in t.splitlines() 
                         for col in line.split()[:5] 
                         if len(line.split()) == 5 and all(c.isdigit() for c in line.split()[:5])
                        ]
                    )),
                    text
                ),
                'Renewal': executor.submit(
                    lambda t: list(set(
                        fast_extract(t.split('Following Trade Marks Registration Renewed')[-1], PATTERNS['renewal']['7digits']) +
                        fast_extract(t.split('Following Trade Marks Registration Renewed')[-1], PATTERNS['renewal']['app_no'])
                    )),
                    text
                )
            }
            
            return {k: f.result() for k, f in futures.items()}
            
    except Exception as e:
        logging.error(f"Page {page.page_number} error: {str(e)}")
        return None

def fast_pdf_processing(uploaded_file, progress_bar, status_text):
    """Optimized PDF processing pipeline."""
    data = {k: [] for k in ['Advertisement', 'Corrigenda', 'RC', 'Renewal']}
    
    try:
        # Read entire file into memory for faster access
        pdf_bytes = io.BytesIO(uploaded_file.read())
        
        with pdfplumber.open(pdf_bytes) as pdf:
            total_pages = len(pdf.pages)
            start_time = time.time()
            
            # Process pages in batches
            batch_size = min(50, max(10, total_pages // 10))
            for batch_start in range(0, total_pages, batch_size):
                batch = pdf.pages[batch_start:batch_start + batch_size]
                
                with ThreadPoolExecutor(max_workers=8) as executor:
                    futures = [executor.submit(process_page, page) for page in batch]
                    
                    for i, future in enumerate(as_completed(futures), start=batch_start):
                        result = future.result()
                        if result:
                            for k, v in result.items():
                                data[k].extend(v)
                        
                        # Update progress less frequently for better performance
                        if i % 5 == 0 or i == total_pages - 1:
                            elapsed = time.time() - start_time
                            remaining = total_pages - i - 1
                            eta = (elapsed / (i + 1)) * remaining if i else 0
                            
                            status_text.markdown(
                                f"<h4 style='text-align: center; color: #FFA500;'>"
                                f"Processed {i + 1}/{total_pages} pages...<br>"
                                f"Speed: {(i + 1)/elapsed:.1f} pages/sec<br>"
                                f"ETA: {eta:.1f} seconds</h4>",
                                unsafe_allow_html=True
                            )
                            progress_bar.progress((i + 1) / total_pages)
            
            # Deduplicate results
            return {k: sorted(list(set(v))) for k, v in data.items()}
            
    except Exception as e:
        logging.error(f"PDF processing failed: {str(e)}", exc_info=True)
        st.error(f"Processing error: {str(e)}")
        return None

def main():
    """Streamlit UI with optimized rendering."""
    st.set_page_config(
        page_title="Fast PDF Extractor",
        page_icon="⚡",
        layout="wide"
    )
    
    st.markdown("""
        <style>
            .stProgress > div > div > div > div {
                background-color: #4CAF50;
            }
            .reportview-container .main .block-container {
                padding-top: 2rem;
            }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("⚡ INDIA TMJ Fast Extractor")
    st.subheader("Extract Numbers from PDF with High Speed")
    
    uploaded_file = st.file_uploader(
        "Upload PDF File", 
        type=["pdf"],
        help="For best performance, use PDFs < 100 pages"
    )
    
    if uploaded_file:
        with st.spinner("Optimizing PDF processing..."):
            # Pre-warm the system
            time.sleep(0.1)
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            start_time = time.time()
            results = fast_pdf_processing(uploaded_file, progress_bar, status_text)
            processing_time = time.time() - start_time
            
        if results:
            st.success(f"Processed in {processing_time:.2f} seconds!")
            
            # Fast rendering with tabs
            tab1, tab2, tab3, tab4 = st.tabs([
                "📢 Advertisement", 
                "✏️ Corrigenda", 
                "®️ RC", 
                "🔄 Renewal"
            ])
            
            with tab1:
                st.dataframe(pd.DataFrame(results['Advertisement'], columns=["Numbers"]))
            with tab2:
                st.dataframe(pd.DataFrame(results['Corrigenda'], columns=["Numbers"]))
            with tab3:
                st.dataframe(pd.DataFrame(results['RC'], columns=["Numbers"]))
            with tab4:
                st.dataframe(pd.DataFrame(results['Renewal'], columns=["Numbers"]))
            
            # Download all button
            csv = pd.concat([
                pd.DataFrame({k: v}) for k, v in results.items()
            ], axis=1).to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="📥 Download All Results as CSV",
                data=csv,
                file_name="tmj_extraction_results.csv",
                mime="text/csv"
            )

if __name__ == "__main__":
    main()
