def mask_email(value):
    if not value or "@" not in value:
        return value
    name, domain = value.split("@", 1)
    return f"{name[:2]}***@{domain}"


def mask_phone(value):
    if not value:
        return value
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def mask_document(value):
    if not value:
        return value
    digits = "".join(char for char in value if char.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"

