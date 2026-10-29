"""Tests for utils/trimmer.py — cutting a long article down to lead + apparatus."""

import pytest


from wikikit.trimmer import trim_article


def _article(body: str) -> str:
    return f"'''Subject''' was a scholar of some note, remembered for teaching.\n\n{body}"


STANDARD = _article("""== Biography ==
He was born and he taught.

== Works ==
He wrote things.

== See also ==
* [[Another Scholar]]

== References ==
{{reflist}}

{{Authority control}}
[[Category:Scholars]]
[[Category:900 deaths]]
""")


class TestNoTrimCases:
    def test_article_without_sections_untouched(self):
        text = _article("Just a lead, nothing else.")
        out, info = trim_article(text)
        assert out == text
        assert info["trimmed"] is False
        assert info["reason"] == "no_sections"

    def test_lead_followed_directly_by_references_untouched(self):
        text = _article("== References ==\n{{reflist}}\n[[Category:X]]\n")
        out, info = trim_article(text)
        assert out == text
        assert info["trimmed"] is False
        assert info["reason"] == "nothing_to_cut"

    def test_sizes_reported_even_when_not_trimmed(self):
        text = _article("Just a lead.")
        _, info = trim_article(text)
        assert info["original_size"] == len(text) == info["trimmed_size"]


class TestStandardTrim:
    def test_lead_and_apparatus_kept_body_cut(self):
        out, info = trim_article(STANDARD)
        assert info["trimmed"] is True
        assert "was a scholar of some note" in out
        assert "{{reflist}}" in out
        assert "He was born and he taught." not in out
        assert "He wrote things." not in out

    def test_categories_survive(self):
        out, _ = trim_article(STANDARD)
        assert "[[Category:Scholars]]" in out
        assert "[[Category:900 deaths]]" in out

    def test_see_also_is_dropped(self):
        out, info = trim_article(STANDARD)
        assert "[[Another Scholar]]" not in out
        assert "See also" in info["cut_sections"]

    def test_cut_sections_listed_in_order(self):
        _, info = trim_article(STANDARD)
        assert info["cut_sections"] == ["Biography", "Works", "See also"]
        assert info["kept_from"] == "References"

    def test_trimmed_size_matches_output(self):
        out, info = trim_article(STANDARD)
        assert info["trimmed_size"] == len(out)
        assert info["trimmed_size"] < info["original_size"]


class TestHeadingDetection:
    def test_level_three_apparatus_heading_found(self):
        text = _article("=== Biography ===\nBody.\n\n=== References ===\n{{reflist}}\n")
        out, info = trim_article(text)
        assert info["trimmed"] is True
        assert info["kept_from"] == "References"
        assert "Body." not in out

    @pytest.mark.parametrize(
        "heading", ["Notes", "Footnotes", "Bibliography", "Sources", "External links"]
    )
    def test_apparatus_heading_variants(self, heading):
        text = _article(f"== Biography ==\nBody.\n\n== {heading} ==\n{{{{reflist}}}}\n")
        _, info = trim_article(text)
        assert info["kept_from"] == heading

    def test_prose_section_named_like_apparatus_is_body(self):
        # Isma'il ibn Ja'far: "== Sources ==" right after the lead is prose
        # about the sources, the real apparatus is at the end.
        text = _article(
            "== Sources ==\nThe sources are scarce.\n\n== Life ==\nBody.\n\n"
            "== Footnotes ==\n{{notelist}}\n\n== References ==\n{{reflist}}\n\n"
            "== Sources ==\n* {{cite book|title=A}}\n[[Category:X]]\n"
        )
        out, info = trim_article(text)
        assert info["trimmed"] is True
        assert info["kept_from"] == "Footnotes"
        assert info["cut_sections"] == ["Sources", "Life"]
        assert "The sources are scarce." not in out
        assert "{{cite book|title=A}}" in out

    def test_apparatus_followed_by_prose_section_still_found(self):
        text = _article("== Life ==\nBody.\n\n== References ==\n{{reflist}}\n\n"
                        "== Gallery ==\nPictures.\n")
        _, info = trim_article(text)
        assert info["kept_from"] == "References"

    def test_markup_in_heading_still_matched(self):
        text = _article("== Biography ==\nBody.\n\n== '''References''' ==\n{{reflist}}\n")
        _, info = trim_article(text)
        assert info["trimmed"] is True

    def test_equals_inside_ref_is_not_a_heading(self):
        text = _article(
            "== Biography ==\nBody.<ref>A source with == not a heading == in it</ref>\n\n"
            "== References ==\n{{reflist}}\n"
        )
        out, info = trim_article(text)
        assert info["cut_sections"] == ["Biography"]
        assert "not a heading" not in out

    def test_equals_inside_template_is_not_a_heading(self):
        text = _article(
            "{{Infobox person\n| name = X\n== not a heading ==\n| era = 9th\n}}\n\n"
            "== Biography ==\nBody.\n\n== References ==\n{{reflist}}\n"
        )
        out, info = trim_article(text)
        assert info["cut_sections"] == ["Biography"]
        assert "Infobox person" in out


