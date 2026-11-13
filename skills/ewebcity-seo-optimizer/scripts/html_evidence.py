"""Pure HTML/HTTP evidence helpers; no fetching, rendering or index assertions."""
from __future__ import annotations

import codecs
from html.parser import HTMLParser
import re


ROBOT_FLAGS = frozenset({"all", "index", "follow", "noindex", "nofollow", "none", "noarchive",
    "nosnippet", "notranslate", "noimageindex", "indexifembedded", "nositelinkssearchbox"})
ROBOT_PARAMETERS = frozenset({"max-snippet", "max-image-preview", "max-video-preview", "unavailable_after"})
WEB_TEXT_CODECS = frozenset({"utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp874",
    "cp1250", "cp1251", "cp1252", "cp1253", "cp1254", "cp1255", "cp1256", "cp1257", "cp1258",
    "iso8859-2", "iso8859-3", "iso8859-4", "iso8859-5", "iso8859-6", "iso8859-7", "iso8859-8",
    "iso8859-9", "iso8859-10", "iso8859-13", "iso8859-14", "iso8859-15", "iso8859-16",
    "koi8-r", "koi8-u", "mac-roman", "mac-cyrillic", "gbk", "gb18030", "big5", "shift_jis",
    "cp932", "euc_jp", "iso2022_jp", "euc_kr", "cp949"})


def header_fields(headers: dict, header_values: dict | None, name: str) -> list[str]:
    """Prefer actual field boundaries over the compatibility comma-joined map."""
    name = name.lower()
    raw = {key.lower(): value for key, value in (header_values or {}).items()}
    if name in raw:
        value = raw[name]
    else:
        value = {key.lower(): value for key, value in headers.items()}.get(name, [])
    return [str(item) for item in value] if isinstance(value, (list, tuple)) else [str(value)]


def robots_evidence(meta: list[dict], headers: dict, header_values: dict | None = None) -> dict:
    """Recognise directive names separately from arguments and preserve UA scope.

    Separate HTTP fields each start in global scope. An explicit crawler prefix
    affects the remaining directives in that field, not following header fields.
    Unknown values are retained rather than interpreted as indexing decisions.
    """
    observations: list[dict] = []
    pieces_seen = 0
    parsing_limited = False
    fields = [(f"meta:{item['agent']}", "*" if item["agent"] == "robots" else item["agent"], item["content"], False)
              for item in meta]
    fields.extend(("http:x-robots-tag", "*", value, True)
                  for value in header_fields(headers, header_values, "x-robots-tag"))
    for field_index, (source, default_agent, value, scoped) in enumerate(fields):
        agent = default_agent.lower()
        groups: dict[str, dict] = {}
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            pieces_seen += 1
            if pieces_seen > 256:
                parsing_limited = True
                break
            prefix = re.match(r"^([a-z0-9_*.-]+)\s*:\s*(.*)$", part, re.I)
            if scoped and prefix and prefix.group(1).lower() not in ROBOT_PARAMETERS | ROBOT_FLAGS:
                # The scope exists even when its first directive is unfamiliar.
                # Otherwise `otherbot: unknown, noindex` would become global.
                agent, part = prefix.group(1).lower(), prefix.group(2).strip()
            record = groups.setdefault(agent, {"source": source, "field_index": field_index,
                "agent": agent, "value": value[:1000], "value_truncated": len(value) > 1000,
                "directives": [], "parameters": [], "unrecognised": []})
            key, separator, argument = part.partition(":")
            key = key.strip().lower()
            if not separator and key in ROBOT_FLAGS:
                record["directives"].append(key)
            elif separator and key in ROBOT_PARAMETERS:
                record["parameters"].append({"name": key, "value": argument.strip()[:512]})
                argument = argument.strip().lower()
                if (key == "max-image-preview" and argument not in {"none", "standard", "large"}) or (
                    key in {"max-snippet", "max-video-preview"} and not re.fullmatch(r"-1|\d+", argument)):
                    record["unrecognised"].append(part[:512])
            elif not separator and all(token in ROBOT_FLAGS for token in part.lower().split()):
                record["directives"].extend(part.lower().split())
            elif record["parameters"] and record["parameters"][-1]["name"] == "unavailable_after" and re.match(r"^\d", part):
                # Preserve a comma in an HTTP-style date; do not interpret it as
                # a separate robots flag or infer whether the date has expired.
                record["parameters"][-1]["value"] = (record["parameters"][-1]["value"] + ", " + part)[:512]
            else:
                record["unrecognised"].append(part[:512])
        for record in groups.values():
            record["directives"] = list(dict.fromkeys(record["directives"]))
        observations.extend(groups.values())
        if parsing_limited:
            break
    noindex = [{"source": item["source"], "field_index": item["field_index"], "agent": item["agent"],
                "value": item["value"], "directives": item["directives"]}
               for item in observations if set(item["directives"]) & {"noindex", "none"}]
    # Arbitrary crawler tokens remain in observations. Summarising every distinct
    # untrusted token against every global directive would amplify input size.
    agents = ("googlebot", "googlebot-news", "bingbot")
    scopes = {}
    for agent in agents:
        applicable = [item for item in observations if item["agent"] in ("*", agent)]
        flags = {value for item in applicable for value in item["directives"]}
        expanded = flags | ({"noindex", "nofollow"} if "none" in flags else set()) | ({"index", "follow"} if "all" in flags else set())
        scopes[agent] = {"observed_flags": sorted(flags),
            "complete": not parsing_limited and not any(item["unrecognised"] for item in applicable),
            "noindex": "noindex" in expanded, "nofollow": "nofollow" in expanded,
            "indexifembedded": "indexifembedded" in expanded,
            "conflicts": [f"{positive}/{negative}" for positive, negative in (("index", "noindex"), ("follow", "nofollow"))
                          if positive in expanded and negative in expanded],
            "noindex_sources": [item for item in noindex if item["agent"] in ("*", agent)]}
    return {"observations": observations, "noindex_observations": noindex, "by_agent": scopes,
        "parsing_limited": parsing_limited, "directive_piece_limit": 256,
        "scope_note": "Global and exactly matching crawler declarations are combined; engine-specific enforcement and actual indexing were not verified.",
        "raw_header_fields_preserved": bool(header_values and "x-robots-tag" in {key.lower() for key in header_values})}


