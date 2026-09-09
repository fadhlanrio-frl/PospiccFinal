# Pospicc Product Intelligence Dashboard

Implementasi MVP dari brief "Product Intelligence Dashboard" — mencakup 6 modul
(Sales, Inventory, Profitability, Marketing, Product Intelligence, Data
Reliability), AI Assistant untuk Q&A natural language, dan automation alerts.

## 🛒 Sumber data: Shopee API (semi real-time) + Plugo (standby) + manual

- **Shopee Open Platform API v2** (`shopee_api_client.py` + `shopee_scheduler.py`)
  adalah sumber utama sekarang - sync otomatis tiap `SHOPEE_SYNC_INTERVAL_MINUTES`
  (default 60 menit) sekali jalan: order baru/terupdate, produk, dan stok
  ditarik langsung dari toko Shopee kamu lewat OAuth, tidak perlu upload file
  lagi. Lihat "Setup Shopee API" di bawah untuk cara connect.
- **Plugo API** (`plugo_client.py` + `scheduler.py`) masih standby menunggu
  approval API key dari admin Plugo - kode sudah siap (base URL & auth sudah
  diverifikasi ke server asli), tinggal diaktifkan begitu key disetujui lewat
  `DATA_SOURCE_MODE=plugo` atau `both` di `.env`.
- **Template Manual** (tab kedua di halaman Import Data) tetap dipakai untuk
  **Inventory** dan **Marketing** — dua hal yang tidak disediakan Shopee lewat
  API-nya secara sederhana — dan sebagai fallback kalau kamu jual di channel
  lain di luar Shopee.

Semua sumber menulis ke tabel database yang sama (keyed by SKU/No. Pesanan),
jadi kalau data yang sama pernah disentuh lebih dari satu sumber, data
terbaru (berdasarkan waktu sync/import) yang dipakai — cek halaman **Data
Reliability** untuk tahu sumber mana yang terakhir update tiap modul.

## Struktur Project

```
pospicc_dashboard/
├── app.py                      # Home page + modul Sales
├── config.py                   # Baca semua env var di satu tempat
├── database.py                 # Skema SQLite + helper query
├── excel_importer.py           # Baca & validasi template Excel manual (Inventory/Marketing), load ke DB
├── shopee_api_client.py        # Adapter Shopee Open Platform API v2 (OAuth + signing + order/produk/stok)
├── shopee_scheduler.py         # Sync otomatis tiap 60 menit (Shopee API)
├── build_excel_template.py     # Generate ulang template Excel (jarang dipakai)
├── plugo_client.py             # Adapter Plugo API (mock + real, standby - lihat Setup Plugo)
├── scheduler.py                # Sync otomatis tiap 10 menit (mode plugo)
├── alerts.py                   # Semua automation/alert rules
├── ai_assistant.py             # Q&A natural language via OpenAI API
├── seed_demo_data.py           # Isi contoh product thesis (opsional)
├── requirements.txt
├── .env.example                # Template - copy jadi .env
├── templates/
│   └── Pospicc_Data_Template.xlsx   # Template yang di-download user di halaman Import Data
└── pages/
    ├── 00_📥_Import_Data.py
    ├── 01_📦_Inventory.py
    ├── 02_💰_Profitability.py
    ├── 03_📣_Marketing.py
    ├── 04_🧠_Product_Intelligence.py
    ├── 05_✅_Data_Reliability.py
    ├── 06_🤖_AI_Assistant.py
    ├── 07_🔔_Alerts.py
    ├── 08_🚚_Shipping_Logistics.py
    ├── 09_🌍_Customer_Geography.py
    ├── 10_👥_Customer_Insights.py
    ├── 11_🎟️_Discounts_Vouchers.py
    ├── 12_↩️_Returns_Cancellations.py
    └── 13_💸_Fees_Settlement.py
```

## Modul dari Data Order Shopee

Selain 6 modul awal, ada 6 modul tambahan yang otomatis terisi dari data order
yang ditarik sync Shopee API (dulu dari file Excel, sekarang otomatis):