class TestNamedReferences:
    def test_definition_in_cut_body_is_inlined(self):
        text = _article(
            'Lead cites it.<ref name="p170"/>\n\n'
            '== Biography ==\nBody.<ref name="p170">{{cite book|page=170}}</ref>\n\n'
            "== References ==\n{{reflist}}\n"
        )
        out, info = trim_article(text)
        assert info["refs_inlined"] == ["p170"]
        assert '<ref name="p170">{{cite book|page=170}}</ref>' in out
        assert '<ref name="p170"/>' not in out

    def test_definition_already_in_lead_is_not_duplicated(self):
        text = _article(
            'Lead defines it.<ref name="p170">{{cite book|page=170}}</ref>\n\n'
            '== Biography ==\nBody.<ref name="p170"/>\n\n'
            "== References ==\n{{reflist}}\n"
        )
        out, info = trim_article(text)
        assert info["refs_inlined"] == []
        assert out.count("{{cite book|page=170}}") == 1

    def test_only_first_invocation_gets_the_definition(self):
        text = _article(
            'One.<ref name="a"/> Two.<ref name="a"/>\n\n'
            '== Biography ==\nBody.<ref name="a">{{cite|x}}</ref>\n\n'
            "== References ==\n{{reflist}}\n"
        )
        out, _ = trim_article(text)
        assert out.count("{{cite|x}}") == 1
        assert out.count('<ref name="a"/>') == 1

    def test_unnamed_refs_left_alone(self):
        text = _article(
            "Lead.<ref>Inline source</ref>\n\n== Biography ==\nBody.\n\n"
            "== References ==\n{{reflist}}\n"
        )
        out, info = trim_article(text)
        assert info["refs_inlined"] == []
        assert "<ref>Inline source</ref>" in out


class TestRescueAndGuards:
    def test_categories_above_references_are_rescued(self):
        text = _article(
            "== Biography ==\nBody.\n\n[[Category:Stranded]]\n\n"
            "== References ==\n{{reflist}}\n[[Category:Normal]]\n"
        )
        out, info = trim_article(text)
        assert "[[Category:Stranded]]" in out
        assert "[[Category:Normal]]" in out
        assert info["categories_recovered"] == 1

    def test_defaultsort_in_cut_region_is_rescued(self):
        text = _article(
            "== Biography ==\nBody.\n{{DEFAULTSORT:Subject, The}}\n\n"
            "== References ==\n{{reflist}}\n"
        )
        out, info = trim_article(text)
        assert "{{DEFAULTSORT:Subject, The}}" in out
        assert info["categories_recovered"] == 1

    def test_article_without_apparatus_keeps_categories(self):
        text = _article("== Biography ==\nBody.\n\n[[Category:Only]]\n")
        out, info = trim_article(text)
        assert info["reason"] == "no_apparatus_heading"
        assert info["trimmed"] is True
        assert "[[Category:Only]]" in out
        assert "Body." not in out

    def test_reflist_injected_when_refs_have_nowhere_to_render(self):
        text = _article(
            'Lead cites.<ref name="a"/>\n\n'
            '== Biography ==\nBody.<ref name="a">{{cite|x}}</ref>\n\n'
            "[[Category:Only]]\n"
        )
        out, info = trim_article(text)
        assert info["reflist_added"] is True
        assert "== References ==" in out
        assert "{{reflist}}" in out

    def test_reflist_not_injected_when_one_is_present(self):
        out, info = trim_article(STANDARD)
        assert info["reflist_added"] is False
        assert out.count("{{reflist}}") == 1

    def test_reflist_not_injected_without_refs(self):
        text = _article("== Biography ==\nBody.\n\n[[Category:Only]]\n")
        _, info = trim_article(text)
        assert info["reflist_added"] is False


class TestThinLead:
    def test_short_lead_flagged(self):
        text = "'''X''' was a person.\n\n== Biography ==\nBody.\n\n== References ==\n{{reflist}}\n"
        _, info = trim_article(text)
        assert info["thin_lead"] is True

    def test_long_lead_not_flagged(self):
        lead = "'''X''' was a person. " + ("He did many notable things. " * 30)
        text = f"{lead}\n\n== Biography ==\nBody.\n\n== References ==\n{{{{reflist}}}}\n"
        _, info = trim_article(text)
        assert len(lead) > 400
        assert info["thin_lead"] is False
