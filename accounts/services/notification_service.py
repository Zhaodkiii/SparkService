from notification_center.services import NotificationCenterService


class NotificationService(NotificationCenterService):
    """Compatibility facade for legacy imports.

    New code should import from `notification_center.services` directly.
    """

    pass
