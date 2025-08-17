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
    import re
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

    # 1️⃣ Jméno, RČ, datum narození
    data["Jméno a příjmení"] = search_after_line("Klient (Vy):")
    data["Rodné číslo"] = search(r"Rodné číslo:\s*(\d{9,10})")
    rc = data["Rodné číslo"]
    if re.match(r"\d{6}", rc):
        rok = int(rc[:2])
        rok += 1900 if rok >= 50 else 2000
        data["Datum narození"] = f"{rc[4:6]}.{rc[2:4]}.{rok}"

    # 2️⃣ Adresa
    for i, line in enumerate(lines):
        if "trvalý pobyt" in line.lower():
            for j in range(i + 1, i + 3):
                if j < len(lines) and lines[j].strip():
                    data["Adresa"] = lines[j].strip()
                    break
            break

    # 3️⃣ SPZ
    spz_match = re.search(r"([A-Z0-9]{5,8}), č\.", text)
    if spz_match:
        data["SPZ"] = spz_match.group(1)

    # 4️⃣ Číslo smlouvy
    data["Číslo smlouvy"] = search(r"Nabídka pojistitele č\.\s*(\d+)")



    # 6️⃣ Počátek pojištění
    data["Počátek pojištění"] = search(r"KČ ROČNĚ\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})")

    # 7️⃣ Roční nájezd
    data["Roční nájezd"] = search(r"Roční nájezd:\s*(Do\s*[\d\s]+km)")

    # 8️⃣ Telefon a e-mail
    data["Telefon"] = search(r"Mobilní telefon:\s*([\+0-9 ]+)")
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    data["E-mail"] = email_match.group(0) if email_match else ""

    # 9️⃣ Krytí PR
    data["Krytí PR"] = "70/70" if "limit 70/70" in text_lower else ""

    # 🔟 Shodný provozovatel a vlastník
    data["Shodný provozovatel"] = "ANO" if "provozovatel je shodný" in text_lower else "NE"
    data["Shodný vlastník"] = "ANO" if "vlastník vozidla je shodný" in text_lower else "NE"

    # 1️⃣1️⃣ Další připojištění
    pripojisteni = []
    for kw in ["právní poradenství", "úrazové pojištění"]:
        if f"{kw} ano" in text_lower:
            pripojisteni.append(kw.capitalize())
    data["Další připojištění"] = ", ".join(pripojisteni)

    # 1️⃣2️⃣ Havarijní pojištění
    havarijni = ["přírodní události", "poškození zvířetem", "havárie", "gap", "skla", "krádež"]
    data["Havarijní pojištění"] = "ANO" if any(f"{kw} ano" in text_lower for kw in havarijni) else "NE"

    # 1️⃣3️⃣ Cena vozidla
    cena_vozidla_match = re.search(r"Cena vozidla\s*[:\-]?\s*([\d\s]+)\s*Kč", text, re.IGNORECASE)
    if cena_vozidla_match:
        data["Cena vozidla"] = cena_vozidla_match.group(1).replace(" ", "")
    else:
        data["Cena vozidla"] = "neuvedeno"

    # 1️⃣4️⃣ Najeté km
    najezd_match = re.search(r"Najeté km\s*[:\-]?\s*([\d\s]+)", text, re.IGNORECASE)
    if najezd_match:
        data["Najeté km"] = najezd_match.group(1).replace(" ", "")
    else:
        data["Najeté km"] = "neuvedeno"

    # 1️⃣5️⃣ Cena - formát pro Allianz
    data["Cena"] = "neuvedeno"
    for i, line in enumerate(lines):
        if "vaše pojistné" in line.lower():
            # Prohledáme následující 3 řádky
            for j in range(1, 4):
                if i + j < len(lines):
                    match = re.search(r"([0-9]{1,3}(?:[ \u00A0]?[0-9]{3}))\s*Kč", lines[i + j])
                    if match:
                        data["Cena"] = match.group(1).replace(" ", "").replace("\u00A0", "")
                        break
            break




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




#############################

