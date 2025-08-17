import os
import time
import shutil
import fitz  # PyMuPDF
import pandas as pd
import re
from datetime import datetime

# Cesty na tvém Macu
WATCH_FOLDER = r"/Users/jirieifler/POJISTOVNY/PDFka"
CSV_PATH = r"/Users/jirieifler/POJISTOVNY/EVIDENCE_UDAJE_AUTA.csv"
SORTED_FOLDER = r"/Users/jirieifler/POJISTOVNY/ZPRACOVANE"
ERROR_FOLDER = r"/Users/jirieifler/POJISTOVNY/CHYBY"
LOG_PATH = r"/Users/jirieifler/POJISTOVNY/log.txt"

def log_error(message):
    with open(LOG_PATH, "a") as log_file:
        log_file.write(f"{datetime.now()}: {message}\n")

def extract_data(text):
    def find(pattern, group=1, default=""):
        match = re.search(pattern, text)
        try:
            return match.group(group).strip()
        except:
            return default

    def find_block(label, group=1):
        return find(rf"{label}\s+([^\n]*)", group)

    lines = text.splitlines()

    vlastnik_adresa = ""
    for i, line in enumerate(lines):
        if "Adresa sídla" in line:
            addr_candidates = []
            for j in range(i + 1, min(i + 4, len(lines))):
                if re.search(r"\d{3} ?\d{2}", lines[j]) or "," in lines[j]:
                    addr_candidates.append(lines[j].strip())
            vlastnik_adresa = " ".join(addr_candidates).strip()
            break

    shodny_provozovatel = "NE"
    lines_lower = [l.lower() for l in lines]
    for i, line in enumerate(lines_lower):
        if "provozovatel" in line:
            okolni = " ".join(lines_lower[i:i + 5])
            if "shodný s pojistníkem" in okolni or "shodny s pojistnikem" in okolni:
                shodny_provozovatel = "ANO"
                break

    data = {
        "Jméno a příjmení": find_block(r"Titul, jméno, příjmení"),
        "Rodné číslo": find_block(r"Rodné číslo"),
        "Datum narození": "",
        "Adresa": find_block(r"Adresa bydliště"),
        "Číslo smlouvy": find(r"Číslo pojistné smlouvy\s+(\d+)"),
        "SPZ": find_block(r"Registrační značka"),
        "Cena vozidla": find(r"Pojistná částka\s+([\d\s]+)", 1).replace(" ", ""),
        "Najeté km": find(r"Stav počítadla \(km\)\s+([\d\s]+)", 1).replace(" ", ""),
        "Roční nájezd": "",
        "Počátek pojištění": find(r"Počátek pojištění\s+(\d{1,2}\. \d{1,2}\. \d{4})"),
        "Cena": find(r"Celkové roční pojistné\s+([\d\s]+)", 1).replace(" ", ""),
        "Krytí PR": "",
        "Havarijní pojištění": "ANO" if "Havarijní pojištění" in text else "NE",
        "Další připojištění": ", ".join(sorted(set(re.findall(r"Pojištění\s([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]+)", text)))),
        "Telefon": find(r"Mobil\s+(\d{3} ?\d{3} ?\d{3})"),
        "E-mail": find(r"E-mail\s+([^\s\n]+)"),
        "Pojistník - Typ osoby": find(r"Typ osoby\s+([^\n]+)"),
        "Pojistník - Plátce DPH": "",
        "Shodný provozovatel": shodny_provozovatel,
        "Shodný vlastník": "NE",
        "Provozovatel - Název": "", "Provozovatel - IČO": "",
        "Provozovatel - Adresa": "", "Provozovatel - Typ osoby": "",
        "Provozovatel - Plátce DPH": "",
        "Vlastník - Název": find_block(r"Vlastník\n\nNázev"),
        "Vlastník - IČO": find_block(r"IČO"),
        "Vlastník - Adresa": vlastnik_adresa,
        "Vlastník - Typ osoby": (
            re.search(r"Typ osoby\s+([^\n]+)", text[text.lower().find("vlastník"):])
            .group(1).strip()
            if "vlastník" in text.lower() and re.search(r"Typ osoby\s+([^\n]+)", text[text.lower().find("vlastník"):])
            else ""
        ),
        "Vlastník - Plátce DPH": find_block(r"Plátce DPH"),
    }

    kryti = re.search(r"Limit.*?na zdraví.*?(\d+\s*mil\.\s*Kč).*?škodě.*?(\d+\s*mil\.\s*Kč)", text, re.DOTALL)
    if kryti:
        data["Krytí PR"] = f"{kryti[1].replace(' ', '')}/{kryti[2].replace(' ', '')}"

    rc = data["Rodné číslo"]
    if re.match(r"\d{6}", rc):
        rok = int(rc[:2])
        rok += 1900 if rok >= 50 else 2000
        data["Datum narození"] = f"{rc[4:6]}.{rc[2:4]}.{rok}"

    return data

def process_pdf(file_path):
    doc = fitz.open(file_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()
    return extract_data(full_text)

def main():
    print("📂 Sledování složky spuštěno...")
    os.makedirs(SORTED_FOLDER, exist_ok=True)
    os.makedirs(ERROR_FOLDER, exist_ok=True)

    while True:
        files = [f for f in os.listdir(WATCH_FOLDER) if f.lower().endswith(".pdf")]
        if not files:
            time.sleep(5)
            continue

        for filename in files:
            full_path = os.path.join(WATCH_FOLDER, filename)
            try:
                data = process_pdf(full_path)
                df_new = pd.DataFrame([data])
                if os.path.exists(CSV_PATH):
                    df_old = pd.read_csv(CSV_PATH)
                    df_full = pd.concat([df_old, df_new], ignore_index=True)
                else:
                    df_full = df_new
                df_full.to_csv(CSV_PATH, index=False)
                shutil.move(full_path, os.path.join(SORTED_FOLDER, filename))
                print(f"✅ Zpracováno a přesunuto: {filename}")
            except Exception as e:
                log_error(f"Chyba při zpracování {filename}: {e}")
                shutil.move(full_path, os.path.join(ERROR_FOLDER, filename))
                print(f"❌ Chyba u souboru {filename}, přesunut do CHYBY")

        time.sleep(5)

if __name__ == "__main__":
    main()