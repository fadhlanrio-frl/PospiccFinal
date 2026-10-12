# Pospicc Dashboard — Technical Lessons Learned
*Referensi untuk project rebuild berikutnya (Firebase atau platform lain). Semua fakta di bawah ini TERVERIFIKASI secara empiris (bukan tebakan/dokumentasi pihak ketiga yang belum dicek) selama pengembangan dashboard versi Streamlit+Turso.*

---

## 1. Shopee Open Platform API v2 — fakta yang sudah terverifikasi

### Base URL (SERING SALAH kalau cuma googling)
- **Sandbox/Test (status app "Developing")**: `https://openplatform.sandbox.test-stable.shopee.sg`
  (Verifikasi 2026-09-11 via dropdown "Request URL" di API Test Tool Shopee sendiri. Host `partner.test-stable.shopeemobile.com` yang banyak disebut di guide pihak ketiga itu **SALAH/usang**.)
- **Live/Production (status app sudah "Live")**: `https://partner.shopeemobile.com`
  (Verifikasi 2026-09-21 dengan request bertanda tangan sengaja salah — hasil `error_sign` bukan `invalid_partner_id` membuktikan host ini cocok dengan Partner ID Live.)
- **Cara verifikasi host kalau ragu**: kirim request dengan `sign` asal-asalan ke endpoint `auth_partner` pakai partner_id yang benar. Kalau hasilnya `error_sign` → host benar, partner_id dikenali. Kalau `invalid_partner_id` → host salah/partner_id tidak terdaftar di situ.

### Alur OAuth
1. `GET {host}/api/v2/shop/auth_partner?partner_id=...&timestamp=...&sign=...&redirect=...` — link ini dibuka user, login, approve, lalu Shopee redirect balik ke `redirect` dengan `?code=...&shop_id=...`.
2. `POST {host}/api/v2/auth/token/get` body `{code, shop_id, partner_id}` — tukar code jadi access_token/refresh_token.
3. `POST {host}/api/v2/auth/access_token/get` body `{refresh_token, shop_id, partner_id}` — refresh token (access_token berlaku 4 jam, refresh_token 30 hari).

**PENTING — response shape beda untuk endpoint auth vs endpoint bisnis:**
- Endpoint auth (`token/get`, `access_token/get`) → `access_token`/`refresh_token`/`expire_in` ada di **level atas** response JSON.
- Endpoint bisnis lainnya (order, product) → data sebenarnya ada di dalam `response.{...}`, bukan level atas (`{"error":"", "message":"", "request_id":"...", "response": {...}}`).

### Signing (HMAC-SHA256)
- Endpoint publik/auth: `base_string = partner_id + path + timestamp`
- Endpoint level-toko (butuh access_token): `base_string = partner_id + path + timestamp + access_token + shop_id`
- Sign = HMAC-SHA256(partner_key, base_string), hasil hex.

### Endpoint yang sudah dipakai & terverifikasi
| Endpoint | Method | Catatan |
|---|---|---|
| `/api/v2/order/get_order_list` | GET | `time_range_field`, `time_from`, `time_to` (maks rentang **15 hari** per panggilan!), `page_size`, `cursor`. `order_status` **OPSIONAL** — nilai `"ALL"` TIDAK VALID, kosongkan saja untuk dapat semua status. |
| `/api/v2/order/get_order_detail` | GET | `order_sn_list` (maks 50/panggilan), `response_optional_fields` (wajib sebut field yang mau diambil, misal `order_status,buyer_username,recipient_address,item_list,total_amount,create_time,payment_method,shipping_carrier,actual_shipping_fee,voucher,coin_offset,discount,note`). |
| `/api/v2/product/get_item_list` | GET | `offset`, `page_size`, `item_status` (misal `"NORMAL"`). Response key: `item` (list `{item_id, item_status}`), `has_next_page`. |
| `/api/v2/product/get_item_base_info` | GET | `item_id_list` (maks 50/panggilan). Field: `item_name`, `item_sku`, `has_model`, `original_price` (**flat**, bukan `price_info` bersarang), `seller_stock` (list `{location_id, stock}`, **bukan** `stock_info_v2`). |
| `/api/v2/product/get_model_list` | GET | `item_id`. Untuk produk dengan varian (`has_model=true`). **BELUM terverifikasi penuh** ke response asli. |