def extract_data_generali(text, filename):
    import re
    data = extract_common_fields()
    data["Zdrojový soubor"] = filename

    # 1️⃣ Najdi blok POJISTNÍK
    pojistnik_match = re.search(
        r"POJISTNÍK\s*-\s*fyzická osoba\s*(.*?)\n(?:PRACOVNÍK|POJISTNÁ|TECHNICKÉ|POJIŠTĚNÍ|$)",
        text,
        re.DOTALL | re.IGNORECASE
    )
    if pojistnik_match:
        pojistnik_text = pojistnik_match.group(1)

        def extract(label):
            pattern = rf"{re.escape(label)}\s*:\s*(.+)"
            match = re.search(pattern, pojistnik_text)
            return match.group(1).strip() if match else ""

        data["Jméno a příjmení"] = extract("Titul, jméno, příjmení, titul za jménem")
        data["Rodné číslo"] = extract("Rodné číslo")
        rc = data["Rodné číslo"].replace("/", "")
        if re.match(r"\d{6}", rc):
            rok = int(rc[:2])
            rok += 1900 if rok >= 50 else 2000
            data["Datum narození"] = f"{rc[4:6]}.{rc[2:4]}.{rok}"
        data["Telefon"] = extract("Telefon")
        data["E-mail"] = extract("E-mail")
        data["Adresa"] = extract("Trvalá adresa")
        data["Pojistník - Typ osoby"] = "fyzická osoba"
    else:
        print("❌ Blok POJISTNÍK nenalezen.")

    # 2️⃣ Vyhledej číslo smlouvy
    smlouva_match = re.search(r"Pojistná smlouva číslo\s*:\s*(\d+)", text)
    if smlouva_match:
        data["Číslo smlouvy"] = smlouva_match.group(1).strip()
    else:
        print("❌ Číslo smlouvy nenalezeno.")

    # 3️⃣ Najdi blok 3.3 Údaje o vozidle
    vozidlo_match = re.search(
        r"3\.3\s+Údaje o vozidle\s*(.*?)\n(?:3\.4|POJIŠTĚNÍ|TECHNICKÉ|$)",
        text,
        re.DOTALL | re.IGNORECASE
    )
    if vozidlo_match:
        vozidlo_text = vozidlo_match.group(1)

        def extract_car(label):
            pattern = rf"{re.escape(label)}\s*:\s*(.+)"
            match = re.search(pattern, vozidlo_text)
            return match.group(1).strip() if match else ""

        data["SPZ"] = extract_car("Registrační značka")

    else:
        print("❌ Blok 3.3 Údaje o vozidle nenalezen.")

    # 4️⃣ Počátek pojištění
    pocatek_match = re.search(r"počátkem pojištění\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})", text, re.IGNORECASE)
    if pocatek_match:
        data["Počátek pojištění"] = pocatek_match.group(1).strip()
    else:
        print("❌ Počátek pojištění nenalezen.")


    # 5️⃣ Krytí PR – ve formátu 100/100 nebo 70/70
    kryti_match = re.search(
        r"Limit pojistného plnění.*?(\d{2,3})\s*[\d\s]*Kč.*?škody na majetku.*?(\d{2,3})\s*[\d\s]*Kč",
        text,
        re.DOTALL | re.IGNORECASE
    )
    if kryti_match:
        castka_zdravi = kryti_match.group(1).strip()
        castka_skoda = kryti_match.group(2).strip()
        data["Krytí PR"] = f"{castka_zdravi}/{castka_skoda}"
    else:
        print("❌ Krytí PR nenalezeno.")

    # 6️⃣ Cena – hledej přesně 9 787 nebo podobný formát
    cena_match = re.search(r"Celkem roční pojistné.*?([0-9\s]{4,7})\s*Kč", text, re.IGNORECASE)
    if not cena_match:
        cena_match = re.search(r"Výše jednotlivé splátky.*?([0-9\s]{4,7})\s*Kč", text, re.IGNORECASE)
    if not cena_match:
        cena_match = re.search(r"Částka\s*([0-9\s]{4,7})\s*Kč", text, re.IGNORECASE)

    if cena_match:
        cena = cena_match.group(1).replace(" ", "")
        data["Cena"] = cena

    # 7️⃣ Další připojištění – například "Sjednaný balíček Exclusive"
    pripojisteni_match = re.search(r"4\.2\s+Doplňková pojištění\s+(.*)", text, re.IGNORECASE)
    if pripojisteni_match:
        data["Další připojištění"] = pripojisteni_match.group(1).strip()

    # 8️⃣ Havarijní pojištění – pokud se v textu zmiňuje o havarijním pojištění

    ### ZDE ZKONTROLOVAT S KUBOU, U GENERALI TO NENÍ JASNÉ ###
    ### ZATÍM TO VYCHÁZÍ NA ANO, ikdyž to tam výslovně není ###

    text_lower = text.lower()
    havarijni_keywords = [
        "havarijní pojištění",
        "poškození zvířetem", "přírodní události", "havárie", "skla", "krádež", "vandalismus", "gap"
    ]
    data["Havarijní pojištění"] = "ANO" if any(kw in text_lower for kw in havarijni_keywords) else "NE"

    # 9️⃣ Cena vozidla – pokud je zmíněná
    vozidlo_match = re.search(r"cena vozidla\s*[:\-]?\s*([0-9\s]{4,10})", text, re.IGNORECASE)
    if vozidlo_match:
        data["Cena vozidla"] = vozidlo_match.group(1).replace(" ", "")
    else:
        data["Cena vozidla"] = "neuvedeno"

    # 🔟 Najeté km – pokud je zmíněno
    najete_km_match = re.search(r"Najeté kilometry\s*[:\-]?\s*([0-9\s]{1,10})", text, re.IGNORECASE)
    if najete_km_match:
        data["Najeté km"] = najete_km_match.group(1).replace(" ", "")
    else:
        data["Najeté km"] = "neuvedeno"

    # 1️⃣1️⃣ Roční nájezd – pokud je zmíněno
    rocni_najezd_match = re.search(r"Roční nájezd\s*[:\-]?\s*([0-9\s]{1,10})", text, re.IGNORECASE)
    if rocni_najezd_match:
        data["Roční nájezd"] = rocni_najezd_match.group(1).replace(" ", "")
    else:
        data["Roční nájezd"] = "neuvedeno"

    # 1️⃣2️⃣ Pojistník - Plátce DPH
    if re.search(r"Plátce DPH\s*[:\-]?\s*ano", text, re.IGNORECASE):
        data["Pojistník - Plátce DPH"] = "ANO"
    else:
        data["Pojistník - Plátce DPH"] = "neuvedeno"

    # 1️⃣3 Shodný provozovatel
    import re
    provozovatel_match = re.search(r"3\.2\s+Držitel\s+\(provozovatel\)\s+vozidla\s+je\s+shodný\s+s\s+pojistníkem", text, re.IGNORECASE)
    if provozovatel_match:
        data["Shodný provozovatel"] = "ANO"
    else:
        data["Shodný provozovatel"] = "NE"
        # SEM POTOM DOPSAT LOGIKU, KDYŽ BUDE NE, ABY VYPSALO NÁZEV,IČO, ADRESU APOD.

    # 1️⃣4 Vlastník - Název
    vlastnik_match = re.search(r"3\.1\s+Vlastník vozidla:\s*(.+)", text)
    if vlastnik_match:
        data["Vlastník - Název"] = vlastnik_match.group(1).strip()
        data["Shodný vlastník"] = "NE"
    else:
        data["Vlastník - Název"] = "neuvedeno"
        data["Shodný vlastník"] = "NE"


    return data

#############################


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

            if "allianz" in text.lower():
                data = extract_data_allianz(text, filename)
            elif "kooperativa" in text.lower():
                data = extract_data_koop(text, filename)
            elif "generali" in text.lower() or "česká podnikatelská" in text.lower():
                data = extract_data_generali(text, filename)
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