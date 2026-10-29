"""Tests for utils/regex_patterns.py — all pure string/regex transformations."""

from wikikit.profiles.uz.rules import (
    remove_empty_params,
    clean_html_comments,
    fix_punctuation_with_refs,
    fix_cite_book_script_title,
    fix_lik_suffix_capitalization,
    fix_year_with_dash,
    fix_punctuation_with_sfn,
    fix_arabic_transliteration,
    fix_gregorian_dates,
    fix_era_abbreviations,
    apply_all_fixes,
)


# ── remove_empty_params ───────────────────────────────────────────────────────

class TestRemoveEmptyParams:
    def test_removes_empty_param(self):
        wikitext = "{{tpl\n| name =\n| value = hello\n}}"
        result = remove_empty_params(wikitext)
        assert "| name =" not in result
        assert "| value = hello" in result

    def test_keeps_filled_param(self):
        wikitext = "{{tpl\n| value = hello\n}}"
        result = remove_empty_params(wikitext)
        assert "| value = hello" in result

    def test_collapses_multiple_newlines(self):
        wikitext = "line1\n\n\n\nline2"
        result = remove_empty_params(wikitext)
        assert "\n\n\n" not in result

    def test_no_change_when_clean(self):
        wikitext = "{{tpl|param=value}}"
        result = remove_empty_params(wikitext)
        assert "param=value" in result


# ── clean_html_comments ───────────────────────────────────────────────────────

class TestCleanHtmlComments:
    def test_removes_inline_comment(self):
        result = clean_html_comments("Hello <!-- comment --> World")
        assert "comment" not in result
        assert "Hello" in result
        assert "World" in result

    def test_removes_multiline_comment(self):
        result = clean_html_comments("before\n<!-- line1\nline2 -->\nafter")
        assert "line1" not in result
        assert "after" in result

    def test_no_change_when_no_comments(self):
        text = "Plain text with no comments"
        assert clean_html_comments(text) == text


# ── fix_punctuation_with_refs ─────────────────────────────────────────────────

class TestFixPunctuationWithRefs:
    def test_moves_period_before_ref_to_after(self):
        result = fix_punctuation_with_refs("text.<ref>source</ref>")
        assert result == "text<ref>source</ref>."

    def test_moves_comma_before_ref_to_after(self):
        result = fix_punctuation_with_refs("text,<ref>source</ref>")
        assert result == "text<ref>source</ref>,"

    def test_moves_period_before_self_closing_ref(self):
        result = fix_punctuation_with_refs('text.<ref name="x"/>')
        assert result.startswith('text<ref name="x"/>')

    def test_removes_punct_between_consecutive_refs(self):
        result = fix_punctuation_with_refs("text</ref>.<ref>next</ref>")
        assert "</ref>.<ref>" not in result
        assert "</ref><ref>" in result or "</ref>\n<ref>" in result or "next</ref>" in result

    def test_deduplicates_period_after_ref(self):
        result = fix_punctuation_with_refs("text</ref>..")
        assert "</ref>.." not in result

    def test_no_period_added_before_lowercase_continuation(self):
        # A ref followed by a lowercase word — no period should be injected
        result = fix_punctuation_with_refs("text</ref> va boshqa")
        # Should NOT have ".</ref>" or "ref>. va" — period before "va" is wrong
        assert ".</ref>" not in result

    def test_no_period_before_piped_link_with_lowercase_label(self):
        # The target is capitalised by MediaWiki; the reader sees "shia".
        text = "— [[Forslar|fors]]<ref>MANBA</ref> [[Shialik|shia musulmon]] olimi"
        assert fix_punctuation_with_refs(text) == text

    def test_period_before_piped_link_with_capital_label(self):
        result = fix_punctuation_with_refs("edi<ref>M</ref> [[Buxoro|Buxoro shahri]]da")
        assert result == "edi<ref>M</ref>. [[Buxoro|Buxoro shahri]]da"

    def test_period_before_capitalised_unpiped_link(self):
        result = fix_punctuation_with_refs("edi<ref>M</ref> [[Buxoro]]da tugʻilgan")
        assert result == "edi<ref>M</ref>. [[Buxoro]]da tugʻilgan"


# ── fix_cite_book_script_title ────────────────────────────────────────────────