### Gotcha penting
- Shopee kirim string literal **`"-"`** (bukan null/kosong) untuk field teks yang belum diisi, misal `item_sku`. Harus di-treat sama seperti "tidak ada".
- **Kemungkinan bug SKU** (masih diinvestigasi per 2026-10-13): kode lama prioritaskan `model_sku` sebelum `item_sku` — kalau dua field itu beda nilai untuk 1 produk, bisa salah ambil SKU. Ditemukan dari ketidakcocokan SKU "TPLJ-2" (dashboard) vs "PNT-02" (Seller Center) untuk transaksi yang sama. **Verifikasi ulang kalau rebuild.**
- `order_status` yang berarti order GAGAL/batal: `CANCELLED`, `IN_CANCEL`. Line item dari order berstatus ini **jangan dihitung sebagai sales/revenue**, tapi order headernya tetap perlu disimpan untuk modul "Returns & Cancellations".
- Rentang waktu `get_order_list` **maksimal 15 hari per panggilan** — kalau butuh data lebih lama, pecah jadi beberapa panggilan berurutan.
- **"Access to Sensitive Data"** (izin terpisah dari akses API dasar) — tanpa izin ini, field alamat pembeli (`city`, `province` di `recipient_address`) datang **tersamar jadi `"****"`**. Field `buyer_username` TIDAK ikut tersamar (beda tingkat sensitivitas).
- Rate limit disebut ~10 request/detik per toko (belum pernah di-stress-test langsung).

### Fakta navigasi Shopee Open Platform Console
- Field **"Test/Live Redirect URL Domain"** minta **DOMAIN SAJA** (protokol+host+port), **BUKAN** path lengkap — jangan isi dengan URL lengkap termasuk path halaman.
- **API Test Tool** di console **cuma bisa pakai Partner ID Test/sandbox** — tidak akan pernah muncul pilihan Partner ID Live, walau app sudah Live. Tidak bisa dipakai untuk cek data produksi asli.
- Login ke akun test sandbox **tidak bisa lewat form login manual biasa** — harus lewat tombol **"Login Seller Center"** di halaman "Test Account-Sandbox v2", dan region/negaranya harus dicocokkan (misal "ID" bukan "SG") sesuai `Area` akun test tersebut.
- Status app "Developing" dan "Live" punya **Partner ID + Partner Key terpisah** (bukan yang sama). Live API Partner Key juga punya **tanggal kadaluarsa** yang perlu diperpanjang berkala.
- IP Address Whitelist itu opsional (toggle default OFF) — kalau mau diaktifkan, perlu tahu IP tetap server hosting kamu (banyak platform gratis seperti Streamlit Cloud TIDAK punya IP tetap yang terjamin).

---

## 2. Pelajaran soal hosting/infrastruktur (konsep ini berlaku di platform manapun, bukan cuma Streamlit)

- **Jangan simpan data penting di storage lokal/ephemeral** — kalau platform hosting bisa "tidur"/restart container (banyak tier gratis begitu), semua file lokal (termasuk database SQLite lokal) bisa hilang total. Selalu pakai database eksternal yang persisten.
- **Background job (scheduler/cron) yang nempel di proses aplikasi akan ikut mati** kalau aplikasinya di-restart/ditidurkan oleh platform hosting. Kalau butuh job yang BENERAN jalan terus (misal sync per jam), harus pakai infrastruktur terjadwal yang independen dari status aplikasi (contoh: Firebase Scheduled Functions, GitHub Actions cron, dll) — bukan cuma scheduler yang jalan di dalam proses app.
- Kalau terpaksa pakai workaround "ping biar app tidak tidur" (misal GitHub Actions cron ping URL tiap 10 menit) — itu cuma tambal sulam, bukan solusi permanen. GitHub juga otomatis menonaktifkan scheduled workflow kalau repo tidak ada commit 60 hari.
- **Saat job terjadwal baru "bangun" setelah mati entah berapa lama** — jangan hardcode window lookback tetap (misal "ambil 24 jam terakhir"). Simpan timestamp sync sukses terakhir di database (bukan di memori proses), lalu hitung gap SEBENARNYA — supaya downtime berhari-hari tetap ter-backfill dengan benar, bukan cuma nutup 24 jam dan diam-diam kehilangan sisanya.

---

