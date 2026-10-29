# -*- coding: utf-8 -*-
"""Tests for utils/link_labels.py — wikilink label cleanup (rule 2)."""

import pytest

from wikikit.profiles.uz.names import clean_page_title, collapse_redundant_labels, is_same_name


# ── is_same_name: collapse ────────────────────────────────────────────────────

class TestIsSameNameTrue:
    @pytest.mark.parametrize("target,label", [
        ("Muhsin al-Hakim", "Muhsin al-Hakim"),   # identical
        ("Lohur", "Lahor"),                        # vowels differ
        ("Mogadisho", "Mogadishu"),                # final vowel differs
        ("Arabiston yarim oroli", "Arabiston yarimoroli"),   # spacing differs
        ("Abulfaraj Isfahoniy", "Abu al-Faraj al-Isfahoniy"),  # Arabic article
        ("Isʼhoq al-Mavsiliy", "Ishoq al-Mavsiliy"),           # ʼ is insignificant
        ("Qurʼon", "Qur’on"),                      # typographic ’ for ʼ
        ("Oʻzbekiston", "O‘zbekiston"),            # typographic ‘ for ʻ
        ("Oysha", "Oisha"),                        # y as a vowel glide
        ("Mahmud Xalil al-Qori", "Mahmud Xalil al-Qoriy"),     # nisba -i / -iy
    ])
    def test_same_name_collapses(self, target, label):
        assert is_same_name(target, label) is True


# ── is_same_name: keep the pipe ───────────────────────────────────────────────

class TestIsSameNameFalse:
    @pytest.mark.parametrize("target,label,reason", [
        ("Somalilar", "somalilik", "lowercase gloss carries the grammar"),
        ("Tasavvuf", "soʻfiy", "different word"),
        ("Fiqh", "fiqh", "case-only difference lowercases the link"),
        ("Kordova (shahar)", "Kordova", "rule 2 parenthetical exception"),
        ("Panjob (viloyat)", "Panjob (Pokiston)", "parenthetical on both sides"),
        ("Oʻn ikki imom", "Oʻn ikki imomiy", "derived adjective"),
        ("Qojarlar sulolasi", "Qojarlar", "label is an ellipsis"),
        ("Rizoshoh Pahlaviy", "Rezo Shoh", "shortened name"),
        ("Fors ustoni", "Fors viloyati", "different word"),
        ("Bengaliya", "Bengal", "different form"),
        ("Shialik", "Shia", "different form"),
        ("Yusuf", "Usuf", "initial y is a consonant"),
        ("Sahihi Buxoriy", "Sahih al-Buxoriy", "different word form"),
        ("Kalkutta", "Kolkata", "different consonants"),
        ("File:Rasm.jpg", "thumb|Izoh", "file link, not a name"),
        ("Turkum:Olimlar", "Olimlar", "namespace prefix"),
        (":fa:نظام‌العلما", "forscha muqobili", "interwiki prefix"),
    ])
    def test_different_name_keeps_pipe(self, target, label, reason):
        assert is_same_name(target, label) is False, reason


# ── collapse_redundant_labels ─────────────────────────────────────────────────

class TestCollapseRedundantLabels:
    def test_collapses_and_keeps_suffix(self):
        text, _ = collapse_redundant_labels("U [[Lohur|Lahor]]ga koʻchdi.")
        assert text == "U [[Lohur]]ga koʻchdi."

    def test_keeps_grammatical_label(self):
        text = "14-asr [[Somalilar|somalilik]] [[olim]]i."
        assert collapse_redundant_labels(text)[0] == text

    def test_leaves_plain_link_alone(self):
        text = "[[Mogadisho]] shahri."
        assert collapse_redundant_labels(text)[0] == text

    def test_file_link_untouched(self):
        text = "[[File:Rasm.jpg|thumb|Izoh matni.]]"
        assert collapse_redundant_labels(text)[0] == text

    def test_reports_undecidable_mismatch(self):
        _, bad = collapse_redundant_labels("[[Rizoshoh Pahlaviy|Rezo Shoh]] davri.")
        assert bad == [("Rizoshoh Pahlaviy", "Rezo Shoh")]

    def test_does_not_report_lowercase_gloss(self):
        _, bad = collapse_redundant_labels("[[Tasavvuf|soʻfiy]] tariqati.")
        assert bad == []

    def test_does_not_report_parenthetical(self):
        _, bad = collapse_redundant_labels("[[Madina (shahar)|Madina]]da.")
        assert bad == []

    def test_report_is_deduplicated(self):
        _, bad = collapse_redundant_labels(
            "[[Fors ustoni|Fors viloyati]] va [[Fors ustoni|Fors viloyati]]."
        )
        assert bad == [("Fors ustoni", "Fors viloyati")]

    def test_whitespace_around_target_is_trimmed(self):
        text, _ = collapse_redundant_labels("[[ Lohur | Lahor ]]")
        assert text == "[[Lohur]]"

    def test_empty_text_unchanged(self):
        assert collapse_redundant_labels("")[0] == ""


# ── italic labels ─────────────────────────────────────────────────────────────

class TestItalicLabel:
    def test_italics_move_outside_the_collapsed_link(self):
        text, mismatches = collapse_redundant_labels("* [[Kitob al-Kofiy|''Kitab al Kafiy'']]")
        assert text == "* ''[[Kitob al-Kofiy]]''"
        assert mismatches == []

    def test_italic_label_of_another_name_is_kept(self):
        text = "[[Kitob al-Kofiy|''Usul al-Kofiy'']]"
        assert collapse_redundant_labels(text)[0] == text


# ── clean_page_title ──────────────────────────────────────────────────────────

class TestCleanPageTitle:
    @pytest.mark.parametrize("raw,expected", [
        ("''Kitāb al Kāfī''", "Kitab al Kafiy"),        # italics and diacritics
        ("axboriy", "Axboriy"),                          # first letter capitalised
        ("oʻn ikki imom", "Oʻn ikki imom"),              # Uzbek letter survives
        ("Shoh Muḥammad Isḥoq  Dehlaviy", "Shoh Muhammad Ishoq Dehlaviy"),
        ("Dilovar Xon (siyosatchi)", "Dilovar Xon (siyosatchi)"),
    ])
    def test_cleans(self, raw, expected):
        assert clean_page_title(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "''", "a|b", "[[X]]", "Kitob#bob"])
    def test_rejects_unusable(self, raw):
        assert clean_page_title(raw) is None


class TestReferencesUntouched:
    def test_link_in_a_reference_is_not_collapsed(self):
        text = "[[Lohur|Lahor]]da<ref>{{cite book |location=[[Lohur|Lahor]]}}</ref>"
        cleaned, _ = collapse_redundant_labels(text)
        assert cleaned == "[[Lohur]]da<ref>{{cite book |location=[[Lohur|Lahor]]}}</ref>"

    def test_english_label_in_a_citation_is_not_reported(self):
        text = "Matn<ref>{{cite book |location=[[Lohur|Lahore]]}}</ref>"
        assert collapse_redundant_labels(text)[1] == []