def _split_quoted(value: str, delimiter: str) -> list[str]:
    result, start = [], 0
    quoted = escaped = False
    angle = 0
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted:
            if char == "<":
                angle += 1
            elif char == ">":
                angle = max(0, angle - 1)
            elif char == delimiter and not angle:
                result.append(value[start:index].strip())
                start = index + 1
    result.append(value[start:].strip())
    return result


def link_header_evidence(headers: dict, header_values: dict | None = None) -> dict:
    """Parse Link field syntax sufficiently to retain canonical/alternate facts.

    This does not fetch targets or apply link anchors to other resource contexts.
    """
    links, invalid = [], []
    parsing_limited = False
    for raw in header_fields(headers, header_values, "link"):
        for item in _split_quoted(raw, ","):
            if len(links) + len(invalid) >= 200:
                parsing_limited = True
                break
            match = re.match(r"^<([^>]*)>\s*(.*)$", item, re.S)
            if not match:
                if item:
                    invalid.append(item[:500])
                continue
            parameters: dict[str, list[str]] = {}
            malformed = bool(match.group(2).strip() and not match.group(2).lstrip().startswith(";"))
            for parameter in _split_quoted(match.group(2), ";"):
                if not parameter:
                    continue
                key, separator, value = parameter.partition("=")
                if not separator or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key.strip()):
                    malformed = True
                    continue
                value = value.strip()
                if value.startswith('"'):
                    if not re.fullmatch(r'"(?:[^"\\]|\\.)*"', value, re.S):
                        malformed = True
                        continue
                    value = re.sub(r"\\(.)", r"\1", value[1:-1])
                elif not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", value):
                    malformed = True
                    continue
                parameters.setdefault(key.strip().lower(), []).append(value)
            if malformed:
                invalid.append(item[:500])
            links.append({"href": match.group(1), "relations": parameters.get("rel", [""])[0].lower().split(),
                "hreflang": parameters.get("hreflang", [None])[0],
                "anchor": parameters.get("anchor", [None])[0], "source": "http:link", "malformed": malformed})
        if parsing_limited:
            break
    return {"links": links, "invalid": invalid, "parsing_limited": parsing_limited, "annotation_limit": 200, "unassessed": [
        {"href": item["href"], "anchor": item["anchor"], "reason": "Link anchor changes the resource context; this auditor does not apply anchored canonical/alternate annotations."}
        for item in links if item["anchor"] is not None and ("canonical" in item["relations"] or
            ("alternate" in item["relations"] and item["hreflang"] is not None))]}


