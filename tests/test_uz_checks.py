# -*- coding: utf-8 -*-
"""Tests for utils/source_checks.py — warnings about defects the pipeline cannot fix.

The fixtures are cut from the three en.wiki articles of the 2026-09-16 batch
that carried such a defect into the translation.
"""

from wikikit.profiles.uz.checks import (
    check_output,
    check_source,
    english_subject_name,
    lead_lacks_dash,
    mixed_script_words,
    year_conflicts,
)

KULAYNI = """{{Short description|Persian Shia hadith collector (864–941 CE)}}
{{Infobox religious biography
| birth_date     = 255 [[Islamic calendar|AH]]<br/>/868 [[Common Era|CE]]
| death_date     = 329 AH<br/>/941 CE
}}
Text.<ref>Baḥr al-ʿUlūm, Sayyid. Edited by Muḥammad Ṣādiq Baḥر al-ʿUlūم. Tehran: Maktabat al-Ṣādiق.</ref>
<ref>Khoei, ''Muʿjam rijāl al-ḥadīث'', vol. 19.</ref>
[[Category:860s births]]
[[Category:941 deaths]]
"""

KHALIL = """{{Infobox religious biography
| birth_date         = 1939''{{small| (1358 AH)}}''
| death_date         = 3 September 2018 <br>{{small|''(23 [[Dhu al-Hijjah]] 1439 AH)''}}
}}
'''Khalil bin Abd al-Rahman al-Qari''' (1939 - 3 September 2018) was ...
[[category:1940 births]]
[[Category:2018 deaths]]
"""

CLEAN = """{{Short description|Pakistani mufti (1951–2022)}}
{{Infobox religious biography
| birth_date = {{Birth date|1951|05|14|df=y}}
| death_date = {{Death date and age|2022|02|27|1951|05|14|df=y}}
| native_name = مفتی محمود اشرف عثمانی
}}
[[Category:1951 births]]
[[Category:2022 deaths]]
"""


class TestMixedScript:
    def test_finds_every_glued_word_once(self):
        assert mixed_script_words(KULAYNI) == [
            "Baḥر", "al-ʿUlūم", "al-Ṣādiق", "al-ḥadīث",
        ]

    def test_arabic_text_on_its_own_is_fine(self):
        assert mixed_script_words(CLEAN) == []

    def test_letter_after_arabic_word(self):
        assert mixed_script_words("محمدx") == ["محمدx"]


class TestYearConflicts:
    def test_short_description_against_infobox(self):
        assert year_conflicts(KULAYNI) == [
            "tugʻilgan yili: qisqa tavsifda 864, bilgiqutida 868",
        ]

    def test_hijri_year_is_not_a_birth_year(self):
        # "255 AH / 868 CE" is 868 only; the decade category 860s agrees.
        assert not any("255" in c for c in year_conflicts(KULAYNI))

    def test_category_against_infobox(self):
        assert year_conflicts(KHALIL) == [
            "tugʻilgan yili: kategoriyada 1940, bilgiqutida 1939",
        ]

    def test_lowercase_category_is_read(self):
        assert year_conflicts(KHALIL.replace("[[category:", "[[Category:")) == year_conflicts(KHALIL)

    def test_consistent_article_has_none(self):
        assert year_conflicts(CLEAN) == []

    def test_years_in_an_infobox_comment_are_ignored(self):
        # Raja ibn Haywa: an empty death_date holding the template's example.
        text = ("{{Infobox person\n| birth_date = {{circa|660}}\n"
                "| death_date = <!-- (e.g., ...|1908|31|8|1967|28|2}}) -->\n}}\n"
                "[[Category:730 deaths]]")
        assert year_conflicts(text) == []

    def test_no_infobox_no_comparison(self):
        assert year_conflicts("{{Short description|X (1900–1950)}}\n[[Category:1901 births]]") == []


class TestEnglishSubjectName:
    RESULT = "'''Mahmood Ashraf Usmani''' (1951-yil 14-may – 2022-yil 27-fevral) — ulamo."

    def test_english_bold_name_is_found(self):
        assert english_subject_name(self.RESULT, "Mahmood Ashraf Usmani") == "Mahmood Ashraf Usmani"

    def test_transliterated_name_passes(self):
        result = self.RESULT.replace("Mahmood Ashraf Usmani", "Mahmud Ashraf Usmoniy")
        assert english_subject_name(result, "Mahmood Ashraf Usmani") is None

    def test_name_spelled_alike_in_both_languages_is_not_flagged(self):
        assert english_subject_name("'''Ahmad Bamba''' — shayx.", "Ahmad Bamba") is None

    def test_disambiguator_is_ignored(self):
        result = "'''Khalil Ahmad''' — olim."
        assert english_subject_name(result, "Khalil Ahmad (scholar)") == "Khalil Ahmad"

    def test_no_title(self):
        assert english_subject_name(self.RESULT, None) is None


class TestMessages:
    def test_source_messages(self):
        messages = check_source(KULAYNI)
        assert len(messages) == 2
        assert messages[0].startswith("Manbada lotin soʻziga arab harfi yopishgan")
        assert "Baḥر" in messages[0]
        assert messages[1] == "Manbada yil ziddiyati — tugʻilgan yili: qisqa tavsifda 864, bilgiqutida 868"

    def test_clean_source_is_silent(self):
        assert check_source(CLEAN) == []

    def test_output_message(self):
        messages = check_output(TestEnglishSubjectName.RESULT, "Mahmood Ashraf Usmani")
        assert messages == [
            "Maqola nomi inglizcha qolgan: '''Mahmood Ashraf Usmani''' — oʻzbekcha transliteratsiya qiling"
        ]


class TestLeadLacksDash:
    def test_uzbek_structure_passes(self):
        text = "{{Bilgiquti}}\n'''Ali''' (1810-yilda tugʻilgan; 1880-yilda vafot etgan) — hind olimi. U ..."
        assert lead_lacks_dash(text) is False

    def test_english_comma_style_is_caught(self):
        # Al-Rabiʼ, 2026-09-17: the model kept the English structure.
        text = ("'''Ar-Rabiʼ ibn Habib al-Farohidiy''' ([[Arab tili|arab tili]]: الربيع), "
                "koʻpincha shunchaki '''Imom ar-Rabiʼ''' deb ataladi, 8-asr olimi edi. U ...")
        assert lead_lacks_dash(text) is True

    def test_no_bracket(self):
        assert lead_lacks_dash("'''Ali''' — olim.") is False

    def test_dash_inside_the_bracket_does_not_count(self):
        assert lead_lacks_dash("'''Ali''' (1810 — 1880) hind olimi edi.") is True

    def test_period_inside_the_bracket_does_not_end_the_sentence(self):
        assert lead_lacks_dash("'''Ali''' (taxm. 868. yil) — olim.") is False

    def test_refs_and_templates_are_ignored(self):
        text = ("'''Ali''' ({{Lang|fa|{{nobr|علی}}}}; 868)<ref>Manba. Ikkinchi gap.</ref> "
                "— [[Forslar|fors]]<ref name=\"x\"/> olimi.")
        assert lead_lacks_dash(text) is False

    def test_no_lead_line(self):
        assert lead_lacks_dash("Matn boshlanadi.") is False

    def test_output_message(self):
        assert check_output("'''Ali''', olim edi.", None) == [
            "Kirish jumlasi 1-qoidaga mos emas: nom va qavsdan keyin «—» yoʻq"
        ]
