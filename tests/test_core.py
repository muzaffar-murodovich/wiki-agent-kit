"""Core of the kit: read-only API, profiles, prepare/finish round trip, checks, queue."""

import json

import pytest

from wikikit import api, checks, finder, labels, lookup, profiles, translate
from wikikit.wikitext import generic_clean_title, generic_same_name


# ------------------------------------------------------------------ api

@pytest.mark.parametrize("action", ["edit", "wbeditentity", "upload", "login", "wbsetlabel", "cxpublish"])
def test_write_actions_are_refused_before_any_request(action, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a request was made")
    monkeypatch.setattr(api.urllib.request, "urlopen", boom)
    with pytest.raises(api.WriteRefused):
        api.api({"action": action, "title": "X"})


def test_token_requests_are_refused(monkeypatch):
    monkeypatch.setattr(api.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    with pytest.raises(api.WriteRefused):
        api.api({"action": "query", "meta": "siteinfo|tokens"})


@pytest.mark.parametrize("spec,host", [
    ("en", "en.wikipedia.org"), ("uz.wiktionary", "uz.wiktionary.org"), ("enwiki", "en.wikipedia.org"),
    ("uzwikisource", "uz.wikisource.org"), ("wikidata", "www.wikidata.org"), ("commons", "commons.wikimedia.org"),
    ("en.wikipedia.org", "en.wikipedia.org"),
])
def test_site_host(spec, host):
    assert api.site_host(spec) == host


def test_user_agent_carries_contact(monkeypatch):
    monkeypatch.setenv("WIKIKIT_CONTACT", "User:Example")
    assert "User:Example" in api.user_agent()


# ------------------------------------------------------------------ generic helpers

def test_generic_same_name_ignores_diacritics_not_words():
    assert generic_same_name("São Paulo", "Sao Paulo")
    assert not generic_same_name("Lahore", "Lahor")
    assert not generic_same_name("Somalis", "somali")          # lowercase gloss keeps its pipe
    assert not generic_same_name("Cordoba (city)", "Cordoba")  # disambiguator keeps its pipe


def test_generic_clean_title():
    assert generic_clean_title("''kitob al-kofiy''") == "Kitob al-kofiy"
    assert generic_clean_title("bad|name") is None
    assert generic_clean_title("") is None


def test_label_collapse_leaves_references_alone():
    text = "[[Lohur|Lohur]] va <ref>[[Lohur|Lahore]]</ref>"
    out, mism = labels.collapse(text, generic_same_name)
    assert out == "[[Lohur]] va <ref>[[Lohur|Lahore]]</ref>"
    assert mism == []


# ------------------------------------------------------------------ profiles

def test_uz_profile_loads_with_hooks():
    profiles.clear_cache()
    p = profiles.load("uz")
    s = p.summary()
    assert s["category_namespace"] == "Turkum"
    assert {"post_process", "same_name", "clean_title"} <= set(s["hooks"])
    assert p.same_name("Lohur", "Lahor")            # the uz skeleton comparator
    text, n = p.localize("== See also ==")
    assert n == 1 and "Yana qarang" in text


def test_unknown_language_gets_generic_profile():
    p = profiles.load("xx-test")
    assert p.directory is None and p.category_ns == "Category"
    assert p.post_process("abc") == "abc"


def test_user_profile_overrides_builtin(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKIKIT_HOME", str(tmp_path))
    d = tmp_path / "profiles" / "kaa"
    d.mkdir(parents=True)
    (d / "profile.json").write_text(json.dumps({"lang": "kaa", "namespaces": {"category": "Kategoriya"}}))
    profiles.clear_cache()
    assert profiles.load("kaa").category_ns == "Kategoriya"
    assert "kaa" in profiles.available()
    profiles.clear_cache()


# ------------------------------------------------------------------ prepare / finish round trip

SOURCE = """{{Short description|Persian polymath}}
{{Infobox person
| name = Ibn Sina
| birth_place = [[Afshana]]
}}
'''Avicenna''' was a [[Physician|physician]] from [[Bukhara]] who wrote ''[[The Canon of Medicine]]''.<ref>{{cite book |title=A History |author-link=Some Historian |url=https://example.org/book}}</ref> He taught [[Unknown Student|a student]].

== References ==
{{Reflist}}

[[Category:Persian physicians]]
[[Category:Unmapped category]]
"""

PAGES = {
    # title: (qid, uz title)
    "Afshana": ("Q1", "Afshona"),
    "Physician": ("Q2", "Shifokor"),
    "Bukhara": ("Q3", "Buxoro"),
    "The Canon of Medicine": ("Q4", "Tib qonunlari"),
    "Unknown Student": (None, None),
    "Some Historian": ("Q5", None),
    "Category:Persian physicians": ("Q6", "Turkum:Fors shifokorlari"),
    "Category:Unmapped category": (None, None),
    "Template:Short description": ("Q7", "Andoza:Qisqa tavsif"),
    "Template:Infobox person": ("Q8", None),
    "Template:Reflist": ("Q9", "Andoza:Manbalar"),
}


@pytest.fixture
def fake_wiki(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKIKIT_HOME", str(tmp_path))
    profiles.clear_cache()

    def fake_api(params, site="en", **kw):
        if params.get("action") == "query" and "titles" in params:
            pages = []
            for t in params["titles"].split("|"):
                qid, uz = PAGES.get(t, (None, None))
                p = {"title": t}
                if qid:
                    p["pageprops"] = {"wikibase_item": qid}
                if uz:
                    p["langlinks"] = [{"lang": "uz", "title": uz}]
                if t not in PAGES:
                    p["missing"] = True
                pages.append(p)
            return {"query": {"pages": pages}}
        if params.get("action") == "wbgetentities":
            return {"entities": {q: {"sitelinks": {}} for q in params["ids"].split("|")}}
        raise AssertionError(params)

    monkeypatch.setattr(lookup, "api", fake_api)
    monkeypatch.setattr(translate.LinkContext, "for_site", classmethod(lambda cls, site: translate.Preparer(None, profiles.load("uz")).ctx))
    monkeypatch.setattr(translate, "fetch_wikitext", lambda title, site: {
        "title": title, "redirected_from": None, "revid": 123, "timestamp": "t",
        "qid": "Q8011", "wikitext": SOURCE, "site": "en.wikipedia.org"})
    yield tmp_path
    profiles.clear_cache()


def test_start_writes_placeholders_and_hides_citations(fake_wiki):
    r = translate.start("Avicenna", "uz")
    prepared = open(r["prepared_path"], encoding="utf-8").read()
    assert "[[Q2|physician]]" in prepared and "[[Q3|Bukhara]]" in prepared
    assert "[[LNK1|a student]]" in prepared
    assert "⟦CAT:Q6|Persian physicians|⟧" in prepared
    assert "{{TPL:Q7|" in prepared
    assert "example.org" not in prepared and "<ref>REF_" in prepared
    links = json.load(open(r["links_path"], encoding="utf-8"))
    assert links == [{"id": "LNK1", "source_target": "Unknown Student", "source_label": "a student"}]
    # The infobox has no uz counterpart and no fallback mapping in the test map,
    # so the uz profile (unmapped_templates = drop) removes it... unless a fallback exists:
    assert "Shaxs bilgiqutisi" in prepared  # profile fallback "infobox person"
    assert r["counts"]["failed_lookups"] == []


def test_finish_round_trip(fake_wiki):
    r = translate.start("Avicenna", "uz")
    prepared = open(r["prepared_path"], encoding="utf-8").read()
    # A "translation" that keeps every placeholder, as the translator agent must.
    translated = (prepared.replace("was a", "—").replace("from", "")
                  .replace("[[LNK1|a student]]", "[[LNK1|shogirdi]]")
                  .replace("|Persian physicians|", "|Fors shifokorlari|"))
    open(r["write_translation_to"], "w", encoding="utf-8").write(translated)
    json.dump({"title": "Ibn Sino", "links": {"LNK1": "Nomaʼlum shogird"}},
              open(r["write_names_to"], "w", encoding="utf-8"))
    rep = translate.finish(r["job"])
    final = open(rep["final_path"], encoding="utf-8").read()
    assert "[[Shifokor|physician]]" in final
    assert "[[Buxoro|Bukhara]]" in final or "[[Buxoro]]" in final
    assert "[[Nomaʼlum shogird|shogirdi]]" in final
    assert "[[Turkum:Fors shifokorlari]]" in final
    assert "[[Turkum:Unmapped category]]" in final           # no item: namespace still localized
    assert "{{Qisqa tavsif|" in final
    assert "https://example.org/book" in final              # reference restored verbatim
    assert "author-link" not in final                        # no uz article: author-link dropped
    assert rep["leftover_placeholders"] == []
    assert rep["checks"]["references"]["new_urls"] == []
    assert rep["references"] == {"restored": 1, "total": 1}
    prep = translate.publish_prep(r["job"])
    assert "title=Ibn+Sino" in prep["edit_url"] and "action=edit" in prep["edit_url"]
    assert "123" in prep["edit_summary"]


def test_dropped_placeholder_is_reported(fake_wiki):
    r = translate.start("Avicenna", "uz")
    prepared = open(r["prepared_path"], encoding="utf-8").read()
    broken = prepared.replace("[[Q2|physician]]", "[[Q2|shifokor]] https://made-up.example")
    open(r["write_translation_to"], "w", encoding="utf-8").write(broken)
    rep = translate.finish(r["job"])
    assert "https://made-up.example" in rep["checks"]["references"]["new_urls"]
    assert rep["checks"]["blocking"]


# ------------------------------------------------------------------ checks

def test_number_check_finds_changed_numbers():
    res = checks.number_check("Born in 1043, wrote 12 books.", "1034-yilda tugʻilgan, 12 ta kitob yozgan.")
    assert res["missing_in_translation"] == ["1043"]
    assert res["not_in_source"] == ["1034"]


def test_markup_check():
    assert checks.markup_check("'''X''' [[a]] {{b}}") == []
    assert any("unbalanced [[" in p for p in checks.markup_check("'''X''' [[a] {{b}}"))
    assert any("placeholder" in p for p in checks.markup_check("'''X''' [[LNK1|a]]"))


def test_undefined_named_ref_is_caught():
    final = "'''X''' text.<ref name=\"a\" />"
    assert checks.reference_check("", final)["undefined_named_refs"] == ["a"]


# ------------------------------------------------------------------ queue

def test_queue_never_downgrades_and_requires_reasons(tmp_path):
    q = finder.Queue("en", "uz", path=tmp_path / "q.json")
    assert q.add("A", 100) == "added"
    assert q.set_status("A", "published") == "ok"
    assert q.add("A") == "dup:published"
    assert q.set_status("A", "queued").startswith("kept")
    assert q.reject("A", "x").startswith("kept")       # published: the human's to undo
    q.add("B", 50)
    with pytest.raises(ValueError):
        q.reject("B", "  ")
    assert q.reject("B", "off topic", "Cat") == "rejected (was queued)"
    assert q.rejected("topic")[0]["title"] == "B"
    assert q.requeue("B") == "queued"
    q.save()
    assert finder.Queue("en", "uz", path=tmp_path / "q.json").next(5)[0]["title"] == "B"


def test_unmapped_template_with_text_is_kept_not_dropped(fake_wiki):
    poem = "{{Text and translation|Bu dunyo bir saroydir, kelgan ketar|This world is a palace; who comes, goes}}"
    deco = "{{Unmapped decoration|yes|left}}"
    r = translate.start("Avicenna", "uz", wikitext=f"'''X''' is a poet.\n{poem}\n{deco}\n")
    prepared = open(r["prepared_path"], encoding="utf-8").read()
    assert "Text and translation" in prepared            # content survives
    assert "Unmapped decoration" not in prepared         # decoration goes
    assert r["counts"]["templates_kept_without_target"] == ["Text and translation"]
    assert r["counts"]["templates_removed"] == ["Unmapped decoration"]


# ------------------------------------------------------------------ regressions from the Opus code review

def test_link_context_classifies_prefixes():
    ctx = translate.LinkContext({"category": 14, "kategorie": 14, "datei": 6, "file": 6, "template": 10, "vorlage": 10},
                                {"wikt", "d"}, {"!", "CURRENTYEAR"})
    assert ctx.kind("wikt:flâneur") == "skip"
    assert ctx.kind("#Life") == "skip"
    assert ctx.kind("d:Q90") == "skip"
    assert ctx.kind("fr:Paris") == "skip"
    assert ctx.kind("Datei:Foo.jpg") == "skip"
    assert ctx.kind("Kategorie:Physiker") == "category"
    assert ctx.kind("Star Wars: Episode IV") == "article"
    assert ctx.template_name("Vorlage:Infobox") == "Infobox"
    assert ctx.template_name("Template:Foo") == "Foo"
    assert ctx.template_name("CURRENTYEAR") is None
    assert ctx.template_name("!") is None
    assert ctx.template_name("lc:ABC") is None


def test_names_json_flat_form_is_read(fake_wiki):
    r = translate.start("Avicenna", "uz")
    open(r["write_translation_to"], "w", encoding="utf-8").write(open(r["prepared_path"], encoding="utf-8").read())
    json.dump({"title": "Ibn Sino", "LNK1": "Nomaʼlum shogird"}, open(r["write_names_to"], "w", encoding="utf-8"))
    rep = translate.finish(r["job"])
    assert "[[Nomaʼlum shogird|a student]]" in open(rep["final_path"], encoding="utf-8").read()
    assert rep["links"]["name_taken_from_label"] == []


def test_mobile_url():
    from wikikit.pages import parse_page_ref
    assert parse_page_ref("https://en.m.wikipedia.org/wiki/Al-Biruni") == ("en.wikipedia.org", "Al-Biruni")


def test_set_status_cannot_reject(tmp_path):
    q = finder.Queue("en", "uz", path=tmp_path / "q.json")
    q.add("A")
    q.set_status("A", "published")
    assert q.set_status("A", "rejected").startswith("invalid")
    assert q.known("A") == "published"


def test_number_check_normalises_groups_and_native_digits():
    assert checks.number_check("Population 1,234,567 in 1950.", "Aholisi 1 234 567, ۱۹۵۰-yil.") == {
        "missing_in_translation": [], "not_in_source": []}


def test_fetch_text_refuses_local_and_private_urls():
    from wikikit import cite
    for url in ("file:///etc/passwd", "http://127.0.0.1:8080/", "http://localhost/x", "ftp://example.org/x"):
        with pytest.raises(ValueError):
            cite.fetch_text(url)


def test_windows_reserved_slug():
    assert translate._slug("Con") == "Con_"
