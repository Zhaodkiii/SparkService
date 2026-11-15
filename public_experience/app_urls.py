from django.urls import path
from .invitation_api import MyInvitation,Rewards
urlpatterns=[path('invitations/me/',MyInvitation.as_view()),path('rewards/',Rewards.as_view())]
