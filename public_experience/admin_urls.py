from django.urls import path
from .invitation_api import AdminInvitations
urlpatterns=[path('invitations/',AdminInvitations.as_view())]
