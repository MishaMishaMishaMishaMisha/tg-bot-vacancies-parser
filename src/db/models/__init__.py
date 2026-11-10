from .base import Base
from .user import UserModel
from .notification import NotificationStatus, NotificationModel
from .subscription import SubscriptionModel
from .vacancy import VacancyModel

__all__ = [
    "Base",
    "NotificationModel",
    "NotificationStatus",
    "SubscriptionModel",
    "UserModel",
    "VacancyModel",
]


"""
users          пользователи Telegram
subscriptions  наборы фильтров пользователя (у одного пользователя их может быть несколько)
vacancies      вакансии со всех сайтов; (source, external_id) уникальны
notifications  кому какая вакансия отправлена или должна быть отправлена
"""