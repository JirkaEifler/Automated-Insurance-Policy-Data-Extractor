import os
import re
import fitz
import pandas as pd
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_FOLDER = "/Users/jirieifler/POJISTOVNY/PDFka"
CSV_PATH = "/Users/jirieifler/POJISTOVNY/EVIDENCE_UDAJE_AUTA.csv"
SORTED_FOLDER = "/Users/jirieifler/POJISTOVNY/ZPRACOVANE"
ERROR_FOLDER = "/Users/jirieifler/POJISTOVNY/CHYBY"

def extract_common_fields():
    return {
        "Jméno a příjmení": "", "Rodné číslo": "", "Datum narození": "", "Adresa": "", "Číslo smlouvy": "",
        "SPZ": "", "Cena vozidla": "", "Najeté km": "", "Roční nájezd": "", "Počátek pojištění": "", "Cena": "",
        "Krytí PR": "", "Havarijní pojištění": "", "Další připojištění": "", "Telefon": "", "E-mail": "",
        "Pojistník - Typ osoby": "", "Pojistník - Plátce DPH": "", "Shodný provozovatel": "", "Shodný vlastník": "",
        "Provozovatel - Název": "", "Provozovatel - IČO": "", "Provozovatel - Adresa": "",
        "Provozovatel - Typ osoby": "", "Provozovatel - Plátce DPH": "",
        "Vlastník - Název": "", "Vlastník - IČO": "", "Vlastník - Adresa": "",
        "Vlastník - Typ osoby": "", "Vlastník - Plátce DPH": "",
        "Zdrojový soubor": ""
    }

COLUMNS = list(extract_common_fields().keys())

def extract_data_allianz(text, filename):
    lines = text.splitlines()
    text_lower = text.lower()
    data = extract_common_fields()
    data["Zdrojový soubor"] = filename

    def search(pattern, group=1):
        match = re.search(pattern, text)
        return match.group(group).strip() if match else ""

    def search_after_line(startswith, offset=1):
        for i, line in enumerate(lines):
            if startswith.lower() in line.lower():
                if i + offset < len(lines):
                    return lines[i + offset].strip()
        return ""

    data["Jméno a příjmení"] = search_after_line("Klient (Vy):")
    data["Rodné číslo"] = search(r"Rodné číslo:\s*(\d{9,10})")
    rc = data["Rodné číslo"]
    if re.match(r"\d{6}", rc):
        rok = int(rc[:2])
        rok += 1900 if rok >= 50 else 2000
        data["Datum narození"] = f"{rc[4:6]}.{rc[2:4]}.{rok}"

    for i, line in enumerate(lines):
        if "trvalý pobyt" in line.lower():
            for j in range(i + 1, i + 3):
                if j < len(lines) and lines[j].strip():
                    data["Adresa"] = lines[j].strip()
                    break
            break

    spz_match = re.search(r"([A-Z0-9]{5,8}), č\.", text)
    if spz_match:
        data["SPZ"] = spz_match.group(1)

    data["Číslo smlouvy"] = search(r"Nabídka pojistitele č\.\s*(\d+)")
    data["Cena"] = search(r"Cena pojištění\s+([\d ]+)\s*KČ ROČNĚ").replace(" ", "")
    data["Počátek pojištění"] = search(r"KČ ROČNĚ\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})")
    data["Roční nájezd"] = search(r"Roční nájezd:\s*(Do\s*[\d\s]+km)")
    data["Telefon"] = search(r"Mobilní telefon:\s*([\+0-9 ]+)")
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    data["E-mail"] = email_match.group(0) if email_match else ""
    data["Krytí PR"] = "70/70" if "limit 70/70" in text_lower else ""
    data["Shodný provozovatel"] = "ANO" if "provozovatel je shodný" in text_lower else "NE"
    data["Shodný vlastník"] = "ANO" if "vlastník vozidla je shodný" in text_lower else "NE"

    pripojisteni = []
    for kw in ["právní poradenství", "úrazové pojištění"]:
        if f"{kw} ano" in text_lower:
            pripojisteni.append(kw.capitalize())
    data["Další připojištění"] = ", ".join(pripojisteni)

    havarijni = ["přírodní události", "poškození zvířetem", "havárie", "gap", "skla", "krádež"]
    data["Havarijní pojištění"] = "ANO" if any(f"{kw} ano" in text_lower for kw in havarijni) else "NE"
    return data

