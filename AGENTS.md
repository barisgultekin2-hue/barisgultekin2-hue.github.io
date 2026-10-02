# AGENTS.md — barisgultekin2-hue.github.io (Kapalı Çarşı fiyat sitesi)

> GitHub Pages üzerinden yayınlanan statik fiyat sitesi.
> **Bu dosya kök `AGENTS.md`'ye üstündür.**
>
> Repo: `github.com/barisgultekin2-hue/barisgultekin2-hue.github.io`
> Canlı: `https://barisgultekin2-hue.github.io/`
>
> ## BU REPO PUBLIC
> Buraya giden her dosya internette açıktır. Kimlik bilgisi (isim, e-posta,
> telefon, adres) ekleme. Commit imzası da `anonim` olmalı. Değişiklik
> atmadan önce `git diff` ile gözden geçir.

## Ne İşe Yarar

Kapalı Çarşı altın/gümüş ve serbest piyasa döviz alış–satış fiyatlarını
gösteren tek sayfalık bir site. Veri `prices.json` dosyasından okunur.

## Mimari

```text
index.html                      # tek sayfa: HTML + CSS + JS hepsi içinde
prices.json                     # veri: güncellenen fiyat dosyası
update_prices.py                # fiyatları çekip prices.json'u yazan script
.github/workflows/update-prices.yml   # 30 dakikada bir otomatik çalıştırır
.nojekyll                       # Pages'in Jekyll'i işlememesi için (boş dosya)
```

**Veri akışı:** `update_prices.py` → HTTP kaynaklarından fiyat çeker →
`prices.json` yazar → GitHub Actions commit'ler ve push eder →
`index.html` `fetch("./prices.json")` ile okur. Sitede backend yoktur.

## Otomasyon

`update-prices.yml` her 30 dakikada bir (`cron: "0 */30 * * *"`) çalışır:

- Depoyu indirir, Python 3.12 kurar, `python update_prices.py` çalıştırır
- `prices.json` değiştiyse commit atıp push eder
- Fiyatlar değişmediyse hiçbir şey yapmaz (`git diff --quiet` kontrolü)

**Bunun sonucu:** Bu repoda `github-actions[bot]` tarafından otomatik
commit'ler oluşur. `git log`'da günde 48 commit göreceksin. Bu normal.
`workflow_dispatch` ile elle de tetiklenebilir.

**Değiştirirsen:** Sıklığı `update-prices.yml` içindeki `cron` satırından
değişir. Site metninde de bu süreye referans varsa (`index.html` "Hakkımda"
bölümü) **ikisini birlikte güncelle**, yoksa site kendini yanlış tanımlar.

## Asla Yapma

- **Kimlik bilgisi ekleme.** Repo public. İsim, e-posta, telefon, adres yok.
- **`prices.json`'ı elle düzenleme.** Her 30 dakikada otomatik ezilecek.
- **`.nojekyll` dosyasını silme.** Yoksa Pages Jekyll çalıştırıp siteyi bozar.
- **`prices.json`'ı workflow dışında değiştirip commit atma.** Fiyatlar
  her zaman kaynaktan gelmeli.
- **`update_prices.py`'deki kaynak URL'lerini değiştirirken** sitenin
  footer'daki kaynak bağlantılarıyla (`index.html` 245-247. satırlar) uyumlu
  tut. Üçüncü taraf kaynaklara atfrizasyon zorunlu.

## Kimlik Denetimi (Public Repo)

Yeni dosya veya commit atmadan önce şu taramayı çalıştır:

```powershell
Select-String -Path *.html,*.py,*.json -Pattern "Barış|Baris G|barisgu|@gmail|mailto|tel:"
```

Çıktı boşsa temizdir. Doluysa her eşleşmeyi incele — bazıları `@keyframes`
gibi zararsız CSS olabilir, ama isim/e-posta olanları temizle.