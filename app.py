import re import pdfplumber import pandas as pd import streamlit as st import openpyxl import logging from io import BytesIO from concurrent.futures import ThreadPoolExecutor

Configure logging

logging.basicConfig(filename="pdf_extraction.log", level=logging.INFO, format="%(asctime)s - %(message)s")

def extract_numbers(text, pattern): """Extracts numbers using regex and filters valid ones.""" return list(set(re.findall(pattern, text)))

def extract_advertisement_numbers(text): """Extract Advertisement numbers efficiently.""" return extract_numbers(text, r'\b(\d{5,7})\b\s+\d{2}/\d{2}/\d{4}')

def extract_corrigenda_numbers(text): """Extract Corrigenda numbers dynamically.""" found_section = "CORRIGENDA" in text return extract_numbers(text, r'\b(\d{5,7})\b') if found_section else []

def extract_rc_numbers(text): """Extract RC numbers from structured tabular data.""" return extract_numbers(text, r'RC No[:\s]*(\d{5,7})')

def extract_renewal_numbers(text): """Extract Renewal numbers using two logics and combine them into one sheet.""" found_section = "Following Trade Marks Registration Renewed" in text return extract_numbers(text, r'\b(\d{5,7})\b') + extract_numbers(text, r'Application No[:\s]+(\d{5,7})') if found_section else []

def process_page(page): """Process a single PDF page for number extraction.""" text = page.extract_text() if not text: return {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []} return { "Advertisement": extract_advertisement_numbers(text), "Corrigenda": extract_corrigenda_numbers(text), "RC": extract_rc_numbers(text), "Renewal": extract_renewal_numbers(text), }

def extract_numbers_from_pdf(pdf_file): extracted_data = {"Advertisement": [], "Corrigenda": [], "RC": [], "Renewal": []} try: with pdfplumber.open(pdf_file) as pdf: with ThreadPoolExecutor() as executor: results = executor.map(process_page, pdf.pages) for result in results: for key in extracted_data: extracted_data[key].extend(result[key]) except Exception as e: logging.error(f"Error processing PDF: {e}") st.error(f"Error processing PDF: {e}") return extracted_data

def save_to_excel(data_dict): """Save extracted numbers to an Excel file efficiently.""" try: output = BytesIO() with pd.ExcelWriter(output, engine="openpyxl") as writer: for sheet_name, numbers in data_dict.items(): if numbers: df = pd.DataFrame(sorted(set(map(int, numbers))), columns=["Numbers"]) df.to_excel(writer, index=False, sheet_name=sheet_name) output.seek(0) return output if any(data_dict.values()) else None except Exception as e: logging.error(f"Error saving to Excel: {e}") st.error(f"Error saving to Excel: {e}") return None

def main(): st.title("Optimized PDF Number Extractor") uploaded_file = st.file_uploader("Choose a PDF file", type="pdf") if uploaded_file is not None: with st.spinner("Extracting numbers..."): extracted_data = extract_numbers_from_pdf(uploaded_file) excel_file = save_to_excel(extracted_data) if excel_file: st.success("Extraction Completed!") st.download_button("Download Excel File", excel_file, "extracted_numbers.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") for category, numbers in extracted_data.items(): st.write(f"{category}: {len(numbers)} numbers found")

if name == "main": main()

