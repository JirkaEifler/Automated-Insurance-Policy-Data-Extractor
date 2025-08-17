
import os
import re
import fitz
import pandas as pd
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_FOLDER = r"C:\Users\kubab\OneDrive\Plocha\GFS\MAJETEK\AUTA"
SORTED_FOLDER = r"C:\Users\kubab\OneDrive\Plocha\GFS\SORTING"
EXCEL_PATH = r"C:\Users\kubab\OneDrive\Plocha\GFS\EVIDENCE\ÚDAJE AUTA.xlsx"

def extract_common_fields():
    return {
        "Jméno a příjmení": "", "Rodné číslo": "", "Datum narození": "", "Adresa": "", "Číslo smlouvy": "",
        "SPZ": "", "Cena vozidla": "", "Najeté km": "", "Roční nájezd": "", "Počátek pojištění": "", "Cena": "",
        "Krytí PR": "", "Havarijní pojištění": "", "Další připojištění": "", "Telefon": "", "E-mail": "",
        "Pojistník - Typ osoby": "", "Pojistník - Plátce DPH": "", "Shodný provozovatel": "", "Shodný vlastník": "",
        "Provozovatel - Název": "", "Provozovatel - IČO": "", "Provozovatel - Adresa": "",
        "Provozovatel - Typ osoby": "", "Provozovatel - Plátce DPH": "",
        "Vlastník - Název": "", "Vlastník - IČO": "", "Vlastník - Adresa": "",
        "Vlastník - Typ osoby": "", "Vlastník - Plátce DPH": ""
    }

COLUMNS = list(extract_common_fields().keys())

