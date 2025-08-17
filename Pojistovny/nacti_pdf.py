import fitz  # PyMuPDF

# Absolutní cesta k souboru na ploše
pdf_path = "/Users/jirieifler/Desktop/POJISTOVNY/PDFka/petr šimon auto.pdf"

# Otevři PDF
doc = fitz.open(pdf_path)

# Načti celý text
full_text = ""
for page in doc:
    full_text += page.get_text()

doc.close()

# Výstup do konzole
print(full_text)