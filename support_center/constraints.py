"""One authoritative set of limits for API validation and client guidance."""
SUBMISSION_LIMITS = {
    'title_max': 60,
    'description_min': 10,
    'description_max': 2000,
    'contact_max': 100,
    'attachments_max': 6,
    'attachment_bytes_max': 10_000_000,
}
