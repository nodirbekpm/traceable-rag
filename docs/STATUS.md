# STATUS

Oxirgi yangilanish: 2026-10-02
Joriy bosqich: 5 — Gibrid qidiruv, reranking, javob qatlami, sitata tekshiruvi, streaming, kesh
Holat: boshlanmagan (avval 2–3-bosqichni haqiqiy model bilan yopish kerak)

## Tugallangan bosqichlar
- [x] 1 — Repo skeleti, CI, EDGAR fetcher, xom saqlash, xesh, ma'lumot modeli, migratsiyalar (teg: v0.1.0)
- [~] 2 — Extractor, Pydantic sxema, span provenance, validator — kod `main`da (PR #4), **haqiqiy model
  bilan sinalmagan**, teg qo'yilmagan
- [~] 3 — Versiyalash, superseding, idempotentlik, review navbati — kod `main`da (PR #5), **haqiqiy model
  bilan sinalmagan**, teg qo'yilmagan

- [x] 4 — Chunking (3 strategiya), embedding, pgvector + tsvector indekslar — `main`da (PR #6), haqiqiy
  hujjatlarda sinalgan; teg 2–3-bosqich yopilgach ketma-ket qo'yiladi

## 2–3-bosqichni yopish uchun qolgan ish
1. Foydalanuvchi `.env` ga `GEMINI_API_KEY` qo'shadi.
2. `docker compose up -d --build` va `docker compose run --rm api python -m anchor.extract --limit 5`.
   Tekshirish: run'lar `succeeded`, `verified`/`hallucinated` sonlari, narx; ikkinchi ishga tushirishda
   model chaqirilmaydi; `8-K/A` (0001140361-26-035325) asl `8-K` (0001140361-26-015711) ning mos
   faktlarini bosadi (`/facts/{id}/history`).
   Xavf: Gemini `responseJsonSchema` ni yoki `gemini-2.5-flash` nomini qabul qilmasligi mumkin —
   `src/anchor/llm.py` va `LLM_MODEL` sozlamasi.
3. Raqamlarni shu faylga va README'ga yozish, CHANGELOG'da `[0.2.0]`/`[0.3.0]` bo'limlari, teglar.

## Keyingi aniq qadam (5-bosqich)
- Gibrid qidiruv: vektor (HNSW) + matn (`tsvector`) → RRF; uchala rejim alohida chaqiriladigan bo'lsin
  (6-bosqichda taqqoslanadi). Reranking (cross-encoder, lokal). Javob qatlami: LLM, oqim (SSE), har
  da'voga sitata, sitata tekshiruvi (`provenance.locate` qayta ishlatiladi), "topilmadi" javobi,
  Redis kesh, `query_log` jadvali.

## Qabul qilingan qarorlar (TZ dan chetlashishlar)
- `chunk`, `query_log`, `eval_result` jadvallari 4–6-bosqichlarga qoldirildi → docs/decisions/001-defer-ask-tables.md
- Model offset emas, so'zma-so'z iqtibos qaytaradi; oraliq kodda hisoblanadi, tozalangan matnga
  nisbatan (`TEXT_VERSION`) → docs/decisions/002-quotes-instead-of-offsets.md
- Idempotentlik kaliti: hujjat + model nomi + prompt + sxema + matn versiyasi (TZ: xesh + prompt +
  model versiyasi). Provayder qaytargan aniq model build'i chaqiruvdan keyingina ma'lum bo'ladi, shuning
  uchun kalitda sozlamadagi model nomi; build `model_version` da saqlanadi.
- Majburiy qayta ajratish (`force`) yo'q: qayta ishlash uchun versiya o'zgartiriladi.
- LLM provayderi: Gemini (bepul tarif), kod provayderga bog'lanmagan.
- Embedding: lokal CPU modeli `BAAI/bge-small-en-v1.5`, 384 o'lcham (TZ: 1536) → docs/decisions/003-local-cpu-embeddings.md
- Bog'liqliklar `uv` bilan boshqariladi.

## O'lchov natijalari
| Metrika | Qiymat | Sana |
|---|---|---|
| Testlar | 123 o'tdi, ~5 s | 2026-10-02 |
| CI (ruff + pytest) | ~25 s | 2026-10-02 |
| Haqiqiy yuklash, Apple (CIK 320193), 5 hujjat | 1-marta: 5 saqlandi; 2-marta: 0 saqlandi, 0 yuklab olish | 2026-10-02 |
| Xom saqlash hajmi | 5 hujjat = 256 KB | 2026-10-02 |
| HTML → matn, 5 haqiqiy hujjat | 38–73 KB HTML → 3.5–5.2 ming belgi matn | 2026-10-02 |
| `8-K/A` → asl `8-K` bog'lash, haqiqiy juftlik | 1/1 to'g'ri (sana bo'yicha) | 2026-10-02 |
| Bo'laklash, 5 haqiqiy hujjat | fixed 33, sentence 35, section 27 bo'lak (o'rtacha 761 / 667 / 805 belgi) | 2026-10-02 |
| Embedding tezligi, bge-small, CPU | 21–25 bo'lak/s (maqsad > 200 — **bajarilmadi**) | 2026-10-02 |
| Embedding tezligi, all-MiniLM-L6-v2, CPU | 44–52 bo'lak/s | 2026-10-02 |
| Qayta indekslash | 0 bo'lak, 0.1 s | 2026-10-02 |
| Docker image hajmi | 596 MB | 2026-10-02 |

## Ochiq muammolar
- **Eksponatlar yuklanmaydi.** Apple'ning `Item 2.02` hujjatlarida daromad raqamlari asosiy hujjatda
  emas, ilova qilingan press-relizda (Exhibit 99.1). Hozir faqat asosiy hujjat yuklanadi, shuning uchun
  `revenue`, `net_income`, `eps_diluted` maydonlari deyarli bo'sh chiqadi. 6-bosqichdagi oltin to'plamdan
  oldin eksponatlarni yuklashni qo'shish kerak.
- Maydonlararo tekshiruv (jamlanma = qismlar yig'indisi, TZ 4.4) hali yo'q.
- `.claude/settings.json` dagi taqiq tufayli Claude `.env` va `.env.example` ni tahrir qila olmaydi;
  yangi o'zgaruvchilar (`GEMINI_API_KEY`, `LLM_MODEL`) `.env.example` ga qo'lda qo'shilishi kerak.
- Docker Desktop sessiya davomida uch marta o'zi o'chib qoldi; xostda bo'sh RAM ~2 GB edi. Baza
  buyruqlari osilib qolsa birinchi navbatda `docker info` ni tekshirish.
- Korpus juda kichik (5 hujjat, 95 bo'lak) — indeks va tezlik o'lchovlari uchun ko'proq kompaniya yuklash kerak.