def extract_data_allianz(text):
    lines = text.splitlines()
    text_lower = text.lower()

    def search(pattern, group=1):
        match = re.search(pattern, text)
        return match.group(group).strip() if match else ""

    def search_after_line(startswith, offset=1):
        for i, line in enumerate(lines):
            if startswith.lower() in line.lower():
                if i + offset < len(lines):
                    return lines[i + offset].strip()
        return ""

    data = extract_common_fields()
    data["Jméno a příjmení"] = search_after_line("Klient (Vy):")
    data["Rodné číslo"] = search(r"Rodné číslo:\s*(\d{9,10})")
    rc = data["Rodné číslo"]
    if re.match(r"\d{6}", rc):
        rok = int(rc[:2])
        rok += 1900 if rok >= 50 else 2000
        data["Datum narození"] = f"{rc[4:6]}.{rc[2:4]}.{rok}"

    for i, line in enumerate(lines):
        if "trvalý pobyt" in line.lower():
            for j in range(i+1, i+3):
                if j < len(lines) and lines[j].strip():
                    data["Adresa"] = lines[j].strip()
                    break
            break

    spz_match = re.search(r"([A-Z0-9]{5,8}), č\.", text)
    if spz_match:
        data["SPZ"] = spz_match.group(1)

    data["Číslo smlouvy"] = search(r"Nabídka pojistitele č\.\s*(\d+)")
    cena_match = re.search(r"Cena pojištění\s+([\d ]+)\s*KČ ROČNĚ", text, re.IGNORECASE)
    if cena_match:
        data["Cena"] = cena_match.group(1).replace(" ", "")

    start_match = re.search(r"KČ ROČNĚ\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})", text, re.IGNORECASE)
    if start_match:
        data["Počátek pojištění"] = start_match.group(1).strip()

    najed_match = re.search(r"Roční nájezd:\s*(Do\s*[\d\s]+km)", text, re.IGNORECASE)
    if najed_match:
        data["Roční nájezd"] = najed_match.group(1).strip()

    email_match = re.search(r"E[-–]?mail\s*[:：]?\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    if email_match:
        data["E-mail"] = email_match.group(1)

    data["Telefon"] = search(r"Mobilní telefon:\s*([\+0-9 ]+)")
    data["Krytí PR"] = "70/70" if "limit 70/70" in text_lower else ""
    data["Shodný provozovatel"] = "ANO" if "provozovatel je shodný s pojistníkem" in text_lower or "držitel/provozovatel je shodný s pojistníkem" in text_lower else "NE"
    data["Shodný vlastník"] = "ANO" if "vlastník vozidla je shodný s pojistníkem" in text_lower else "NE"

    # Připojištění + havarijní pojištění
    normalized = text.replace("\n", " ").lower()

    pripojisteni_keywords = [
        "právní poradenství",
        "úrazové pojištění"
    ]

    havarijni_bloky = [
        "přírodní události",
        "požár a výbuch",
        "poškození zvířetem",
        "krádež",
        "skla",
        "vandalismus",
        "havárie",
        "doplatek na nové",
        "gap"
    ]

    pripojisteni = []
    for keyword in pripojisteni_keywords:
        if f"{keyword} ano" in normalized:
            pripojisteni.append(keyword.capitalize())

    data["Další připojištění"] = ", ".join(pripojisteni)

    data["Havarijní pojištění"] = "ANO" if any(f"{kw} ano" in normalized for kw in havarijni_bloky) else "NE"

    return data

def extract_data_koop(text):
    def find(pattern, group=1, default=""):
        match = re.search(pattern, text)
        try:
            return match.group(group).strip()
        except:
            return default

    def find_block(label, group=1):
        return find(rf"{label}\s+([^\n]*)", group)

    lines = text.splitlines()
    data = extract_common_fields()

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
            okolni = " ".join(lines_lower[i:i+5])
            if "shodný s pojistníkem" in okolni or "shodny s pojistnikem" in okolni:
                shodny_provozovatel = "ANO"
                break

    data["Jméno a příjmení"] = find_block(r"Titul, jméno, příjmení")
    data["Rodné číslo"] = find_block(r"Rodné číslo")
    data["Adresa"] = find_block(r"Adresa bydliště")
    data["Číslo smlouvy"] = find(r"Číslo pojistné smlouvy\s+(\d+)")
    data["SPZ"] = find_block(r"Registrační značka")
    data["Cena vozidla"] = find(r"Pojistná částka\s+([\d\s]+)", 1).replace(" ", "")
    data["Najeté km"] = find(r"Stav počítadla \(km\)\s+([\d\s]+)", 1).replace(" ", "")
    data["Počátek pojištění"] = find(r"Počátek pojištění\s+(\d{1,2}\. \d{1,2}\. \d{4})")
    data["Cena"] = find(r"Celkové roční pojistné\s+([\d\s]+)", 1).replace(" ", "")
    data["Havarijní pojištění"] = "ANO" if "Havarijní pojištění" in text else "NE"
    data["Další připojištění"] = ", ".join(sorted(set(re.findall(r"Pojištění\s([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]+)", text))))
    data["Telefon"] = find(r"Mobil\s+(\d{3} ?\d{3} ?\d{3})")
    data["E-mail"] = find(r"E-mail\s+([^\s\n]+)")
    data["Pojistník - Typ osoby"] = find(r"Typ osoby\s+([^\n]+)")
    data["Shodný provozovatel"] = shodny_provozovatel
    data["Shodný vlastník"] = "NE"
    data["Vlastník - Název"] = find_block(r"Vlastník\n\nNázev")
    data["Vlastník - IČO"] = find_block(r"IČO")
    data["Vlastník - Adresa"] = vlastnik_adresa
    data["Vlastník - Typ osoby"] = (
        re.search(r"Typ osoby\s+([^\n]+)", text[text.lower().find("vlastník"):])
        .group(1).strip()
        if "vlastník" in text.lower() and re.search(r"Typ osoby\s+([^\n]+)", text[text.lower().find("vlastník"):])
        else ""
    )
    data["Vlastník - Plátce DPH"] = find_block(r"Plátce DPH")

    rc = data["Rodné číslo"]
    if re.match(r"\d{6}", rc):
        rok = int(rc[:2])
        rok += 1900 if rok >= 50 else 2000
        data["Datum narození"] = f"{rc[4:6]}.{rc[2:4]}.{rok}"

    kryti = re.search(r"Limit.*?na zdraví.*?(\d+\s*mil\.\s*Kč).*?škodě.*?(\d+\s*mil\.\s*Kč)", text, re.DOTALL)
    if kryti:
        data["Krytí PR"] = f"{kryti[1].replace(' ', '')}/{kryti[2].replace(' ', '')}"

    return data

class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(".pdf"):
            return

        filename = os.path.basename(event.src_path)
        print(f"📥 Nový PDF soubor detekován: {filename}")

        doc = fitz.open(event.src_path)
        text = "".join([page.get_text() for page in doc])
        doc.close()

        if re.search(r"allianz", text, re.IGNORECASE):
            print("✅ Allianz rozpoznán – spouštím extrakci...")
            data = extract_data_allianz(text)
        elif re.search(r"kooperativa", text, re.IGNORECASE):
            print("✅ Kooperativa rozpoznána – spouštím extrakci...")
            data = extract_data_koop(text)
        else:
            print("❌ Nepodporovaný formát PDF.")
            return

        print("🧾 Získaná data:")
        for k, v in data.items():
            print(f"{k}: {v}")

        df_new = pd.DataFrame([[data.get(col, "") for col in COLUMNS]], columns=COLUMNS)

        if os.path.exists(EXCEL_PATH):
            df_old = pd.read_excel(EXCEL_PATH)
            df_full = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_full = df_new

        df_full.to_excel(EXCEL_PATH, index=False)
        os.rename(event.src_path, os.path.join(SORTED_FOLDER, filename))
        print("✅ Data zapsána a soubor přesunut.")

if __name__ == "__main__":
    print("👀 Sleduji složku pro nové PDF soubory (Allianz + Kooperativa)...")
    event_handler = PDFHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
