# STATUS

Oxirgi yangilanish: 2026-10-02
Joriy bosqich: 4 — Chunking (3 strategiya), embedding, pgvector + tsvector indekslar
Holat: davom etmoqda

## Tugallangan bosqichlar
- [x] 1 — Repo skeleti, CI, EDGAR fetcher, xom saqlash, xesh, ma'lumot modeli, migratsiyalar (teg: v0.1.0)
- [~] 2 — Extractor, Pydantic sxema, span provenance, validator — kod `main`da (PR #4), **haqiqiy model
  bilan sinalmagan**, teg qo'yilmagan
- [~] 3 — Versiyalash, superseding, idempotentlik, review navbati — kod `main`da (PR #5), **haqiqiy model
  bilan sinalmagan**, teg qo'yilmagan

## 2–3-bosqichni yopish uchun qolgan ish
1. Foydalanuvchi `.env` ga `GEMINI_API_KEY` qo'shadi.
2. `docker compose up -d --build` va `docker compose run --rm api python -m anchor.extract --limit 5`.
   Tekshirish: run'lar `succeeded`, `verified`/`hallucinated` sonlari, narx; ikkinchi ishga tushirishda
   model chaqirilmaydi; `8-K/A` (0001140361-26-035325) asl `8-K` (0001140361-26-015711) ning mos
   faktlarini bosadi (`/facts/{id}/history`).
   Xavf: Gemini `responseJsonSchema` ni yoki `gemini-2.5-flash` nomini qabul qilmasligi mumkin —
   `src/anchor/llm.py` va `LLM_MODEL` sozlamasi.
3. Raqamlarni shu faylga va README'ga yozish, CHANGELOG'da `[0.2.0]`/`[0.3.0]` bo'limlari, teglar.

## Keyingi aniq qadam (4-bosqich)
- `chunk` jadvali, uch chunker (fixed, sentence window, Item chegarasiga sezgir), har bo'lak
  `text[span_start:span_end]` ga teng; lokal CPU embedding; HNSW + GIN indekslar; `anchor.index` buyrug'i.

## Qabul qilingan qarorlar (TZ dan chetlashishlar)
- `chunk`, `query_log`, `eval_result` jadvallari 4–6-bosqichlarga qoldirildi → docs/decisions/001-defer-ask-tables.md
- Model offset emas, so'zma-so'z iqtibos qaytaradi; oraliq kodda hisoblanadi, tozalangan matnga
  nisbatan (`TEXT_VERSION`) → docs/decisions/002-quotes-instead-of-offsets.md
- Idempotentlik kaliti: hujjat + model nomi + prompt + sxema + matn versiyasi (TZ: xesh + prompt +
  model versiyasi). Provayder qaytargan aniq model build'i chaqiruvdan keyingina ma'lum bo'ladi, shuning
  uchun kalitda sozlamadagi model nomi; build `model_version` da saqlanadi.
- Majburiy qayta ajratish (`force`) yo'q: qayta ishlash uchun versiya o'zgartiriladi.
- LLM provayderi: Gemini (bepul tarif), kod provayderga bog'lanmagan.
- Bog'liqliklar `uv` bilan boshqariladi.

## O'lchov natijalari
| Metrika | Qiymat | Sana |
|---|---|---|
| Testlar | 100 o'tdi, ~4 s | 2026-10-02 |
| CI (ruff + pytest) | ~25 s | 2026-10-02 |
| Haqiqiy yuklash, Apple (CIK 320193), 5 hujjat | 1-marta: 5 saqlandi; 2-marta: 0 saqlandi, 0 yuklab olish | 2026-10-02 |
| Xom saqlash hajmi | 5 hujjat = 256 KB | 2026-10-02 |
| HTML → matn, 5 haqiqiy hujjat | 38–73 KB HTML → 3.5–5.2 ming belgi matn | 2026-10-02 |
| `8-K/A` → asl `8-K` bog'lash, haqiqiy juftlik | 1/1 to'g'ri (sana bo'yicha) | 2026-10-02 |

## Ochiq muammolar
- **Eksponatlar yuklanmaydi.** Apple'ning `Item 2.02` hujjatlarida daromad raqamlari asosiy hujjatda
  emas, ilova qilingan press-relizda (Exhibit 99.1). Hozir faqat asosiy hujjat yuklanadi, shuning uchun
  `revenue`, `net_income`, `eps_diluted` maydonlari deyarli bo'sh chiqadi. 6-bosqichdagi oltin to'plamdan
  oldin eksponatlarni yuklashni qo'shish kerak.
- Maydonlararo tekshiruv (jamlanma = qismlar yig'indisi, TZ 4.4) hali yo'q.
- `.claude/settings.json` dagi taqiq tufayli Claude `.env` va `.env.example` ni tahrir qila olmaydi;
  yangi o'zgaruvchilar (`GEMINI_API_KEY`, `LLM_MODEL`) `.env.example` ga qo'lda qo'shilishi kerak.
- Docker Desktop sessiya davomida ikki marta o'zi o'chib qoldi.