class _EncodingPrescan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.labels: list[str] = []
        self.inert = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("template", "noscript"):
            self.inert += 1
        if self.inert:
            return
        if tag in ("textarea", "title"):
            self.set_cdata_mode(tag)
        if tag == "meta":
            values = {}
            for key, value in attrs:
                values.setdefault(key, value)
            if values.get("charset"):
                self.labels.append(values["charset"])
            elif (values.get("http-equiv") or "").strip().lower() == "content-type":
                match = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", values.get("content") or "", re.I)
                if match:
                    self.labels.append(match.group(1))

    def handle_endtag(self, tag):
        if tag in ("template", "noscript"):
            self.inert = max(0, self.inert - 1)


def decode_html(body: bytes, headers: dict) -> tuple[str, dict]:
    """Use BOM, declared HTTP charset, then a bounded source-meta prescan.

    Undeclared input uses an explicit UTF-8 default, not a claim about the browser
    or a statistical guess. Diagnostics disclose unsupported labels/replacements.
    """
    declarations = []
    if body.startswith(codecs.BOM_UTF8):
        declarations.append(("bom", "utf-8-sig"))
    elif body.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        declarations.append(("bom", "utf-16"))
    content_type = {key.lower(): value for key, value in headers.items()}.get("content-type", "")
    match = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", content_type, re.I)
    if match:
        declarations.append(("http", match.group(1)))
    prescan = _EncodingPrescan()
    prescan.feed(body[:1024].decode("latin-1"))
    prescan.close()
    declarations.extend(("meta", value) for value in prescan.labels)
    unsupported = []
    chosen = ("default", "utf-8")
    for source, raw_label in declarations:
        label = raw_label.strip().lower()
        if label in {"ascii", "us-ascii", "iso-8859-1", "iso8859-1", "latin1", "latin-1", "l1", "x-user-defined"}:
            label = "windows-1252"
        try:
            codec = codecs.lookup(label)
            # Python also exposes transforms and non-web codecs under charset
            # names. Restrict to actual text encodings and reject known unsafe or
            # unsupported HTML encodings rather than executing a transform.
            if not getattr(codec, "_is_text_encoding", True) or codec.name in {"utf-7", "utf-32", "utf-32-le", "utf-32-be", "unicode-escape", "raw-unicode-escape"}:
                raise LookupError("Unsupported HTML encoding")
            if codec.name in {"ascii", "iso8859-1"}:
                label, codec = "windows-1252", codecs.lookup("windows-1252")
            if source == "meta" and codec.name in {"utf-16", "utf-16-le", "utf-16-be"}:
                # Apply the source-meta rule to the resolved codec so Python
                # aliases such as `utf16` cannot reinterpret ASCII markup.
                label, codec = "utf-8", codecs.lookup("utf-8")
            if codec.name not in WEB_TEXT_CODECS:
                raise LookupError("Charset is outside the supported web text encodings")
            if codec.name == "utf-16" and source != "bom":
                label = "utf-16-le"
            b"".decode(label)
            chosen = (source, label)
            break
        except (LookupError, TypeError, ValueError):
            unsupported.append({"source": source, "label": raw_label})
    had_errors = False
    try:
        text = body.decode(chosen[1], errors="strict")
    except UnicodeError:
        had_errors = True
        text = body.decode(chosen[1], errors="replace")
    return text, {"encoding": chosen[1], "source": chosen[0], "declarations": [{"source": source, "label": label} for source, label in declarations],
        "unsupported_declarations": unsupported, "had_errors": had_errors,
        "replacement_character_count": text.count("\ufffd") if had_errors else 0,
        "default_used": chosen[0] == "default", "browser_encoding_verified": False}
