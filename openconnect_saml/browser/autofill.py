"""Build Qt's form-fill script without depending on a Qt installation."""

import json


def get_selectors(rules, credentials):
    statements = []
    username_only = getattr(credentials, "username_only", False)
    for rule in rules:
        selector = json.dumps(rule.selector)
        if rule.action == "stop":
            statements.append(
                f"var elem = document.querySelector({selector}); if (elem) {{ return; }}"
            )
        elif rule.fill:
            raw_value = getattr(credentials, rule.fill, None)
            if raw_value is None or raw_value == "":
                continue
            value = json.dumps(raw_value)
            statements.append(
                f"""var elem = document.querySelector({selector});
if (elem && !elem.value) {{
    elem.dispatchEvent(new Event("focus"));
    elem.value = {value};
    elem.dispatchEvent(new Event("change", {{bubbles: true}}));
    elem.dispatchEvent(new Event("input", {{bubbles: true}}));
    elem.dispatchEvent(new Event("blur"));
}}"""
            )
        elif rule.action == "click" and not username_only:
            statements.append(
                f"""var elem = document.querySelector({selector});
if (elem) {{ elem.dispatchEvent(new Event("focus")); elem.click(); }}"""
            )
    return "\n".join(statements)
