"""Kapali Carsi altin/gumus ve doviz verisini ceker, prices.json dosyasini yazar.

Calistirma:  python update_prices.py
Cikti:       prices.json (proje kokunde)

Tum kaynaklar herkese acik, API anahtari gerektirmez.
Yalnizca Python standart kutuphanesi kullanilir (kurulum gerekmez).
"""

import concurrent.futures
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# --- Kaynaklar -------------------------------------------------------------

# Canli kaynak: Kapali Carsi altin/gumus ekrani (alis/satis, saniye bazli)
KAPALI_CARSI_URL = "https://anlikaltinfiyatlari.com/altin/kapalicarsi"
# Canli kaynak: Nadir Doviz ekrani (alis/satis)
NADIR_DOVIZ_URL = "https://anlikaltinfiyatlari.com/doviz/nadir-doviz"

# Yedek kaynak: gunluk kapanis JSON (sayfa yapisi degisse bile veri gelir)
DARPHANE_RAW = "https://raw.githubusercontent.com/kessinc/darphane/main"
DARPHANE_ALTIN = f"{DARPHANE_RAW}/altin.json"
DARPHANE_KUR = f"{DARPHANE_RAW}/kurlar.json"

TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# --- Gosterilecek cesitler -------------------------------------------------

GOLD_TL_ITEMS = [
    ("GRAM_HAS_ALTIN", "HAS", "Has Altın (gram)"),
    ("GRAM_ALTIN", "GR", "Gram Altın"),
    ("CEYREK_ALTIN", "CY", "Çeyrek Altın"),
    ("YARIM_ALTIN", "YM", "Yarım Altın"),
    ("TAM_ALTIN", "TM", "Tam Altın"),
    ("ATA_ALTIN", "AT", "Ata Altın"),
    ("BESLI_ALTIN", "BES", "Ata 5'li"),
    ("GREMSE_ALTIN", "GRM", "Gremse (2,5)"),
    ("22_AYAR_BILEZIK", "22A", "22 Ayar Altın"),
    ("IKIBUCUK_ALTIN", "2B5", "İkibuçuk Altın"),
]

GOLD_ONS_ITEMS = [
    ("ONS", "ONS", "Ons Altın"),
]

SILVER_ITEMS = [
    ("GUMUS", "GUM", "Gümüş (gram)"),
    ("GRAM_PLATIN", "PLT", "Platin (gram)"),
    ("GRAM_PALADYUM", "PD", "Paladyum (gram)"),
]

MAJOR_FX = [
    ("USD", "ABD Doları"),
    ("EUR", "Euro"),
    ("GBP", "İngiliz Sterlini"),
    ("CHF", "İsviçre Frangı"),
    ("JPY", "Japon Yeni"),
    ("CAD", "Kanada Doları"),
    ("AUD", "Avustralya Doları"),
    ("SAR", "Suudi Arabistan Riyalı"),
]

# Canli ekran etiketlerini anahtarlara esler
KAPALI_CARSI_MAP = {
    "has altin": "GRAM_HAS_ALTIN",
    "gram altin": "GRAM_ALTIN",
    "ceyrek altin": "CEYREK_ALTIN",
    "yarim altin": "YARIM_ALTIN",
    "tam altin": "TAM_ALTIN",
    "ata altin": "ATA_ALTIN",
    "ata 5'li": "BESLI_ALTIN",
    "ata 5'li altin": "BESLI_ALTIN",
    "gremse": "GREMSE_ALTIN",
    "gremse (2.5)": "GREMSE_ALTIN",
    "22 ayar altin": "22_AYAR_BILEZIK",
    "22 ayar bilezik": "22_AYAR_BILEZIK",
    "ikibucuk altin": "IKIBUCUK_ALTIN",
    "altin ons $": "ONS",
    "altin ons": "ONS",
    "gumus": "GUMUS",
    "gumus gram": "GUMUS",
    "gram platin": "GRAM_PLATIN",
    "platin": "GRAM_PLATIN",
    "paladyum": "GRAM_PALADYUM",
    "gram paladyum": "GRAM_PALADYUM",
}

FX_SCREEN_MAP = {
    "dolar": "USD",
    "euro": "EUR",
    "sterlin": "GBP",
    "pound": "GBP",
    "isvicre frangi": "CHF",
    "frank": "CHF",
    "japon yeni": "JPY",
    "kanada dolari": "CAD",
    "avustralya dolari": "AUD",
    "riyali": "SAR",
    "suudi riyali": "SAR",
}

# --- Yardimcilar -----------------------------------------------------------


def norm(text):
    """Turkce karakterleri indirger, bosluklari sadelestirir."""
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return " ".join(str(text or "").translate(table).lower().split())


METAL_KEYS = {norm(k): v for k, v in KAPALI_CARSI_MAP.items()}
FX_KEYS = {norm(k): v for k, v in FX_SCREEN_MAP.items()}


