# 003. Embedding: lokal CPU modeli, 384 o'lcham; tezlik maqsadi bajarilmadi
Sana: 2026-10-02 | Holat: qabul qilindi (6-bosqichda recall bilan qayta ko'riladi)

## Muammo
TZ: `embedding vector(1536)` (OpenAI o'lchami) va embedding tezligi > 200 bo'lak/soniya.
Loyiha bepul vositalarda ishlashi shart; ishchi mashinada CUDA yo'q (AMD RX 570), Docker ichida GPU yo'q.

## O'lchov (i5-12400, 12 oqim, Docker, o'rtacha bo'lak ~740 belgi)
| Model | O'lcham | batch=4 | batch=32 |
|---|---|---|---|
| BAAI/bge-small-en-v1.5 | 384 | 25 bo'lak/s | 21 bo'lak/s |
| sentence-transformers/all-MiniLM-L6-v2 | 384 | 44 bo'lak/s | 52 bo'lak/s |

Birinchi haqiqiy indekslash (5 hujjat, 3 strategiya, 95 bo'lak, model yuklash bilan): 8.5 s.
O'lchov paytida xostda bo'sh RAM ~2 GB edi — raqamlar pastroq chiqqan bo'lishi mumkin.

## Ko'rib chiqilgan variantlar
- OpenAI embedding API (1536) — pulli.
- Gemini embedding API (bepul tarif) — kunlik chegara, tarmoqqa bog'liq, kalit kerak.
- Lokal ONNX model CPU'da (fastembed) — bepul, kalitsiz, sekinroq.

## Qaror
- `BAAI/bge-small-en-v1.5`, 384 o'lcham, `fastembed` orqali. `chunk.embedding` = `vector(384)`.
- Model nomi sozlama (`EMBEDDING_MODEL`), har bo'lakda `embedding_model` saqlanadi; boshqa o'lchamli
  model uchun migratsiya kerak — kod buni aniq xato bilan aytadi.
- MiniLM ~2 baravar tez, lekin qidiruv uchun maxsus o'qitilmagan. Qaysi biri qolishini tezlik emas,
  6-bosqichdagi recall@5 hal qiladi.

## Natija
- **Maqsad bajarilmadi:** 21–25 bo'lak/s, maqsad > 200. Sabab: GPU yo'q.
- Amaliy ta'sir kichik: 1000 bo'lak ≈ 45 soniya, indekslash bir martalik va idempotent.
- 7-bosqichda sodda choralar sinaladi (ONNX oqim sozlamalari, kvantlangan model, bo'lak uzunligi);
  yetmasa TZ 8-bo'lim tartibida alohida yechim ko'riladi.
