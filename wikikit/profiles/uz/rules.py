#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
utils/regex_patterns.py - All regex patterns in one place
The class holds the named patterns; the functions below are the text fixes.
"""

import re
import mwparserfromhell as mwp

class RegexPatterns:
    """
    Regex patterns used throughout the project.
    Each pattern is named in UPPERCASE.
    """

    # ========== Template Parameter Cleanup ==========

    # Empty template parameter: | param =
    EMPTY_PARAM = r'\|\s*([^=\|{}]+?)\s*=\s*(?=\n\s*[\|}])'

    # ========== Newline Cleanup ==========

    # 3+ newlines -> 2 newlines
    MULTIPLE_NEWLINES = r'\n\s*\n\s*\n+'

    # Empty lines inside templates
    TEMPLATE_EMPTY_LINES = r'(\{\{[^}]*?)\n\n+'

    # ========== Reference Tags ==========

    # <ref>...</ref> tag (closing, NOT self-closing)
    REF_TAG = r'<ref[^/>]*>.*?</ref>'

    # Self-closing ref: <ref ... />
    REF_SELF_CLOSING = r'<ref[^>]*/\s*>'

    # Either kind, as the tail of a tag: </ref> or the closing />
    REF_TAG_END = r'</ref>|/\s*>'

    # Compressed reference placeholder: REF_a1b2c3d4
    REF_PLACEHOLDER = r'REF_[a-f0-9]{8}'

    # Compressed bare citation template: CITE_a1b2c3d4
    CITE_PLACEHOLDER = r'CITE_[a-f0-9]{8}'

    # Either kind — what must never reach the finished article
    COMPRESSED_PLACEHOLDER = r'(?:REF|CITE)_[a-f0-9]{8}'

    # A citation template's name: cite book, cite web, citation ...
    CITATION_TEMPLATE_NAME = r'^\s*(?:cite\b|citation\s*$)'

    # ========== Citations ==========

    # {{sfn|...}} / {{efn|...}}
    SFN_EFN_TEMPLATE = r'\{\{(?:sfn|efn)\s*\|[^}]*\}\}'

    # One citation of any kind: an sfn/efn template or a ref tag.
    CITATION = r'(?:' + SFN_EFN_TEMPLATE + r'|' + REF_TAG + r'|' + REF_SELF_CLOSING + r')'

    # ========== Punctuation Around References ==========
    # These are the patterns fix_punctuation_with_refs actually applies.
    # Keep them here rather than inline: an earlier set of near-miss copies
    # lived in this class while the function ran its own, and the two drifted.

    # text.<ref>...</ref>  ->  the mark belongs after the tag
    PUNCT_BEFORE_REF = r'([.,;!?])\s*(' + REF_TAG + r')'

    # text.<ref name="x"/>  ->  same, for a self-closing tag
    PUNCT_BEFORE_SELF_CLOSING_REF = r'([.,;!?])\s*(' + REF_SELF_CLOSING + r')'

    # </ref>.<ref>  ->  a mark stranded between two refs
    PUNCT_BETWEEN_REFS = r'(' + REF_TAG_END + r')([.,;!?])(\s*)(<ref)'

    # A ref that ends a sentence and has no mark. '[' is excluded here and
    # handled by REF_BEFORE_CAPITALISED_LINK, because a lowercase link
    # continues the sentence.
    REF_NEEDS_PERIOD = r'(</ref>)(\s+)(?![.,;!?<{\[a-zʼ‘’\'])'
    SELF_CLOSING_REF_NEEDS_PERIOD = r'(/\s*>)(\s+)(?![.,;!?<{\[a-zʼ‘’\'])'

    # </ref>.. -> </ref>.
    REPEATED_PUNCT_AFTER_REF = r'(' + REF_TAG_END + r')([.,;!?])\2+'

    # The body of a link whose VISIBLE text is capitalised, read after "[[".
    # A piped link shows its label, not its target, and a target is always
    # capitalised on MediaWiki — so [[Shialik|shia musulmon]] continues the
    # sentence. The mandatory "\|" keeps the first branch from backtracking
    # onto the target's capital.
    CAPITALISED_LINK_BODY = (
        r'[^\]|]*\|[A-ZА-ЯЁʿʾ]'
        r'|[A-ZА-ЯЁʿʾ][^\]|]*\]\]'
    )

    # </ref> [[Ism]] -> a capitalised link does start a new sentence
    REF_BEFORE_CAPITALISED_LINK = (
        r'(' + REF_TAG_END + r')(\s+)(\[\[)(?=' + CAPITALISED_LINK_BODY + r')'
    )

    # ========== Dates ==========

    _EN_MONTH = (
        r'(?P<m>January|February|March|April|May|June|July|August'
        r'|September|October|November|December)'
    )
    # An Uzbek case suffix the model put on the year: "2018-yilga"
    _YEAR_SUFFIX = r'(?:-yil(?P<s>\w*))?'

    # 3 September 2018
    EN_DATE_DMY = r'\b(?P<d>\d{1,2})\s+' + _EN_MONTH + r',?\s+(?P<y>\d{3,4})\b' + _YEAR_SUFFIX
    # September 3, 2018
    EN_DATE_MDY = r'\b' + _EN_MONTH + r'\s+(?P<d>\d{1,2}),?\s+(?P<y>\d{3,4})\b' + _YEAR_SUFFIX

    # hijriy 255-yil [[Islomiy taqvim|AH]]  /  hijriy 329-yil AH
    ERA_AFTER_UZ_YEAR = (
        r'\b((?:hijriy|milodiy)\s+\d+-yil\w*)'
        r'(?:\s*\[\[[^\]|]*\|\s*(?:AH|H|CE|AD)\s*\]\]|\s+(?:AH|CE|AD)\b)'
    )
    # 255 [[Islomiy taqvim|AH]]  /  868 CE
    ERA_AFTER_NUMBER = (
        r'\b(?P<n>\d{1,4})'
        r'(?:\s*\[\[[^\]|]*\|\s*(?P<era>AH|H|CE|AD)\s*\]\]|\s+(?P<era2>AH|CE|AD)\b)'
    )

    # ========== Wikilinks ==========

    # [[link|text]] or [[link]]
    WIKILINK = r'\[\[([^\]\|]+)(?:\|([^\]]+))?\]\]'

    # A link with no uz.wiki article, as prepare() hands it to the model:
    # [[LNK3|label]]. The page name is filled in by finalize().
    LINK_PLACEHOLDER = r'LNK\d+'
    # The same placeholder in the translated text, with the label the model wrote
    TRANSLATED_LINK_PLACEHOLDER = r'\[\[(LNK\d+)\|([^\]]*)\]\]'
    # The model now and then writes a link placeholder in template braces:
    # {{LNK8|shayx ul-hadis}}. Parsed as a template, it never got resolved.
    BRACED_LINK_PLACEHOLDER = r'\{\{\s*((?:LNK|Q)\d+)\s*\|([^{}|]*)\}\}'
    # A Q/LNK placeholder still standing as a link or template after finalize()
    LEFTOVER_LINK_PLACEHOLDER = r'(?:\[\[|\{\{)\s*((?:LNK|Q)\d+)\s*[|\]}]'
    # A citation parameter that names a wiki page: author-link, editor1-link,
    # authorlink, title-link...
    CITATION_LINK_PARAM = r'^[a-z]+\d*-?link\d*$'

    # Characters a page name cannot contain
    INVALID_TITLE_CHARS = r'[\[\]{}|<>#]'

    # ========== HTML Comments ==========

    # <!-- comment -->
    HTML_COMMENT = r'<!--.*?-->'

    # ========== Categories ==========

    # Category token: ⟦CAT:Q12345|cat_name|sort_key⟧ (sort_key may be empty)
    CAT_TOKEN = r'⟦CAT:(Q\d+)\|([^|⟧]+)\|([^⟧]*)⟧'

    # ========== Source Checks ==========

    # A Latin word with Arabic letters glued to it: Baḥر, al-ʿUlūم — a defect
    # already present in the en.wiki source.
    _LATIN = r'A-Za-zÀ-ɏḀ-ỿ'
    MIXED_SCRIPT_WORD = (
        r'[' + _LATIN + r'ʿʾ\-]*[' + _LATIN + r'][\u0600-\u06FF]+[' + _LATIN + r']*'
        r'|[\u0600-\u06FF]+[' + _LATIN + r']+'
    )

    # {{Short description|Persian Shia hadith collector (864–941 CE)}}
    SHORT_DESCRIPTION = r'\{\{\s*short description\s*\|([^}]*)\}\}'
    YEAR_RANGE = r'(\d{3,4})\s*[–—-]\s*(\d{3,4})'

    # | birth_date = ...   (one infobox line)
    INFOBOX_DATE = r'^\s*\|\s*(birth|death)_date\s*=(.*)$'

    # A year in the Islamic calendar, bare or linked: 255 AH, 255 [[...|AH]]
    HIJRI_YEAR = r'\d{1,4}\s*(?:\[\[[^\]|]*\|\s*)?A\.?H\b\.?'

    # [[Category:1940 births]], [[category:860s deaths]]
    YEAR_CATEGORY = r'\[\[\s*category\s*:\s*(\d{3,4})(s?)\s+(births|deaths)\s*[\]|]'

    # The lead line: the first line that opens with the bold subject name
    LEAD_LINE = r"^'''[^\n]*"
    # Inline markup dropped before the lead sentence is read
    LEAD_NOISE = r'<ref[^>]*/\s*>|<ref[^>]*>.*?</ref>|\{\{[^{}]*\}\}'

    # Spellings Uzbek never uses, so a bold name with one is still English
    ENGLISH_SPELLING = r'w|th|oo|ee|ou|kh|gh|dh|ph|c(?!h)|[āīūḥṣḍṭẓ]'

    # ========== Apparatus Headings (trimmer) ==========

    # A section heading whose body is citation apparatus rather than prose.
    # Matched against the heading TITLE only: mwparserfromhell already
    # guarantees the caller is looking at a real heading and not a "==" that
    # happens to sit inside a <ref> body or a template parameter.
    #
    # "See also" is deliberately absent. It sits before == References == and
    # holds en.wiki links that become red links in uz, so the trim drops it.
    APPARATUS_HEADING = (
        r'^\s*(?:references?|sources?|notes?|footnotes?|citations?'
        r'|works\s+cited|bibliography|further\s+reading|external\s+links)\s*$'
    )


# ========== Special Regex Functions ==========

def remove_empty_params(wikitext: str) -> str:
    """Remove empty template parameters."""
    cleaned = re.sub(RegexPatterns.EMPTY_PARAM, '', wikitext)
    cleaned = re.sub(RegexPatterns.MULTIPLE_NEWLINES, '\n\n', cleaned)
    cleaned = re.sub(RegexPatterns.TEMPLATE_EMPTY_LINES, r'\1\n', cleaned)
    return cleaned


def clean_html_comments(wikitext: str) -> str:
    """Remove HTML comments: <!-- ... -->"""
    return re.sub(RegexPatterns.HTML_COMMENT, '', wikitext, flags=re.DOTALL)


def fix_punctuation_with_refs(wikitext: str) -> str:
    """
    Fix punctuation placement around references.

    Transformations:
    - text.<ref>...</ref>   ->  text<ref>...</ref>.
    - text.<ref name="x"/>  ->  text<ref name="x"/>.
    - </ref>.<ref>          ->  </ref><ref>
    - </ref> (sentence end)  ->  </ref>.
    - </ref>..              ->  </ref>.
    """
    # 1. Move punctuation from before a ref to after it, either tag kind.
    wikitext = re.sub(RegexPatterns.PUNCT_BEFORE_REF, r'\2\1', wikitext, flags=re.DOTALL)
    wikitext = re.sub(RegexPatterns.PUNCT_BEFORE_SELF_CLOSING_REF, r'\2\1', wikitext)

    # 2. Drop a mark stranded between two consecutive refs.
    wikitext = re.sub(RegexPatterns.PUNCT_BETWEEN_REFS, r'\1\3\4', wikitext)

    # 3. Add the sentence's period when a ref ends it and none is there.
    wikitext = re.sub(RegexPatterns.REF_NEEDS_PERIOD, r'\1.\2', wikitext)
    wikitext = re.sub(RegexPatterns.SELF_CLOSING_REF_NEEDS_PERIOD, r'\1.\2', wikitext)

    # 4. Collapse a mark that ended up repeated.
    wikitext = re.sub(RegexPatterns.REPEATED_PUNCT_AFTER_REF, r'\1\2', wikitext)

    # 5. A capitalised [[link]] starts a new sentence; step 3 skips '[' so
    #    that a lowercase link, which continues the sentence, is left alone.
    wikitext = re.sub(RegexPatterns.REF_BEFORE_CAPITALISED_LINK, r'\1.\2\3', wikitext)

    return wikitext


# ========== Cite Book Script-Title Fix ==========

def fix_cite_book_script_title(wikitext: str) -> str:
    """
    Replace `script-title` with `title` in {{cite book}} templates.
    Strips the language prefix (e.g. "ru:") from the value.

    Example:
    {{cite book |script-title=ru:Text}} -> {{cite book |title=Text}}
    """
    pattern = r'\{\{cite\s+book([^}]*?)\|\s*script-title\s*=\s*(?:[a-z]{2}:)?([^}|\]]*)'
    replacement = r'{{cite book\1|title=\2'
    return re.sub(pattern, replacement, wikitext, flags=re.IGNORECASE)


# ========== Lowercase -lik Suffix Fix ==========

# "Malik" and "Abdulmalik" are names, not a -lik adjective: lowercased, the
# localization map's "-malik" rule then turned "Abd al-Malik" into "Abd almalik".
_LIK_WORD = re.compile(r'\b([A-Z][a-z]*(?<![Mm]a)lik)\b(?![}\]])')

# Positions where the capital is correct and the word must be left alone:
# the start of a line (a paragraph starts a sentence, and the article name
# opens with '''), the start of a new sentence, a template parameter value
# and the inside of a [[wikilink]].
_LIK_KEEP_CAPITAL = re.compile(
    r"(?:\A|\n)[ \t*#:;]*(?:'{2,})?[ \t]*$"   # line start / '''article name'''
    r"|[.!?][ \t]*$"                           # new sentence
    r"|[=:][ \t]*$"                             # template parameter value
    r"|\[[ \t]*$"                               # [[wikilink]] target
)


# Everything a _LIK_KEEP_CAPITAL match may consist of after its first
# character. Walking back over this run bounds how far the scan has to look.
_LIK_LOOKBACK_CHARS = " \t*#:;'"


def _keep_capital_scan_start(wikitext: str, word_start: int) -> int:
    """
    Earliest position a _LIK_KEEP_CAPITAL match ending at `word_start` can begin.

    Every alternative is a single leading character (\n, '.', '=', '[' ...)
    followed by a run drawn from _LIK_LOOKBACK_CHARS, and none of them can span
    a newline. Bounding the scan this way keeps the whole fix linear; searching
    from position 0 for every -lik word made it quadratic — a 180 KB article
    spent about twelve seconds here.
    """
    i = word_start
    while i > 0 and wikitext[i - 1] in _LIK_LOOKBACK_CHARS:
        i -= 1
    # One more character for the alternative's own leading token, and never
    # past the newline that opens this line.
    return max(i - 1, wikitext.rfind('\n', 0, word_start), 0)


def fix_lik_suffix_capitalization(wikitext: str) -> str:
    """
    Lowercase words ending with -lik suffix mid-sentence.

    The suffix builds a common adjective, so it is lowercase inside a sentence
    but keeps its capital wherever any other word would keep it.

    Example:
    '''Ubaydul Haq''' — Bangladeshlik teacher
    -> '''Ubaydul Haq''' — bangladeshlik teacher

    But keeps:
    '''Mogadishulik Saʼid''' — ...   (article name)
    | nationality = Bangladeshlik      (parameter value)
    [[Bangladeshlik]]                  (link target)
    """
    def replacer(match):
        word = match.group(1)
        if _LIK_KEEP_CAPITAL.search(wikitext, _keep_capital_scan_start(wikitext,
                                                                       match.start()),
                                    match.start()):
            return word
        return word[0].lower() + word[1:]

    return _LIK_WORD.sub(replacer, wikitext)


# ========== Year With Dash Fix ==========

# A calendar year is 3-4 digits, optionally the two-digit tail of a range
# (1975/76). A duration ("28 yil davomida") is not a year and keeps its space.
_YEAR_BEFORE_YIL = re.compile(
    r'(?<!\d)(\d{3,4}(?:/\d{2})?)\s+(yil(?:da|lar(?:i|da)?)?)'
)

# Words that mark the number as a length of time rather than a point in time.
_DURATION_AFTER_YIL = re.compile(
    r'\w*\s+(?:davom\w*|mobaynida|ichida|oldin|avval|keyin|burun'
    r'|muqaddam|oʻtgach|ortiq|kam|koʻp)\b'
)


def fix_year_with_dash(wikitext: str) -> str:
    """
    Add dash between year numbers and -yil suffix.

    Examples:
    2025 yil -> 2025-yil
    1975/76 yillarda -> 1975/76-yillarda

    A duration keeps its space, because -yil marks a point in time only:
    28 yil davomida -> 28 yil davomida
    100 yil oldin   -> 100 yil oldin
    """
    def replacer(match):
        if _DURATION_AFTER_YIL.match(wikitext, match.end()):
            return match.group(0)
        return f"{match.group(1)}-{match.group(2)}"

    # Pattern 1: YYYY yil -> YYYY-yil
    wikitext = _YEAR_BEFORE_YIL.sub(replacer, wikitext)

    # Pattern 2: {{Circa|910}} yilda -> {{Circa|910}}-yilda
    wikitext = re.sub(r'(\{\{\s*Circa[^}]*\}\})\s+(yil(?:da|lar(?:i|da)?)?)', r'\1-\2', wikitext)

    return wikitext


# ========== Fix Punctuation With SFN Templates ==========

_CITATION = RegexPatterns.CITATION

# A citation chain plus the punctuation mark in front of it. Citations may be
# separated by stray punctuation and spaces, but never by a newline: joining
# across one would swallow a paragraph break.
_CITATION_CHAIN = re.compile(
    r'(?P<lead>[.,;!?])?[ \t]*'
    r'(?P<chain>' + _CITATION + r'(?:[ \t]*[.,;!?]*[ \t]*' + _CITATION + r')*)'
    r'(?P<trail>[.,;!?]*)',
    re.IGNORECASE | re.DOTALL,
)

_ONE_CITATION = re.compile(_CITATION, re.IGNORECASE | re.DOTALL)

# The text a reader sees for a link: the label when piped, else the target.
# See RegexPatterns.CAPITALISED_LINK_BODY for why the target is not enough.
_VISIBLE_LINK_TEXT = re.compile(r'\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]')
_HAS_SFN_EFN = re.compile(RegexPatterns.SFN_EFN_TEMPLATE, re.IGNORECASE)


def _chain_closes_sentence(rest: str) -> bool:
    """
    True when a period should be invented after a citation chain.

    `rest` is the text following the chain. A period is only invented when
    the chain really ends a sentence: a lowercase word means the sentence is
    still running, and markup that opens something new is left alone. A
    capitalised [[link]] does start a new sentence, so it counts.
    """
    space = re.match(r'\s+', rest)
    if not space:
        return False

    after = rest[space.end():]
    if not after:
        # End of the paragraph or of the document.
        return True
    if after[0] in '.,;!?<{':
        return False
    if after.startswith('[['):
        visible = _VISIBLE_LINK_TEXT.match(after)
        nxt = visible.group(1)[:1] if visible else after[2:3]
        return bool(nxt) and (nxt.isupper() or nxt.isdigit())
    if after[0] in "[ʼʻ‘’'":
        return False
    return not after[0].islower()


def fix_punctuation_with_sfn(wikitext: str) -> str:
    """
    Put the sentence punctuation after a chain of {{sfn}}/{{efn}} citations.

    A run of citations is treated as one unit rather than one hop at a time.
    The first punctuation mark found — in front of the chain, or stranded
    between two of its templates — becomes the chain's trailing mark, and any
    further marks inside the chain are dropped.

    Moving the marks one template at a time is what used to pile them up:

        Matn.{{sfn|A}}.{{sfn|B}} Yana.  ->  Matn{{sfn|A}}{{sfn|B}}.. Yana.

    An existing mark is never destroyed and a period is never invented in
    front of a word that continues the sentence.

    A chain of plain <ref> tags with no {{sfn}}/{{efn}} in it belongs to
    fix_punctuation_with_refs and is left untouched here.
    """
    def rebuild(match: re.Match) -> str:
        chain = match.group('chain')
        if not _HAS_SFN_EFN.search(chain):
            return match.group(0)

        citations = _ONE_CITATION.findall(chain)
        # findall() with a non-capturing group returns whole matches.
        joined = ''.join(citations)

        # The first mark anywhere in the chain region is the sentence's own;
        # the rest are artefacts of an earlier pass moving it template by
        # template, and go.
        marks = [match.group('lead')] if match.group('lead') else []
        marks += re.findall(r'[.,;!?]', chain)
        marks += list(match.group('trail'))

        if marks:
            return joined + marks[0]
        if _chain_closes_sentence(match.string[match.end():]):
            return joined + '.'
        return joined

    return _CITATION_CHAIN.sub(rebuild, wikitext)


# ========== Combine All Fixes ==========

def _fix_all_punctuation(wikitext: str) -> str:
    """Both punctuation fixes, in order. Refs first: it normalises the tags
    that fix_punctuation_with_sfn then treats as part of a citation chain."""
    wikitext = fix_punctuation_with_refs(wikitext)
    return fix_punctuation_with_sfn(wikitext)



def apply_all_fixes(wikitext: str) -> str:
    """Apply all text fixes in sequence. Order matters!"""

    # 0. Arabic transliteration + date fixes (already infobox-aware via mwparserfromhell)
    wikitext = fix_arabic_transliteration(wikitext)

    # 0b. AH/CE markers next to a year — references and citations excluded
    wikitext = apply_outside_refs(wikitext, fix_era_abbreviations)

    # 1. Cite book script-title fix
    wikitext = fix_cite_book_script_title(wikitext)

    # 2. Year dash fix
    wikitext = fix_year_with_dash(wikitext)

    # 3. -lik suffix capitalization fix — a citation quotes its title as published
    wikitext = apply_outside_refs(wikitext, fix_lik_suffix_capitalization)

    # 4. Punctuation around references and citations — skip infoboxes.
    #    Both run inside one masking pass: each _apply_fix_outside_infoboxes
    #    call parses the whole article to find the infoboxes, and the second
    #    parse re-derived exactly what the first one had.
    wikitext = _apply_fix_outside_infoboxes(wikitext, _fix_all_punctuation)

    # 6. fix template blank lines 
    wikitext = fix_template_blank_lines(wikitext)
    
    # Collapse 3+ consecutive newlines to 2 (single blank line max)
    wikitext = re.sub(r'\n{3,}', '\n\n', wikitext)

    return wikitext

_DIACRITIC_TRANS = str.maketrans({
    'ā': 'a', 'Ā': 'A',
    'ī': 'i', 'Ī': 'I',
    'ū': 'u', 'Ū': 'U',
    'ḥ': 'h', 'Ḥ': 'H',
    'ṣ': 's', 'Ṣ': 'S',
    'ḍ': 'd', 'Ḍ': 'D',
    'ṭ': 't', 'Ṭ': 'T',
    'ẓ': 'z', 'Ẓ': 'Z',
    'ġ': 'gʻ', 'Ġ': 'Gʻ',
    'ʿ': '',
    'ʾ': '',
})

# Tags whose contents must NEVER be modified
_PROTECTED_TAGS = frozenset({
    'ref', 'nowiki', 'pre', 'source', 'syntaxhighlight', 'code', 'math'
})


def transliterate_name(text: str) -> str:
    """Rule 1 and 2 transliteration for a bare name, such as a page title."""
    return _apply_arabic_text_fixes(text)


def _apply_arabic_text_fixes(text: str) -> str:
    """Apply Rule 1 (diacritics) and Rule 2 (solar letters) to plain text."""

    # Rule 1a: Final -ī → -iy (must run BEFORE general diacritic removal,
    # otherwise the information is lost)
    text = re.sub(r'ī\b', 'iy', text)
    text = re.sub(r'Ī\b', 'Iy', text)

    # Rule 1b: Remove all other diacritics
    text = text.translate(_DIACRITIC_TRANS)

    # Rule 2: Solar letter assimilation (al-X → aX-X)
    # 'Sh' must come first in the alternation to avoid 'S' matching first
    def _solar_replace(m: re.Match) -> str:
        prefix = m.group(1)  # 'a' or 'A'
        letter = m.group(2)  # 'Sh', 'R', 'D', 'N', 'S', 'T', or 'Z'
        if letter == 'Sh':
            return f'{prefix}sh-{letter}'
        return f'{prefix}{letter.lower()}-{letter}'

    text = re.sub(r'\b([Aa])l-(Sh|R|D|N|S|T|Z)', _solar_replace, text)
    return text


def _process_wikicode_safe(code) -> None:
    """
    Recursively walk the parse tree, applying text fixes ONLY to safe contexts.
    Skips <ref>, URLs, and non-infobox templates.
    """
    for node in code.nodes:
        node_type = type(node).__name__

        if node_type == 'Text':
            node.value = _apply_arabic_text_fixes(node.value)
            node.value = _apply_date_fixes(node.value)

        elif node_type == 'Heading':
            _process_wikicode_safe(node.title)

        elif node_type == 'Wikilink':
            # Process visible label only — link target is intentionally untouched
            if node.text is not None:
                _process_wikicode_safe(node.text)

        elif node_type == 'Tag':
            tag_name = str(node.tag).lower() if node.tag else ''
            if tag_name in _PROTECTED_TAGS:
                continue
            if node.contents is not None:
                _process_wikicode_safe(node.contents)

        elif node_type == 'ExternalLink':
            # Skip URL; process display title only
            if node.title is not None:
                _process_wikicode_safe(node.title)

        elif node_type == 'Template':
            # Process param values ONLY for infobox templates (containing 'bilgiquti').
            # Skip all other templates (cite book, sfn, lang-*, etc.).
            template_name = str(node.name).strip().lower()
            if 'bilgiquti' not in template_name:
                continue
            for param in node.params:
                _process_wikicode_safe(param.value)

        # Comment, HTMLEntity, Argument → skip

def fix_arabic_transliteration(wikitext: str) -> str:
    """
    Apply translation_rules.md Rules 1 and 2 deterministically.

    Rule 1: diacritic removal (ā→a, ī→i, ū→u, ḥ→h, ʿ→∅, ʾ→∅, etc.)
            with final -ī → -iy preservation.
    Rule 2: solar letter assimilation (al-Roziy → ar-Roziy, al-Shofiʼiy → ash-Shofiʼiy).

    Skips: <ref>...</ref>, URLs, template parameter values, link targets.

    Examples:
        Labīd            → Labid
        al-ʿĀmirī        → al-Amiriy
        al-Shofiʼiy      → ash-Shofiʼiy
        al-Tabariy       → at-Tabariy
        Muḥammad         → Muhammad
    """
    code = mwp.parse(wikitext, skip_style_tags=True)
    _process_wikicode_safe(code)
    return str(code)

def _apply_fix_outside_infoboxes(wikitext: str, fix_func) -> str:
    """
    Apply a regex-based fix function to wikitext, but skip infobox templates
    (templates containing 'bilgiquti' in their name).
    """
    code = mwp.parse(wikitext, skip_style_tags=True)

    # Collect infobox templates as strings (no AST manipulation)
    infoboxes = []
    for tpl in code.filter_templates():
        if 'bilgiquti' in str(tpl.name).strip().lower():
            infoboxes.append(str(tpl))

    # Replace each infobox with a placeholder via plain string replace
    text = wikitext
    placeholders = {}
    for i, infobox in enumerate(infoboxes):
        placeholder = f"@@INFOBOX_{i}@@"
        placeholders[placeholder] = infobox
        text = text.replace(infobox, placeholder, 1)

    # Apply fix to text without infoboxes
    text = fix_func(text)

    # Restore infoboxes
    for placeholder, original in placeholders.items():
        text = text.replace(placeholder, original)

    return text
def _apply_date_fixes(text: str) -> str:
    """Apply Rule 5a: hijri/milodi date formatting."""
    text = re.sub(
        r'\b(\d+)\s+(hijriy|milodiy)(?:\s+(yil(?:da|gacha|dan|ga|i|lar(?:i|da|dan|ga)?)?))?\b',
        lambda m: f"{m.group(2)} {m.group(1)}-{m.group(3) or 'yil'}",
        text
    )
    text = re.sub(r'\b(hijriy|milodiy)\s+(\d+)\b(?!\s*-)', r'\1 \2-yil', text)
    return fix_gregorian_dates(text)


_EN_MONTHS = {
    'january': 'yanvar', 'february': 'fevral', 'march': 'mart',
    'april': 'aprel', 'may': 'may', 'june': 'iyun', 'july': 'iyul',
    'august': 'avgust', 'september': 'sentyabr', 'october': 'oktyabr',
    'november': 'noyabr', 'december': 'dekabr',
}


def fix_gregorian_dates(text: str) -> str:
    """
    English full dates -> Uzbek date order.

        3 September 2018            -> 2018-yil 3-sentyabr
        September 3, 2018           -> 2018-yil 3-sentyabr
        September 3, 2018-yilga     -> 2018-yil 3-sentyabrga

    A case suffix the model already hung on the year moves to the month,
    which is now the last word of the date. Only called on article text and
    infobox values, so a citation's |date= parameter is never touched.
    """
    def uz(day: str, month: str, year: str, suffix) -> str:
        return f"{year}-yil {int(day)}-{_EN_MONTHS[month.lower()]}{suffix or ''}"

    text = re.sub(
        RegexPatterns.EN_DATE_DMY,
        lambda m: uz(m.group('d'), m.group('m'), m.group('y'), m.group('s')),
        text, flags=re.IGNORECASE,
    )
    return re.sub(
        RegexPatterns.EN_DATE_MDY,
        lambda m: uz(m.group('d'), m.group('m'), m.group('y'), m.group('s')),
        text, flags=re.IGNORECASE,
    )


_ERA_WORD = {'AH': 'hijriy', 'H': 'hijriy', 'CE': 'milodiy', 'AD': 'milodiy'}


def fix_era_abbreviations(text: str) -> str:
    """
    Drop the English AH/CE markers the model keeps next to an Uzbek year.

        hijriy 255-yil [[Islomiy taqvim|AH]] -> hijriy 255-yil
        hijriy 329-yil AH                    -> hijriy 329-yil
        255 [[Islomiy taqvim|AH]]            -> hijriy 255-yil
        868 CE                               -> milodiy 868-yil

    Call it through apply_outside_refs(): a citation may legitimately read
    "1417 AH".
    """
    text = re.sub(RegexPatterns.ERA_AFTER_UZ_YEAR, r'\1', text)
    return re.sub(
        RegexPatterns.ERA_AFTER_NUMBER,
        lambda m: f"{_ERA_WORD[m.group('era') or m.group('era2')]} {m.group('n')}-yil",
        text,
    )


# Top-level citation templates are masked with the refs: their titles quote
# the source verbatim.
_CITATION_TEMPLATE = r'\{\{\s*(?:cite\b|citation\b)[^{}]*\}\}'
_REF_OR_CITATION = re.compile(
    RegexPatterns.REF_TAG + r'|' + RegexPatterns.REF_SELF_CLOSING + r'|' + _CITATION_TEMPLATE,
    re.DOTALL | re.IGNORECASE,
)


def apply_outside_refs(wikitext: str, fix_func) -> str:
    """Apply a string fix to everything except references and citation templates."""
    saved = []

    def mask(match: re.Match) -> str:
        saved.append(match.group(0))
        return f"\x00{len(saved) - 1}\x00"

    text = fix_func(_REF_OR_CITATION.sub(mask, wikitext))
    return re.sub(r'\x00(\d+)\x00', lambda m: saved[int(m.group(1))], text)

def fix_template_blank_lines(wikitext: str) -> str:
    """Clean up multi-line template formatting."""
    code = mwp.parse(wikitext, skip_style_tags=True)
    
    for tpl in code.filter_templates():
        if not tpl.params:
            continue
        
        is_multiline = any('\n' in str(p) for p in tpl.params)
        if not is_multiline:
            continue
        
        # Clean blank lines inside param values
        for param in tpl.params:
            value_str = str(param.value)
            cleaned = re.sub(r'\n\s*\n+', '\n', value_str)
            if cleaned != value_str:
                param.value = cleaned
        
        # Ensure name ends with newline so first param starts on new line
        name_str = str(tpl.name)
        if not name_str.endswith('\n'):
            tpl.name = name_str.rstrip() + '\n'
    
    return str(code)