def to_float(raw):
    """Sayi metnini float'a cevirir.

    Hem nokta ondalikli '6648.00' hem Turkce bicimli '6.648,00' metnini anlar.
    """
    if isinstance(raw, (int, float)):
        return float(raw)

    metin = re.sub(r"[^0-9.,-]", "", str(raw or ""))
    if not metin or metin in {"-", ".", ","}:
        return None

    nokta, virgul = metin.count("."), metin.count(",")

    if nokta and virgul:
        # Ikisi de varsa son gorulen ayirici ondalik ayiricidir
        if metin.rfind(".") > metin.rfind(","):
            metin = metin.replace(",", "")
        else:
            metin = metin.replace(".", "").replace(",", ".")
    elif virgul:
        parcalar = metin.split(",")
        # Tek virgul ve ardindan 1-2 hane varsa ondaliktir
        if len(parcalar) == 2 and len(parcalar[1]) in (1, 2):
            metin = metin.replace(",", ".")
        else:
            metin = metin.replace(",", "")
    elif nokta and len(metin.split(".")) > 2:
        metin = metin.replace(".", "")

    try:
        return float(metin)
    except ValueError:
        return None


# Mantikli fiyat araliklari. Kaynak verisi bozulursa sahte fiyat
# yayimlamak yerine o satiri atlamak icin kullanilir.
ARALIK = {
    "TL": (1.0, 5_000_000.0),
    "$": (100.0, 50_000.0),
    "FX": (0.5, 5_000.0),
}

uyarilar = []


def sane(alis, satis, aralik):
    """Fiyat mantikli araliktaysa True doner."""
    alt, ust = aralik
    if not (alt <= alis <= ust and alt <= satis <= ust):
        return False
    # Satis alistan belirgin sekilde kucuk olamaz (kaynak karisikligi)
    if satis < alis * 0.95:
        return False
    return True


def get(url, as_json=False):
    """URL'den icerik ceker. Yalnizca standart kutuphane kullanir."""
    istek = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(istek, timeout=TIMEOUT) as yanit:
        ham = yanit.read()

    if as_json:
        return json.loads(ham.decode("utf-8", "replace"))

    # Turkce karakterler bozulmasin diye once dogru kodlama denenir
    for kodlama in ("utf-8", "iso-8859-9"):
        try:
            return ham.decode(kodlama)
        except UnicodeDecodeError:
            continue
    return ham.decode("utf-8", "replace")


# --- Canli kaynaklar -------------------------------------------------------


def fetch_kapali_carsi():
    """Kapali Carsi ekranindaki alis/satis satirlarini okur."""
    html = get(KAPALI_CARSI_URL)
    prices = {}
    times = []

    for row in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        link = re.search(r"<a [^>]*>([^<]+)</a>", row)
        plain = re.search(r'data-trend="[^"]+"[^>]*></span>\s*([^<]+?)\s*<span', row)
        label = link.group(1) if link else (plain.group(1) if plain else "")

        alis = re.search(r'data-name="[A-Za-z0-9_]+_alis">([\d.,]+)<', row)
        satis = re.search(r'data-name="[A-Za-z0-9_]+_satis">([\d.,]+)<', row)
        if not (label and alis and satis):
            continue

        key = METAL_KEYS.get(norm(label))
        if not key:
            continue

        alis_val, satis_val = to_float(alis.group(1)), to_float(satis.group(1))
        if alis_val is None or satis_val is None or alis_val <= 0:
            continue
        prices[key] = {"alis": alis_val, "satis": satis_val}

        stamp = re.search(r"_zaman\"[^>]*>\s*([\d:]+)", row)
        if stamp:
            times.append(stamp.group(1))

    return prices, (max(times) if times else "")


def fetch_nadir_doviz():
    """Nadir Doviz ekranindaki alis/satis kur tablosunu okur."""
    html = get(NADIR_DOVIZ_URL)
    rates = {}
    times = []

    for row in re.findall(r"<tr[^>]*>.*?</tr>", html, re.S):
        code = re.search(r'data-kurcode="([^"]+)"', row)
        alis = re.search(r'data-id="alis"[^>]*>([\d.,]+)<', row)
        satis = re.search(r'data-id="satis"[^>]*>([\d.,]+)<', row)
        if not (code and alis and satis):
            continue

        alis_val, satis_val = to_float(alis.group(1)), to_float(satis.group(1))
        if alis_val is None or satis_val is None or alis_val <= 0:
            continue
        rates[code.group(1)] = {"alis": alis_val, "satis": satis_val}

        stamp = re.search(r'data-id="saat"[^>]*>\s*([\d:]+)<', row)
        if stamp:
            times.append(stamp.group(1))

    return rates, (max(times) if times else "")


# --- Yedek kaynak (gunluk kapanis) -----------------------------------------


def fetch_darphane():
    """Sayfa yapisi degisse bile calisan yedek kaynak (gunluk kapanis)."""
    altin = get(DARPHANE_ALTIN, as_json=True)
    kurlar = get(DARPHANE_KUR, as_json=True)
    # Bu kaynak veriyi alt basliklarin icine koyuyor
    return (
        altin.get("altin_ve_emtia", {}),
        kurlar.get("serbest_piyasa_kurlari") or kurlar.get("resmi_tcmb_kurlari", {}),
    )


