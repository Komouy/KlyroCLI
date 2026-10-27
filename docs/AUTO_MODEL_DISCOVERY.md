# 🌐 KlyroCLI Real-Time Free Model Auto-Discovery

Dokumen ini merinci arsitektur dan spesifikasi teknis untuk fitur **Otomatis Menambah & Memperbarui Model Gratis secara Real-Time** di KlyroCLI.

---

## 🎯 Tujuan Fitur

1. **Zero-Manual Effort**: Pengguna tidak perlu mengecek atau mendaftarkan model AI baru satu per satu ke dalam konfigurasi.
2. **Always Fresh & 100% Free**: Mendeteksi model-model baru yang dirilis oleh penyedia (khususnya OpenRouter Free Tier, Groq, dan Local Ollama) dengan tarif $0.00.
3. **Self-Healing (Auto-Eviction)**: Mengeliminasi model yang sudah mati (*decommissioned* / HTTP 404) agar router dan pengguna tidak mengalami request gagal.
4. **Smart Router Integration**: Otomatis memasukkan model gratis baru ke *candidate pool* Smart Router untuk perutean tugas secara dinamis.

---

## 🏗️ Arsitektur Sistem

```
┌────────────────────────────────────────────────────────┐
│               KlyroCLI Startup Sequence               │
└──────────────────────────┬─────────────────────────────┘
                           │
       (Spawn Non-blocking Daemon Background Thread)
                           ▼
┌────────────────────────────────────────────────────────┐
│           BackgroundModelDiscoveryUpdater              │
│  - Query: https://openrouter.ai/api/v1/models          │
│  - Filter: id.endswith(":free") && pricing == 0        │
│  - Probe: Local Ollama (/api/tags)                     │
│  - Check: Groq / Mistral available endpoints           │
└──────────────────────────┬─────────────────────────────┘
                           │
             (Bandingkan dengan Cache Lokal)
                           │
        ┌──────────────────┴──────────────────┐
        ▼                                     ▼
 [Model Baru Ditemukan]             [Model Kadaluarsa / 404]
        │                                     │
        ▼                                     ▼
 1. Simpan ke live_models_cache.json    1. Masukkan ke dead_models.json
 2. Inject ke PROVIDER_CATALOG         2. Hapus dari Router Pool
 3. Tambahkan ke SmartRouter Pool       3. Reset jika sedang aktif
 4. Tampilkan Badge Halus:
    "✨ 3 Model Gratis Baru Tersedia"
```

---

## 📋 Komponen Utama

### 1. `LiveModelDiscovery` (`core/model_discovery.py`)
* Memanggil endpoint API penyedia secara berkala dengan TTL terkonfigurasi (default: 6 jam).
* Mendeteksi model OpenRouter yang memiliki tag `:free` dan tarif input/output $0.00.
* Menyimpan metadata model (nama, context length, provider, peran model).

### 2. `BackgroundModelUpdater` (Thread Daemon)
* Dijalankan saat CLI inisialisasi tanpa menghambat render UI prompt.
* Jika mendeteksi model baru yang belum ada di katalog sebelumnya, mengirimkan pesan ramah ke antarmuka terminal:
  ```text
  ✨ Auto-Discovery: 3 model gratis baru terdeteksi (DeepSeek R1, Llama 3.3 70B, Gemini 2.0 Flash)
  ```

### 3. Perintah CLI `/cmodel free` & `/cmodel sync`
* `/cmodel free`: Menampilkan filter khusus berisi seluruh model yang 100% gratis saat ini beserta ukuran context window-nya.
* `/cmodel sync`: Memaksa pembaruan katalog langsung dari API saat itu juga (*force refresh*).

---

## ⚙️ Skema Konfigurasi (`klyro_config.json`)

```json
{
  "auto_discover_free_models": true,
  "discovery_interval_hours": 6,
  "prefer_free_models_in_router": true,
  "notify_on_new_models": true
}
```

---

## 🚀 Rencana Rilis
Fitur ini akan diaktifkan secara bertahap:
1. Tahap 1: Penguatan cache dan live query OpenRouter `:free` (sudah tersedia dasar di `core/model_discovery.py`).
2. Tahap 2: Pengaktifan background daemon thread pada `klyro_cli.py`.
3. Tahap 3: Penambahan filter tab interaktif di menu `/cmodel`.
