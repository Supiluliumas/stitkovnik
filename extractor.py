"""Label extraction rules shared by the OCR service and tests."""
import re
import unicodedata

DEFAULT_RULES = {
    "S/N": ["S/N", "S / N", "S N", "S.N.", "SN", "Serial Number", "Serial No.", "Serial ID", "Serial", "Sériové číslo"],
    "MAC": ["MAC Address", "MAC Addr", "MAC", "MAC adresa"],
    "Model": ["Model", "Model No.", "Type", "Typ", "Product Model"],
    "Výrobce": ["Manufacturer", "Výrobce", "Brand", "Vendor"],
    "Napájení": ["Power Supply", "Power", "Input", "Voltage", "Rating", "Napájení"],
    "P/N": ["P/N", "Part Number", "Part No."],
    "Verze": ["Hardware Version", "HW Version", "HW", "Version", "Verze"],
}


def validate_rules(rules):
    if not isinstance(rules, dict) or not 2 <= len(rules) <= 40:
        raise ValueError("Pravidla musí obsahovat 2 až 40 polí.")
    if not all(key in rules for key in ("S/N", "MAC")):
        raise ValueError("Pravidla musí obsahovat pole S/N a MAC.")
    for key, aliases in rules.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 80:
            raise ValueError("Název pole musí mít 1 až 80 znaků.")
        if not isinstance(aliases, list) or not 1 <= len(aliases) <= 30:
            raise ValueError(f"Pole {key} musí mít 1 až 30 názvů ze štítku.")
        if any(not isinstance(a, str) or not a.strip() or len(a) > 80 for a in aliases):
            raise ValueError(f"Neplatný název ze štítku pro pole {key}.")
    return rules


def fold(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.translate(HOMOGLYPHS)) if not unicodedata.combining(c)).lower()


# Vision can return visually identical Cyrillic letters on Latin device labels.
HOMOGLYPHS = str.maketrans('АВСЕНІКМОРТХаесорху', 'ABCEHIKMOPTXaecopxy')


MAC_SEPARATED = re.compile(r"(?<![0-9a-z])(?:[0-9a-f]{2}(?:\s*[:\-]\s*|\s+)){5}[0-9a-f]{2}(?![0-9a-z])", re.I)
MAC_COMPACT = re.compile(r"(?<![0-9a-f])[0-9a-f]{12}(?![0-9a-f])", re.I)
MAC_DOTTED = re.compile(r"(?<![0-9a-f])(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}(?![0-9a-f])", re.I)


def normalize_macs(value, allow_compact=True):
    value = value.translate(HOMOGLYPHS).replace('–', '-').replace('—', '-')
    matches = []
    for pattern in [MAC_SEPARATED, MAC_DOTTED] + ([MAC_COMPACT] if allow_compact else []):
        for match in pattern.finditer(value):
            raw = re.sub(r"[^0-9a-f]", "", match.group(), flags=re.I).upper()
            normalized = ":".join(raw[i:i + 2] for i in range(0, 12, 2))
            if normalized not in matches:
                matches.append(normalized)
    return matches


def extract(text, rules=None):
    rules = validate_rules(rules if rules is not None else DEFAULT_RULES)
    fields = {key: "" for key in rules}
    aliases = []
    for key, names in rules.items():
        for name in names:
            escaped = re.escape(fold(name).rstrip("."))
            # OCR often drops spaces around the slash in S / N.
            escaped = escaped.replace(r"\ ", r"\s*")
            if key == 'S/N' and fold(name).replace(' ', '') == 's/n':
                escaped = r'(?:s\s*/\s*n|s\s*[i1|l]\s*n(?=\s*[:=#]))'
            aliases.append((key, name, escaped))
    aliases.sort(key=lambda item: len(item[1]), reverse=True)
    alternatives = "|".join(f"(?P<f{i}>{pattern})" for i, (_, _, pattern) in enumerate(aliases))
    pattern = re.compile(r"(?<![\w/])(?:" + alternatives + r")(?![\w/])\.?\s*[:=#]?\s*", re.I)
    original = unicodedata.normalize("NFC", text).replace("\r", "").replace("\u00a0", " ")
    normalized = fold(original)
    matches = list(pattern.finditer(normalized))
    for i, match in enumerate(matches):
        key = aliases[int(match.lastgroup[1:])][0]
        end = matches[i + 1].start() if i + 1 < len(matches) else len(original)
        # Normalized Czech characters preserve offsets on ordinary label text.
        value = original[match.end():end].strip().lstrip(":;=| \t")
        value = value.split("\n")[0].strip() if value else ""
        if value:
            if fields[key] and value != fields[key]:
                fields[key] += "; " + value
            else:
                fields[key] = value
    macs = normalize_macs(fields["MAC"]) if fields["MAC"] else normalize_macs(original, allow_compact=False)
    if macs:
        fields["MAC"] = "; ".join(macs)
    if 'Model' in fields and not fields['Model']:
        model = re.search(r'\b(?:DH\s*[-–—]\s*)?IPC(?:\s*[-–—]\s*[A-Z0-9]+)+\b|\b\d+(?:\.\d+)?[A-Z]?-[A-Z0-9]+(?:-[A-Z0-9]+){2,}\b', original, re.I)
        if model:
            fields['Model'] = re.sub(r'\s*[-–—]\s*', '-', model.group()).translate(HOMOGLYPHS)
    if "Výrobce" in fields and not fields["Výrobce"]:
        brand = re.search(r"\b(HIKVISION|DAHUA|AXIS|UNIVIEW|REOLINK|VIVOTEK|HANWHA|TP-LINK)\b", original, re.I)
        if brand:
            fields["Výrobce"] = brand.group().upper()
    if "Napájení" in fields and not fields["Napájení"]:
        power = re.search(r"\b\d+(?:[.,]\d+)?\s*V\s*(?:DC|AC)\b(?:\s*[,/]?\s*\d+(?:[.,]\d+)?\s*A\b)?", original, re.I)
        if power:
            fields["Napájení"] = power.group().strip()
        else:
            power = re.search(r'\b\d+(?:[.,]\d+)?\s*V(?:\b|DC|AC)[^\n]*', original, re.I)
            if power:
                fields['Napájení'] = power.group().strip()
    # Keep other explicitly labelled values as additional export columns.
    known = {fold(name).rstrip(".") for names in rules.values() for name in names}
    for line in original.splitlines():
        match = re.match(r"^\s*([^:=]{2,45})\s*[:=]\s*(.+?)\s*$", line)
        if match:
            key, value = match.groups()
            key = key.strip()
            if fold(key).rstrip(".") not in known and not pattern.search(fold(key)):
                fields.setdefault(key, value)
    warnings = []
    if not fields["S/N"]:
        warnings.append("Chybí S/N")
    if not fields["MAC"]:
        warnings.append("Chybí MAC")
    elif not macs:
        warnings.append("MAC nemá platný formát")
    elif len(macs) > 1:
        warnings.append("Více MAC adres – zkontrolujte přiřazení")
    if "; " in fields["S/N"]:
        warnings.append("Více sériových čísel – zkontrolujte přiřazení")
    return {"fields": fields, "warnings": warnings, "text": original}