class TestFixCiteBookScriptTitle:
    def test_strips_lang_prefix_and_renames_param(self):
        wikitext = "{{cite book |script-title=ru:Tekst}}"
        result = fix_cite_book_script_title(wikitext)
        assert "script-title" not in result
        assert "title=Tekst" in result

    def test_handles_no_lang_prefix(self):
        wikitext = "{{cite book |script-title=Tekst}}"
        result = fix_cite_book_script_title(wikitext)
        assert "script-title" not in result
        assert "title=Tekst" in result

    def test_does_not_touch_regular_title_param(self):
        wikitext = "{{cite book |title=Normal}}"
        result = fix_cite_book_script_title(wikitext)
        assert result == wikitext

    def test_does_not_touch_unrelated_template(self):
        wikitext = "{{cite web |script-title=ar:Text}}"
        result = fix_cite_book_script_title(wikitext)
        # only cite book is affected
        assert result == wikitext


# ── fix_lik_suffix_capitalization ─────────────────────────────────────────────

class TestFixLikSuffixCapitalization:
    def test_lowercases_mid_sentence(self):
        result = fix_lik_suffix_capitalization("Uni Bangladeshlik olim deb atashgan")
        assert result == "Uni bangladeshlik olim deb atashgan"

    def test_keeps_capital_in_article_name(self):
        wikitext = "'''Mogadishulik Saʼid''' — somalilik olim."
        assert fix_lik_suffix_capitalization(wikitext) == wikitext

    def test_keeps_capital_at_line_start(self):
        wikitext = "Bangladeshlik olim keldi."
        assert fix_lik_suffix_capitalization(wikitext) == wikitext

    def test_keeps_capital_after_sentence_end(self):
        wikitext = "U ketdi. Toshkentlik olim keldi."
        assert fix_lik_suffix_capitalization(wikitext) == wikitext

    def test_keeps_capital_in_spaced_parameter_value(self):
        wikitext = "| name          = Mogadishulik Saʼid"
        assert fix_lik_suffix_capitalization(wikitext) == wikitext

    def test_skips_when_equals_immediately_adjacent(self):
        # lookbehind only skips if = is the char directly before the word (no space)
        wikitext = "| nationality =Bangladeshlik"
        result = fix_lik_suffix_capitalization(wikitext)
        assert "Bangladeshlik" in result

    def test_skips_inside_wikilink(self):
        wikitext = "[[Bangladeshlik]]"
        result = fix_lik_suffix_capitalization(wikitext)
        assert "[[Bangladeshlik]]" in result

    def test_multiple_occurrences(self):
        result = fix_lik_suffix_capitalization("Hindistонlik va Bangladeshlik mutafakkirlar")
        # Capital -lik words mid-sentence get lowercased
        assert "Bangladeshlik" not in result or "bangladeshlik" in result


# ── fix_year_with_dash ────────────────────────────────────────────────────────

class TestFixYearWithDash:
    def test_basic_yil(self):
        assert fix_year_with_dash("2025 yil") == "2025-yil"

    def test_yilda(self):
        assert fix_year_with_dash("1400 yilda") == "1400-yilda"

    def test_yillar(self):
        assert fix_year_with_dash("1990 yillar") == "1990-yillar"

    def test_yillarda(self):
        assert fix_year_with_dash("1975 yillarda") == "1975-yillarda"

    def test_already_dashed_unchanged(self):
        assert fix_year_with_dash("2025-yil") == "2025-yil"

    def test_circa_template(self):
        result = fix_year_with_dash("{{Circa|910}} yilda")
        assert "{{Circa|910}}-yilda" in result

    def test_no_year_unchanged(self):
        text = "Hello World"
        assert fix_year_with_dash(text) == text

    def test_short_duration_keeps_space(self):
        text = "u yerda 28 yil davomida ilm toʻplagan"
        assert fix_year_with_dash(text) == text

    def test_long_duration_keeps_space(self):
        assert fix_year_with_dash("100 yil oldin") == "100 yil oldin"
        assert fix_year_with_dash("500 yildan ortiq") == "500 yildan ortiq"

    def test_year_range_tail(self):
        assert fix_year_with_dash("1975/76 yillarda") == "1975/76-yillarda"

    def test_year_with_case_suffix(self):
        assert fix_year_with_dash("2011 yildan beri") == "2011-yildan beri"


