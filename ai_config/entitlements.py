"""Client AI trial access, independent of the retired subscription service."""
from ai_config.services import TrialService

class ProEntitlementResolver:
    @staticmethod
    def is_pro_user(*, user) -> bool:
        return bool(TrialService.build_pro_summary(user=user)["is_pro"])