| Modul | Data yang dipakai | Insight yang didapat |
|---|---|---|
| 🚚 Shipping & Logistics | Kurir, waktu kirim, berat paket | Ketepatan waktu kirim, kurir mana yang dipakai, fulfillment time |
| 🌍 Customer Geography | Provinsi/kota pembeli | Sebaran pasar, kandidat area untuk fokus marketing |
| 👥 Customer Insights | Username pembeli, metode bayar, catatan order | Repeat buyer rate, metode pembayaran favorit, suara pembeli langsung |
| 🎟️ Discounts & Vouchers | Voucher penjual/Shopee, cashback, diskon CC | Berapa besar "kebocoran" revenue ke diskon, siapa yang menanggung |
| ↩️ Returns & Cancellations | Returned quantity, status pembatalan | Produk dengan return rate tinggi - sinyal kualitas/ekspektasi |
| 💸 Fees & Settlement | Breakdown biaya per order (dari import Excel lama) | Biaya Shopee ASLI (bukan estimasi) per kategori - admin, AMS ads, dll |

Semua modul ini juga otomatis masuk ke konteks **AI Assistant**, jadi kamu bisa
tanya hal seperti "biaya apa yang paling besar makan margin kita?" atau
"provinsi mana yang paling potensial digarap?" dan dijawab berdasarkan data asli.

**Catatan tentang Fees & Settlement**: modul ini dulu terisi dari upload Excel
"Shopee Income Report", yang sudah dihapus (digantikan sync API). Shopee Open
API tidak punya endpoint payout/fee sesederhana Income Report, jadi modul ini
untuk sekarang tidak dapat data baru secara otomatis - data lama (kalau ada)
tetap tersimpan. Kalau breakdown biaya ini masih dibutuhkan, langkah lanjutan
yang mungkin: sync lewat endpoint escrow Shopee (`get_escrow_detail` per
order) - belum dibangun karena field mapping-nya perlu diverifikasi dulu
terhadap response asli.

## Setup — Step by Step

### 1. Prasyarat
- Python 3.10 atau lebih baru terinstall