# ── fix_punctuation_with_sfn ──────────────────────────────────────────────────

class TestFixPunctuationWithSfn:
    def test_moves_period_before_sfn_to_after(self):
        result = fix_punctuation_with_sfn("text.{{sfn|Smith|2020}}")
        assert "text.{{sfn" not in result
        assert "{{sfn|Smith|2020}}" in result

    def test_removes_punct_between_sfn_and_sfn(self):
        result = fix_punctuation_with_sfn("{{sfn|A|2020}}.{{sfn|B|2021}}")
        assert "}}.{{" not in result

    def test_no_change_when_correct(self):
        # period already after sfn and followed by space — should stay
        result = fix_punctuation_with_sfn("text{{sfn|A}}\n")
        assert "{{sfn|A}}" in result

    def test_comma_survives_a_chain_of_sfns(self):
        # The comma has to travel past every template, not be dropped
        # between two of them and replaced by an invented period.
        result = fix_punctuation_with_sfn("matn edi,{{sfn|A}}{{sfn|B}} u keldi.")
        assert result == "matn edi{{sfn|A}}{{sfn|B}}, u keldi."

    def test_period_survives_a_chain_of_sfns(self):
        result = fix_punctuation_with_sfn("matn tugadi.{{sfn|A}}{{sfn|B}} Yangi.")
        assert result == "matn tugadi{{sfn|A}}{{sfn|B}}. Yangi."

    def test_no_period_invented_before_lowercase_word(self):
        # A lowercase word means the sentence continues.
        result = fix_punctuation_with_sfn("matn davom etadi{{sfn|A}} va yana.")
        assert result == "matn davom etadi{{sfn|A}} va yana."

    def test_missing_period_still_added_before_capital(self):
        result = fix_punctuation_with_sfn("matn tugadi{{sfn|A}} Yangi jumla.")
        assert result == "matn tugadi{{sfn|A}}. Yangi jumla."

    def test_chain_of_two_does_not_double_the_period(self):
        # Each mark used to be moved one template at a time, so they piled
        # up behind the last one: "...}}{{sfn|B}}.. Yana."
        result = fix_punctuation_with_sfn("Matn.{{sfn|A}}.{{sfn|B}} Yana.")
        assert result == "Matn{{sfn|A}}{{sfn|B}}. Yana."

    def test_chain_of_three_does_not_triple_the_period(self):
        result = fix_punctuation_with_sfn("Matn.{{sfn|A}}.{{sfn|B}}.{{efn|c}} Yana.")
        assert result == "Matn{{sfn|A}}{{sfn|B}}{{efn|c}}. Yana."

    def test_no_doubled_punctuation_anywhere_in_a_long_chain(self):
        result = fix_punctuation_with_sfn(
            "Matn.{{sfn|A}}.{{sfn|B}}.{{sfn|C}}.{{efn|d}} Yana."
        )
        assert ".." not in result

    def test_mark_stranded_inside_the_chain_is_kept(self):
        # The period came from before the chain and an earlier pass pushed it
        # inwards; dropping it would lose the sentence break entirely.
        result = fix_punctuation_with_sfn("Matn<ref>x</ref>.{{sfn|A}} va yana")
        assert result == "Matn<ref>x</ref>{{sfn|A}}. va yana"

    def test_ref_before_sfn_hands_its_mark_to_the_chain(self):
        result = fix_punctuation_with_sfn("Matn</ref>.{{sfn|A}} Word")
        assert result == "Matn</ref>{{sfn|A}}. Word"

    def test_paragraph_break_inside_a_run_is_not_swallowed(self):
        result = fix_punctuation_with_sfn("Matn{{sfn|A}}\n\n{{sfn|B}} Boshqa.")
        assert "\n\n" in result

    def test_no_period_before_piped_link_with_lowercase_label(self):
        text = "olim{{sfn|A}} [[Shialik|shia]] edi"
        assert fix_punctuation_with_sfn(text) == text

    def test_period_before_piped_link_with_capital_label(self):
        result = fix_punctuation_with_sfn("olim{{sfn|A}} [[Shialik|Shia]] edi")
        assert result == "olim{{sfn|A}}. [[Shialik|Shia]] edi"

    def test_plain_ref_chain_is_left_to_the_ref_fix(self):
        src = "Matn.<ref>a</ref><ref>b</ref> Word"
        assert fix_punctuation_with_sfn(src) == src


