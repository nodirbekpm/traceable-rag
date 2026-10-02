# 002. Model belgi raqamini emas, so'zma-so'z iqtibos qaytaradi
Sana: 2026-10-02 | Holat: qabul qilindi (o'lchov 6-bosqichda)

## Muammo
TZ 4.2: "har bir qiymat bilan birga model manba oralig'ini qaytarishi shart". Til modellari belgilarni
sanashda ishonchsiz — `span_start`/`span_end` ni to'g'ridan-to'g'ri so'rasak, raqamlar tez-tez
noto'g'ri chiqadi va to'g'ri qiymat ham "topilmadi" deb rad etiladi.

Ikkinchi savol: oraliq nimaga nisbatan? Xom fayl HTML — undagi belgi raqami o'quvchi ko'radigan
matnga to'g'ri kelmaydi.

## Ko'rib chiqilgan variantlar
- Modeldan `span_start`/`span_end` so'rash — sanash xatolari.
- Matnni raqamlangan qatorlarga bo'lib, qator raqamini so'rash — oraliq qo'pol (butun qator).
- Modeldan so'zma-so'z iqtibos (`quote`) so'rash, oraliqni kodda hisoblash.

## Qaror
- Model `value` va uni o'z ichiga olgan `quote` qaytaradi. Oraliqni `provenance.locate` haqiqiy
  matndan topadi: avval aynan mos, bo'lmasa bo'shliq va tirnoq/chiziq turiga bag'rikeng qidiruv
  (bunda ishonch 0.9 ga ko'paytiriladi).
- Iqtibos topilmasa yoki qiymat iqtibos ichida bo'lmasa — `hallucinated`, oraliqsiz saqlanadi.
- `span_start`/`span_end` qiymatning o'ziga, `source_excerpt` iqtibosga ishora qiladi.
- Oraliqlar `html_to_text` chiqargan matnga nisbatan. O'zgartirish algoritmi `TEXT_VERSION` bilan
  versiyalangan va har `extraction_run` da yoziladi; xom baytlar o'zgarmas saqlangani uchun matn
  istalgan payt qayta tiklanadi.

## Natija
Provenance va'dasi kuchaydi: oraliq modelning da'vosi emas, kodning tekshiruvi. Raqamli taqqoslash
(to'g'ridan-to'g'ri offset so'rash bilan) 6-bosqichdagi ekstraksiya oltin to'plamida o'lchanadi —
hozircha o'lchov yo'q.