### 2. Buat virtual environment & install dependencies
```bash
cd pospicc_dashboard
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Setup environment variables
```bash
cp .env.example .env
```
Buka `.env` dan isi minimal `OPENAI_API_KEY` (dari platform.openai.com) untuk
fitur AI Assistant. Biarkan `DATA_SOURCE_MODE=excel` untuk sekarang.

### 4. Jalankan aplikasi
```bash
streamlit run app.py
```

### 5. Setup Shopee API (sumber data utama)
1. Buka https://open.shopee.com/ → daftar sebagai Partner (pakai akun Shopee
   yang punya akses admin ke toko Pospicc).
2. Partner Portal → **App Management** → **Create App** (pilih tipe app untuk
   toko sendiri, bukan public/ISV app kalau memang cuma untuk 1 toko).
3. Salin **Partner ID** dan **Partner Key** dari halaman detail app ke
   `SHOPEE_PARTNER_ID` / `SHOPEE_PARTNER_KEY` di `.env`.
4. Jalankan `streamlit run app.py`, buka halaman **📥 Import Data**, salin URL
   halaman itu persis dari address bar browser ke `SHOPEE_REDIRECT_URL` di
   `.env`, lalu daftarkan URL yang sama persis di pengaturan Redirect URL app
   kamu di Shopee Open Platform. Restart aplikasi setelah `.env` diisi.
5. Di tab **🛒 Shopee API** halaman Import Data, klik **Connect Shopee**,
   login sebagai penjual toko Pospicc, setujui akses. Kamu akan diarahkan
   balik otomatis dan toko akan tersambung.
6. Sync pertama akan menarik ~24 jam data terakhir; sesudah itu otomatis tiap
   `SHOPEE_SYNC_INTERVAL_MINUTES` (default 60) menit, atau klik **Sync Shopee
   sekarang** kapan saja untuk sync manual.

### 6. Isi Inventory & Marketing (tidak disediakan Shopee API)
1. Di halaman **📥 Import Data**, buka tab **📝 Template Manual**.
2. Klik **Download Template Excel**, isi sheet **Inventory** (snapshot stock
   per SKU) dan **Marketing** (ads spend/ROAS per produk per tanggal).
3. Upload file yang sudah diisi, isi nama kamu, klik **Import ke Dashboard**.

Untuk update rutin, isi ulang sheet-nya dan upload lagi — sistem menyimpan
snapshot inventory terbaru dan menambahkan data marketing baru tanpa
menghapus histori sebelumnya.

### 7. Coba fitur AI Assistant
Buka halaman **🤖 AI Assistant**, coba tanya:
- "Produk mana yang perlu direstock bulan ini, dan kenapa?"
- "Apakah kita kehilangan penjualan karena stok terlalu rendah?"

## Setup Plugo API (standby - menunggu approval)

Kode integrasi Plugo sudah siap dan base URL/auth-nya sudah diverifikasi ke
server asli (`api.plugo.world`), tapi API key masih ditolak server sampai
admin Plugo meng-approve akses. Begitu key valid:

1. Update `PLUGO_API_KEY` di `.env` dengan key yang sudah di-approve.
2. Set `DATA_SOURCE_MODE=plugo` (Plugo saja) atau `both` (Plugo + Shopee API
   + manual template semua jalan bersamaan).
3. Restart aplikasi. Tombol "Sync Plugo now" akan muncul di Home.

Field mapping response (`_normalize_*` di `plugo_client.py`) dan endpoint
inventory Plugo (belum ketemu strukturnya - `/v1/inventory` & `/v1/stocks`
sama-sama 404) masih perlu diverifikasi begitu ada response asli.

## Troubleshooting Import Excel

- **"Sheet tidak ditemukan"** — jangan ubah nama sheet/tab di file Excel.
- **"Kehilangan kolom wajib"** — jangan ubah nama header di baris ke-2 tiap
  sheet (baris pertama adalah instruksi, bukan header).
- **Baris di-skip karena SKU tidak ditemukan** — pastikan SKU di sheet
  Sales/Inventory/Marketing persis sama (termasuk huruf besar/kecil) dengan
  SKU yang ada di sheet Products.
- Kalau perlu template baru: `python build_excel_template.py`

## Menambahkan Data Marketing & Product Intelligence

Selain lewat Excel, dua modul ini juga bisa diisi manual langsung di
dashboard: halaman **Marketing** dan **Product Intelligence** masing-masing
punya form input.

## Alert Thresholds

Semua ambang batas alert bisa diubah di `.env`:
`LOW_STOCK_THRESHOLD_UNITS`, `LOW_STOCK_DAYS_TO_STOCKOUT`, `STALE_DATA_HOURS`,
`LOW_ROAS_THRESHOLD`, `SALES_SPIKE_MULTIPLIER`.

## Known Limitations

- Template Manual (Inventory/Marketing) butuh upload manual tiap kali ada
  data baru — belum otomatis seperti sync Shopee API.
- Belum ada sistem login/role — semua orang yang buka URL bisa lihat dan
  edit semua data.
- Scheduler (Shopee API & Plugo) jalan di proses yang sama dengan Streamlit —
  belum production-grade untuk uptime 24/7; kalau proses Streamlit-nya
  restart, jadwal sync mulai dari awal lagi (bukan hilang datanya, cuma
  timer-nya reset).
- Fees & Settlement tidak lagi dapat data baru otomatis sejak upload Excel
  "Income Report" dihapus - lihat catatan di bagian "Modul dari Data Order
  Shopee" di atas.
- Field mapping response Shopee API (`_normalize`-style parsing di
  `shopee_api_client.py`) belum diverifikasi terhadap response asli karena
  OAuth belum pernah di-test end-to-end - cek data yang masuk setelah connect
  pertama kali, sesuaikan kalau ada field yang kosong/salah.
- SHOPEE_REDIRECT_URL pakai `localhost` hanya berfungsi kalau kamu connect
  dari browser di komputer yang sama dengan yang menjalankan `streamlit run` -
  untuk multi-user/deploy production butuh domain HTTPS asli.