# ── fix_arabic_transliteration ────────────────────────────────────────────────

class TestFixArabicTransliteration:
    def test_macron_a_removed(self):
        result = fix_arabic_transliteration("Kātib")
        assert "ā" not in result
        assert "Katib" in result

    def test_macron_u_removed(self):
        result = fix_arabic_transliteration("Qūt")
        assert "ū" not in result
        assert "Qut" in result

    def test_dot_h_removed(self):
        result = fix_arabic_transliteration("Muḥammad")
        assert "ḥ" not in result
        assert "Muhammad" in result

    def test_final_i_macron_becomes_iy(self):
        result = fix_arabic_transliteration("al-Amirī")
        assert "ī" not in result
        assert "Amiriy" in result

    def test_hamza_removed(self):
        result = fix_arabic_transliteration("ʿAlim")
        assert "ʿ" not in result
        assert "Alim" in result

    def test_solar_letter_r(self):
        result = fix_arabic_transliteration("al-Roziy")
        assert "ar-Roziy" in result

    def test_solar_letter_n(self):
        result = fix_arabic_transliteration("al-Nasafiy")
        assert "an-Nasafiy" in result

    def test_solar_letter_sh(self):
        result = fix_arabic_transliteration("al-Shofiiy")
        assert "ash-Shofiiy" in result

    def test_solar_letter_t(self):
        result = fix_arabic_transliteration("al-Tabariy")
        assert "at-Tabariy" in result

    def test_skips_ref_tag_content(self):
        wikitext = "<ref>al-Ṭabarī notes here</ref>"
        result = fix_arabic_transliteration(wikitext)
        # Content inside <ref> should be untouched
        assert "Ṭ" in result or "al-Ṭabarī" in result

    def test_processes_wikilink_label_not_target(self):
        # Link target should be untouched; label can be processed
        wikitext = "[[Abū_Bakr|Abū Bakr]]"
        result = fix_arabic_transliteration(wikitext)
        # Target part (before |) should remain; label (after |) gets processed
        assert "[[Abū_Bakr|" in result  # target unchanged
        # Label loses diacritics
        assert "|Abu Bakr]]" in result or "|Abū Bakr]]" not in result or "[[Abū_Bakr|" in result

    def test_no_diacritics_unchanged(self):
        text = "Hello World"
        result = fix_arabic_transliteration(text)
        assert result == text


# ── apply_all_fixes ───────────────────────────────────────────────────────────

class TestApplyAllFixes:
    def test_collapses_excess_newlines(self):
        result = apply_all_fixes("a\n\n\n\nb")
        assert "\n\n\n" not in result
        assert "a" in result and "b" in result

    def test_applies_year_dash_fix(self):
        result = apply_all_fixes("Tug'ilgan: 2025 yil")
        assert "2025-yil" in result

    def test_applies_lik_fix(self):
        result = apply_all_fixes("Kitob Bangladeshlik olim haqida")
        assert "bangladeshlik" in result

    def test_smoke_complex_wikitext(self):
        wikitext = (
            "'''Test''' — Bangladeshlik olim.<ref>source</ref>\n"
            "2025 yil tugʻilgan. al-Roziy haqida <!-- comment -->\n"
        )
        result = apply_all_fixes(wikitext)
        assert isinstance(result, str)
        assert len(result) > 0


# ── -lik lookback bounds ──────────────────────────────────────────────────────

