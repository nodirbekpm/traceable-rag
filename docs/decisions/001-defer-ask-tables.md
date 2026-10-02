# 001. `chunk`, `query_log`, `eval_result` jadvallari keyingi bosqichlarga qoldirildi
Sana: 2026-10-02 | Holat: qabul qilindi

## Muammo
TZ 6-bo'limi yetti jadvalni bitta skelet sifatida beradi, `chunk.embedding` esa `vector(1536)` deb
qotirilgan. 1536 — OpenAI embedding o'lchami. Loyiha bepul vositalarda ishlashi shart, ishchi mashinada
CUDA yo'q (AMD RX 570) — lokal CPU modellarining o'lchami odatda 384 yoki 768. O'lcham 4-bosqichda
o'lchov bilan tanlanadi; hozir qotirilsa, keyin ustun turini o'zgartiruvchi migratsiya kerak bo'ladi.

## Ko'rib chiqilgan variantlar
- Yetti jadvalni hozir yaratish, `vector(1536)` bilan — o'lcham o'zgarsa qayta migratsiya.
- `vector` ni o'lchamsiz e'lon qilish — HNSW indeks o'lchamsiz ustunda qurilmaydi.
- Faqat Core jadvallarini yaratish, qolganini egasi bo'lgan bosqichda qo'shish.

## Qaror
1-bosqichda `source_document`, `extraction_run`, `extracted_fact`, `review_queue` yaratiladi.
`chunk` — 4-bosqich, `query_log` — 5-bosqich, `eval_result` — 6-bosqich. `vector` kengaytmasi
birinchi migratsiyada yoqiladi.

Qo'shimcha: `source_document` ga `external_id` (EDGAR accession raqami, UNIQUE) va `publisher_id`
(CIK) qo'shildi — qayta yuklamasdan dublikatni aniqlash uchun.

## Natija
O'lchanadigan tezlik farqi yo'q — bu tartib qarori. Uch va'daga ta'sir qilmaydi: provenance cheklovi
(`verified` holati span'siz yozilmaydi) va `is_current` partial indeksi birinchi migratsiyada bor.