def darphane_metal(items, data):
    """Yedek kaynaktan metal satirlarini cikarir."""
    result = {}
    for key, symbol, name in items:
        row = data.get(key)
        if isinstance(row, dict):
            alis = to_float(row.get("alis"))
            satis = to_float(row.get("satis"))
        elif isinstance(row, (int, float)):
            alis = satis = float(row)
        else:
            continue
        if alis and satis and alis > 0:
            result[key] = {"alis": alis, "satis": satis, "symbol": symbol, "name": name}
    return result


# --- Veri kurulumu ---------------------------------------------------------


def build_rows(items, prices, darphane_data, unit, is_ons=False):
    """Verilen cesitleri, oncelikle canli veriden olusturur."""
    aralik = ARALIK["$" if is_ons else "TL"]
    rows = []

    for key, symbol, name in items:
        value = prices.get(key)
        source = "canli"

        if not value and darphane_data:
            backup = darphane_metal([(key, symbol, name)], darphane_data)
            if backup:
                value = backup[key]
                source = "kapanis"

        if not value:
            continue

        if not sane(value["alis"], value["satis"], aralik):
            uyarilar.append(f"{name}: mantiksiz fiyat, atlandi "
                            f"({value['alis']:,.2f} / {value['satis']:,.2f})")
            continue

        rows.append({
            "symbol": symbol,
            "name": name,
            "alis": round(value["alis"], 4),
            "satis": round(value["satis"], 4),
            "unit": unit,
            "source": source,
        })
    return rows


def build_forex(rates, darphane_kurlar):
    """Ana donvizleri canli ya da yedek kaynaktan olusturur."""
    rows = []

    for code, name in MAJOR_FX:
        value = rates.get(code)
        source = "canli"

        if not value and darphane_kurlar:
            row = darphane_kurlar.get(code)
            if isinstance(row, dict):
                alis = to_float(row.get("alis"))
                satis = to_float(row.get("satis") or row.get("alis"))
                if alis:
                    value = {"alis": alis, "satis": satis or alis}
                    source = "kapanis"

        if not value:
            continue

        if not sane(value["alis"], value["satis"], ARALIK["FX"]):
            uyarilar.append(f"{name} ({code}): mantiksiz kur, atlandi "
                            f"({value['alis']:,.4f})")
            continue

        rows.append({
            "symbol": code,
            "name": name,
            "alis": round(value["alis"], 4),
            "satis": round(value["satis"], 4),
            "unit": "TL",
            "source": source,
        })
    return rows


def main():
    print("Kapali Carsi verisi cekiliyor...")

    metals, metal_time = {}, ""
    rates, fx_time = {}, ""
    hata = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        isler = {
            "kapali": pool.submit(fetch_kapali_carsi),
            "doviz": pool.submit(fetch_nadir_doviz),
            "altin": pool.submit(fetch_darphane),
        }
        sonuclar = {}
        for ad, is_ in isler.items():
            try:
                sonuclar[ad] = is_.result()
            except Exception as exc:
                hata.append(f"{ad}: {exc}")
                sonuclar[ad] = None
                print(f"  [!] {ad} basarisiz: {exc}")

    if sonuclar["kapali"]:
        metals, metal_time = sonuclar["kapali"]
    if sonuclar["doviz"]:
        rates, fx_time = sonuclar["doviz"]

    yedek_altin, yedek_kur = ({}, {})
    if sonuclar["altin"]:
        yedek_altin, yedek_kur = sonuclar["altin"]
    else:
        hata.append("yedek kaynak")

    veri = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sourceTime": max([t for t in (metal_time, fx_time) if t], default=""),
        "source": "Kapali Carsi + Nadir Doviz (canli)",
        "gold": build_rows(GOLD_TL_ITEMS, metals, yedek_altin, "TL")
               + build_rows(GOLD_ONS_ITEMS, metals, yedek_altin, "$", is_ons=True),
        "silver": build_rows(SILVER_ITEMS, metals, yedek_altin, "TL"),
        "forex": build_forex(rates, yedek_kur),
    }

    toplam = sum(len(veri[k]) for k in ("gold", "silver", "forex"))
    if toplam == 0:
        print("HATA: Hicbir veri alinamadi. Site eski veriyi gostermeye devam eder.")
        return 1

    cikti = Path(__file__).resolve().parent / "prices.json"
    cikti.write_text(
        json.dumps(veri, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    canli = sum(1 for grup in ("gold", "silver", "forex")
                for r in veri[grup] if r["source"] == "canli")
    print(f"  Altin : {len(veri['gold'])} cesit")
    print(f"  Gumus : {len(veri['silver'])} cesit")
    print(f"  Doviz : {len(veri['forex'])} para birimi")
    print(f"  ({canli}/{toplam} satir canli kaynaktan)")
    if hata:
        print(f"  Yedek kaynak kullanildi: {', '.join(hata)}")
    for satir in uyarilar:
        print(f"  [!] {satir}")
    print(f"  -> {cikti.name} yazildi ({cikti.stat().st_size} bayt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