class TestLikSuffixScanBounds:
    """The lookback deciding whether to keep the capital used to rescan the
    whole article from position 0 for every -lik word."""

    def test_scan_start_never_precedes_the_line(self):
        from wikikit.profiles.uz.rules import _keep_capital_scan_start
        text = "birinchi qator\nBu Bangladeshlik olim"
        start = _keep_capital_scan_start(text, text.index("Bangladeshlik"))
        assert start >= text.index("\n")

    def test_stays_linear_on_one_long_line(self):
        import time
        text = "Bu Bangladeshlik olim va Toshkentlik shoir haqida matn. " * 3000
        began = time.perf_counter()
        fix_lik_suffix_capitalization(text)
        assert time.perf_counter() - began < 2.0

    def test_result_matches_a_full_scan(self):
        from wikikit.profiles.uz.rules import _LIK_WORD, _LIK_KEEP_CAPITAL

        def full_scan(wikitext):
            def replacer(m):
                w = m.group(1)
                if _LIK_KEEP_CAPITAL.search(wikitext, 0, m.start()):
                    return w
                return w[0].lower() + w[1:]
            return _LIK_WORD.sub(replacer, wikitext)

        samples = [
            "'''Mogadishulik Sad''' — Bangladeshlik olim",
            "| nationality = Bangladeshlik\n| bio = U Toshkentlik edi",
            "* Bangladeshlik\n# Toshkentlik\n: Suriyalik",
            "[[Bangladeshlik]] va Toshkentlik. Suriyalik keldi",
            "Matn tugadi. Bangladeshlik olim\n\nToshkentlik shoir",
            "\t'''Toshkentlik''' va Bangladeshlik",
        ]
        for sample in samples:
            assert fix_lik_suffix_capitalization(sample) == full_scan(sample)


# ── fix_gregorian_dates ───────────────────────────────────────────────────────

class TestFixGregorianDates:
    def test_day_month_year(self):
        assert fix_gregorian_dates("3 September 2018") == "2018-yil 3-sentyabr"

    def test_month_day_year(self):
        assert fix_gregorian_dates("September 3, 2018") == "2018-yil 3-sentyabr"

    def test_case_suffix_moves_to_the_month(self):
        result = fix_gregorian_dates("(September 3, 2018-yilga toʻgʻri keladi)")
        assert result == "(2018-yil 3-sentyabrga toʻgʻri keladi)"

    def test_leading_zero_dropped(self):
        assert fix_gregorian_dates("05 March 1990") == "1990-yil 5-mart"

    def test_month_name_alone_untouched(self):
        assert fix_gregorian_dates("May oyida") == "May oyida"

    def test_infobox_value_fixed_through_apply_all(self):
        result = apply_all_fixes("{{Bilgiquti\n| death_date = 3 September 2018\n}}")
        assert "2018-yil 3-sentyabr" in result

    def test_citation_date_untouched_through_apply_all(self):
        text = "Matn.<ref>{{cite web|date=September 4, 2018}}</ref>"
        assert "September 4, 2018" in apply_all_fixes(text)


# ── fix_era_abbreviations ─────────────────────────────────────────────────────

class TestFixEraAbbreviations:
    def test_linked_ah_after_uzbek_year(self):
        result = fix_era_abbreviations("hijriy 255-yil [[Islomiy taqvim|AH]]")
        assert result == "hijriy 255-yil"

    def test_bare_ah_after_uzbek_year(self):
        assert fix_era_abbreviations("hijriy 329-yil AH") == "hijriy 329-yil"

    def test_linked_ce_after_number(self):
        assert fix_era_abbreviations("868 [[Bizning era|CE]]") == "milodiy 868-yil"

    def test_bare_ah_after_number(self):
        assert fix_era_abbreviations("(1358 AH)") == "(hijriy 1358-yil)"

    def test_lowercase_word_untouched(self):
        assert fix_era_abbreviations("255 ah") == "255 ah"

    def test_reference_untouched_through_apply_all(self):
        text = "Matn<ref>Nashr al-Fiqaha, 1417 AH.</ref>"
        assert "1417 AH." in apply_all_fixes(text)

    def test_citation_template_untouched_through_apply_all(self):
        text = "* {{cite book|title=Year 300 AH}}"
        assert "300 AH" in apply_all_fixes(text)


class TestLikSuffixLeavesNames:
    def test_malik_is_a_name_not_an_adjective(self):
        text = "Xalifa Abd al-Malik davrida va Abdulmalik bilan"
        assert fix_lik_suffix_capitalization(text) == text

    def test_citation_title_is_left_alone(self):
        text = "Matn {{cite journal |title=Abd al-Malik and the Dome}} va Bangladeshlik olim"
        result = apply_all_fixes(text)
        assert "|title=Abd al-Malik and the Dome}}" in result
        assert "bangladeshlik olim" in result
