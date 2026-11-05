from django.urls.converters import UUIDConverter


class ProductionUUIDConverter(UUIDConverter):
    """Accept UUIDs serialized by both Foundation and Python."""
    regex = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