def extract_data_koop(text, filename):
    data = extract_common_fields()
    data["Zdrojový soubor"] = filename

    def find(pattern, group=1, default=""):
        match = re.search(pattern, text)
        try:
            return match.group(group).strip()
        except:
            return default

    def find_block(label, group=1):
        return find(rf"{label}\s+([^\n]*)", group)

    lines = text.splitlines()
    data["Jméno a příjmení"] = find_block(r"Titul, jméno, příjmení")
    data["Rodné číslo"] = find(r"Rodné číslo\s+(\d{9,10})")
    rc = data["Rodné číslo"]
    if re.match(r"\d{6}", rc):
        rok = int(rc[:2])
        rok += 1900 if rok >= 50 else 2000
        data["Datum narození"] = f"{rc[4:6]}.{rc[2:4]}.{rok}"

    data["Adresa"] = find_block(r"Adresa bydliště")
    data["Číslo smlouvy"] = find(r"\b(\d{10})\b")
    data["SPZ"] = find_block(r"Registrační značka")
    data["Cena vozidla"] = find(r"Pojistná částka\s+([\d\s]+)", 1).replace(" ", "")
    data["Najeté km"] = find(r"Stav počítadla \(km\)\s+([\d\s]+)", 1).replace(" ", "")
    data["Počátek pojištění"] = find(r"Počátek pojištění\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})")
    data["Cena"] = find(r"Celkové roční pojistné\s+([\d\s]+)", 1).replace(" ", "")
    data["Telefon"] = find(r"Mobil\s+(\d{3} ?\d{3} ?\d{3})")
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    data["E-mail"] = email_match.group(0) if email_match else ""
    data["Pojistník - Typ osoby"] = find(r"Typ osoby\s+([^\n]+)")

    block = re.search(r"Doplňková pojištění(.*?)(?:Roční pojistné|$)", text, re.DOTALL)
    if block:
        items = [r.strip() for r in block.group(1).split("\n") if "pojištění" in r.lower()]
        data["Další připojištění"] = ", ".join(sorted(set(items)))

    data["Havarijní pojištění"] = "ANO" if "Havarijní pojištění" in text else "NE"
    return data

def extract_data_generali(text, filename):
    data = extract_common_fields()
    data["Zdrojový soubor"] = filename

    lines = text.splitlines()
    text_lower = text.lower()

    def search(pattern, group=1):
        match = re.search(pattern, text)
        return match.group(group).strip() if match else ""

    data["Jméno a příjmení"] = search(r"Pojištěný:?\s*([A-ZŠČŘŽÁÉĚÍÝÚŮĎŤŇ][^\n]*)")
    data["Rodné číslo"] = search(r"Rodné číslo:?\s*(\d{9,10})")
    rc = data["Rodné číslo"]
    if re.match(r"\d{6}", rc):
        rok = int(rc[:2])
        rok += 1900 if rok >= 50 else 2000
        data["Datum narození"] = f"{rc[4:6]}.{rc[2:4]}.{rok}"

    data["Adresa"] = search(r"Adresa:?\s*([^\n]+)")
    data["Číslo smlouvy"] = search(r"Smlouva č\.:?\s*([\d/]+)")
    data["SPZ"] = search(r"SPZ:?\s*([A-Z0-9]{5,8})")
    data["Cena vozidla"] = search(r"Cena vozidla:?\s*([\d ]+)").replace(" ", "")
    data["Najeté km"] = search(r"Najeté km:?\s*([\d ]+)").replace(" ", "")
    data["Roční nájezd"] = search(r"Roční nájezd:?\s*([\d ]+)")
    data["Počátek pojištění"] = search(r"Počátek pojištění:?\s*(\d{1,2}\.\d{1,2}\.\d{4})")
    data["Cena"] = search(r"Roční pojistné:?\s*([\d ]+)").replace(" ", "")
    data["Telefon"] = search(r"(?:Telefon|Mobil):?\s*([\+0-9 ]+)")
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    data["E-mail"] = email_match.group(0) if email_match else ""
    data["Havarijní pojištění"] = "ANO" if "havarijní pojištění" in text_lower else "NE"
    pripojisteni = re.findall(r"Připojištění:?\s*(.*)", text)
    if pripojisteni:
        data["Další připojištění"] = ", ".join(sorted(set(pripojisteni)))
    kryti_match = re.search(r"Limit odpovědnosti:?\s*(\d+\s*mil.*?)\s*/\s*(\d+\s*mil.*?)\s*Kč", text)
    if kryti_match:
        data["Krytí PR"] = f"{kryti_match[1].replace(' ', '')}/{kryti_match[2].replace(' ', '')}"
    return data

class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(".pdf"):
            return

        filename = os.path.basename(event.src_path)
        print(f"\U0001F4E5 Nový PDF soubor detekován: {filename}")

        try:
            doc = fitz.open(event.src_path)
            text = "".join([page.get_text() for page in doc])
            doc.close()

            if not text.strip():
                print("\U0001F50D Text nenalezen, přeskočeno.")
                return

            if "generali" in text.lower():
                data = extract_data_generali(text, filename)
            elif "allianz" in text.lower():
                data = extract_data_allianz(text, filename)
            elif "kooperativa" in text.lower():
                data = extract_data_koop(text, filename)
            else:
                print("❌ Nepodporovaná pojišťovna – přeskočeno.")
                return

            df_new = pd.DataFrame([[data.get(col, "") for col in COLUMNS]], columns=COLUMNS)

            if os.path.exists(CSV_PATH):
                df_old = pd.read_csv(CSV_PATH)
                df_full = pd.concat([df_old, df_new], ignore_index=True)
            else:
                df_full = df_new

            df_full.to_csv(CSV_PATH, index=False)
            os.rename(event.src_path, os.path.join(SORTED_FOLDER, filename))
            print("✅ Data zapsána a soubor přesunut.")

        except Exception as e:
            print(f"❌ Chyba při zpracování {filename}: {e}")
            os.rename(event.src_path, os.path.join(ERROR_FOLDER, filename))

if __name__ == "__main__":
    print("👀 Sleduji složku pro nové PDF soubory (Allianz, Kooperativa, Generali)...")
    os.makedirs(SORTED_FOLDER, exist_ok=True)
    os.makedirs(ERROR_FOLDER, exist_ok=True)
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