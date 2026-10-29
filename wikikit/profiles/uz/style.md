# Oʻzbekcha Vikipediya — tarjima uslubi

Bu fayl tarjimon agentga (`agents/translator.md`) beriladi. Placeholder qoidalari
(`[[Q…|…]]`, `[[LNK…|…]]`, `⟦CAT:…⟧`, `{{TPL:…}}`, `REF_…`, `CITE_…`) agentning oʻz
yoʻriqnomasida — bu yerda faqat oʻzbek tiliga xos qoidalar.

Bu qoidalar `wikipedia-translator` loyihasida har kuni nashr qilingan maqolalarda
sinovdan oʻtgan. Sana, AH/CE, `-lik` qoʻshimchasi, transliteratsiya va manba atrofidagi
tinish belgilari keyin kod bilan ham tuzatiladi (`fixers.py`), lekin toʻgʻri yozilgani
maʼqul.

## 1. Kirish jumlasi
Tuzilishi: `'''Ism''' (maʼlumotlar; muqobil nomlar) — taʼrif`.
Qavsdan keyin em-dash (—) qoʻyiladi; inglizcha vergul uslubi emas. Taʼrif bitta jumla —
uni nuqta bilan boʻlmang, manba belgisidan (`<ref>`) keyin ham.

- Notoʻgʻri: `'''Ismoil ibn Abdurahmon''' (1043-yilda vafot etgan), '''Ismoil az-Zafir''' nomi bilan ham tanilgan, Toledo taifasining birinchi hukmdori`
- Toʻgʻri: `'''Ismoil ibn Abdurahmon''' (1043-yilda vafot etgan; '''Ismoil az-Zafir''' nomi bilan ham tanilgan) — Toledo taifasining birinchi hukmdori`
- Notoʻgʻri: `'''Ahmad Aliy''' (1810 – 1880-yil 17-aprel) — hind olimi`
- Toʻgʻri: `'''Ahmad Aliy''' (1810-yilda tugʻilgan; 1880-yil 17-aprelda vafot etgan) — hind olimi`

## 2. Maqola mavzusining nomi
Bold lead nomi va bilgiqutidagi `name =` qiymati oʻzbekcha transliteratsiya qilinadi va
butun matnda aynan bir xil yoziladi. Inglizcha shakl qoldirilmaydi.

- Notoʻgʻri: `'''Mahmood Ashraf Usmani''' ... Usmoniy 1970-yilda ...`
- Toʻgʻri: `'''Mahmud Ashraf Usmoniy''' ... Usmoniy 1970-yilda ...`

Ismlarni transliteratsiya qilish (matndagi barcha ismlar uchun):
- w → v (Wajihuddin → Vajihuddin); diakritikalar olib tashlanadi (ā → a, ḥ → h, ʿ yozilmaydi);
- arabcha nisba -iy bilan tugaydi (Siddiqi → Siddiqiy, al-Qari → al-Qoriy);
- arabcha artikl quyosh harflariga moslashadi (al-Razi → ar-Roziy);
- joy nomi havolada qanday yozilgan boʻlsa, matnda ham shunday (`[[Q11739|Lohur]]` boʻlsa, matnda ham "Lohurda").

## 3. Havola matnlari
`[[Q…|matn]]` va `[[LNK…|matn]]` dagi koʻrinadigan matn HAR DOIM oʻzbekcha — manbada
diakritikali, kursivli yoki inglizcha nom boʻlsa ham (`Kitāb al-Kāfī` → `Kitob al-Kofiy`,
`Four Deputies` → `toʻrt noib`).

## 4. Sanalar
- Yil "hijriy"/"milodiy" soʻzidan keyin, `-yil` qoʻshimchasi bilan: `132 hijriy/750 milodiy` → `hijriy 132-yil/milodiy 750-yil`.
- AH, CE, AD (havola koʻrinishida ham) qoldirilmaydi: `255 [[Q28892|AH]]` → `hijriy 255-yil`.
- Toʻliq sana oʻzbekcha tartibda, bilgiqutida ham: `3 September 2018` → `2018-yil 3-sentyabr`.
- Manbada boʻlmagan sanani qoʻshmang: faqat "1301" boʻlsa, hijriy muqobilini hisoblamang.

## 5. Geografik nomlar
Jumla ichida inglizcha "Shahar, Shtat, Mamlakat" tartibi oʻzbekcha egalik qurilishiga aylanadi:
- Notoʻgʻri: `U Damashq, Suriyada yashagan` → Toʻgʻri: `U Suriyaning Damashq shahrida yashagan`
Bilgiquti qiymatlarida tartib oʻz holicha qoladi.

## 6. Boʻlim sarlavhalari
- Biography, Life → Hayoti
- Early life → Yoshligi
- See also → Yana qarang
- References, Notes, Citations → Manbalar
- Bibliography → Adabiyotlar
- Further reading → Qoʻshimcha oʻqish uchun
- External links → Havolalar

## 7. Andoza qiymatlari
Bilgiquti parametrlarining qiymatlari tarjima qilinadi. URL, fayl nomi, raqamlar,
arabcha/forscha/urducha yozuv va `native_name` oʻzgarmaydi. Parametr nomlari (`birth_date`)
oʻzgarmaydi.

## 8. uz.wiki'da maqolasi yoʻq havolalar (LNK nomlari)
Har bir `LNK` uchun oʻzbekcha **sahifa nomi** kerak (qizil havola boʻlishi normal):
1. Kishi ismi — transliteratsiya: `Syed Ahmad Khan` → `Sayyid Ahmad Xon`, `Rashiq al-Nasimi` → `Roshiq an-Nasimiy`.
2. Tushuncha, asar, tashkilot — tarjima: `Treaty of Safar` → `Safar shartnomasi`, `University of Sindh` → `Sind universiteti`.
3. Joy — qabul qilingan shakl: `Lahore` → `Lohur`, `Muzaffarabad` → `Muzaffarobod`.
4. Qavsdagi aniqlashtiruvchi ham tarjima qilinadi: `Dilawar Khan (politician)` → `Dilovar Xon (siyosatchi)`.
5. Sahifa nomi bosh harf bilan; kursiv, qoʻshtirnoq, unvon (shayx, imom, mavlono), kelishik va egalik qoʻshimchalarisiz.
6. Ism maqola matnida qanday yozilgan boʻlsa, sahifa nomida ham aynan shunday (matnda "Muhammad Qosim Nanautaviy" → nom ham `Muhammad Qosim Nanautaviy`, "Nanutaviy" emas).

## 9. Tutuq belgisi va oʻ/gʻ
`ʻ` (U+02BB) va `ʼ` (U+02BC) toʻgʻri harflar. Ammo ‘/’ yozilib qolsa ham **tuzatish
kerak emas** — uz.wiki'dagi Vikifikator saqlash paytida oʻzi almashtiradi.
