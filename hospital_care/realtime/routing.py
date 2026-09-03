from django.urls import path

from hospital_care.realtime.doctor_conversation_consumer import DoctorConversationConsumer

websocket_urlpatterns = [
    path("ws/hospital/doctor/conversations/", DoctorConversationConsumer.as_asgi()),
]