## 3. Pelajaran arsitektur data (relevan kalau tetap pakai SQL; kalau pindah ke Firestore/NoSQL, baca baik-baik)

- Skema dashboard ini **sangat relasional** — banyak JOIN antar tabel (products ↔ sales_orders ↔ order_headers) dan agregasi (`GROUP BY` + `SUM`/`COUNT`) di hampir semua halaman.
- **Firestore (NoSQL) TIDAK punya JOIN dan GROUP BY multi-kolom** seperti SQL. Kalau rebuild pakai Firestore, agregasi (total revenue per SKU, jumlah order per provinsi, dst) harus:
  - Dihitung di sisi aplikasi (ambil banyak dokumen, jumlahkan manual) — bisa lambat/mahal untuk data besar, ATAU
  - Disimpan sebagai "dokumen ringkasan" terpisah yang di-update otomatis oleh Cloud Function tiap ada data baru masuk (pola umum di Firestore, tapi nambah kompleksitas signifikan dibanding query SQL biasa).
- Firestore punya fitur aggregation query (`count()`, `sum()`, `average()`) tapi itu cuma untuk SATU query terfilter, bukan pengganti `GROUP BY sku` yang menghasilkan banyak baris sekaligus.

---

## 4. Pelajaran logika bisnis (berlaku di platform manapun)

- **"Unit terjual" (jumlah quantity) ≠ "jumlah order"** — satu order bisa berisi beberapa quantity dari satu produk. Jangan tampilkan cuma salah satu tanpa label jelas, orang gampang salah paham.
- **HPP (harga pokok) TIDAK tersedia dari Shopee API sama sekali** — kalau auto-register produk dari Shopee, HPP akan selalu 0 kecuali diisi manual. Hati-hati: ini bikin margin keuntungan kelihatan "100%" (salah/menyesatkan) kalau tidak disadari, bukan cuma angka 0 yang jelas kelihatan aneh.
- **Alert/notifikasi butuh mekanisme dedup** — tanpa itu, kondisi yang sama (misal stok rendah) akan dicatat ulang sebagai alert baru SETIAP kali job sync jalan, bukan cuma sekali waktu kondisi itu benar-benar baru terjadi.
- Tabel yang sudah di-`GROUP BY` tidak akan pernah punya baris dengan SKU yang sama dua kali — kalau menemukan itu, berarti sedang salah lihat level data (per-transaksi vs teragregasi).
- Order yang **dibatalkan pembeli** harus dikeluarkan dari semua angka penjualan/revenue, TAPI datanya tetap perlu disimpan untuk modul riwayat pembatalan — jangan dihapus total dari database.

---

## 5. Ringkasan kebutuhan bisnis asli (dari brief awal — jangan sampai hilang scope-nya)

**Tujuan utama**: GM dapat "second opinion" berbasis data sebelum ambil keputusan produk/restock/funding/marketing — bukan pengganti keputusan manusia.

**6 modul inti**: Sales, Inventory, Profitability, Marketing, Product Intelligence, Data Reliability.

**AI Assistant** — aturan ketat: cuma kasih rekomendasi, **TIDAK PERNAH** boleh eksekusi aksi (ubah stok, buat order, aktifkan iklan, ubah budget, lakukan pembayaran). Harus bisa sebut kapan data terakhir update kalau relevan ke jawabannya.

**Automasi prioritas**: alert stok rendah/stockout, lonjakan penjualan, data basi, overspend/ROAS rendah iklan, konflik nama/SKU produk, reminder laporan bulanan, reminder pembayaran vendor.

**Data governance** — tiap jenis data idealnya ada "pemilik" yang jelas (stok→Operations, keuangan→Finance, marketing→Marketing, dst) — brief aslinya minta ini ditampilkan, bukan cuma didokumentasikan.

**Pendekatan pengembangan yang disarankan brief asli**: mulai dari data yang rapi → bangun tampilan sederhana → tambah alert → sambungkan AI → **baru PALING TERAKHIR** tambah integrasi real-time ke API eksternal (karena ini bagian paling berisiko/rawan bug, seperti yang terbukti di project ini).

---

*Dokumen ini dibuat 2026-10-13 dari project `pospicc_dashboard-3` (versi Streamlit + Turso + Shopee Open API). Salin/rujuk dokumen ini di awal project baru supaya tidak mengulang proses trial-and-error yang sama.*
