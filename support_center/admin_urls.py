from django.urls import path
from . import views as v
from rest_framework.permissions import IsAuthenticated, BasePermission
from .services import permit
class SupportUploadPermission(BasePermission):
    def has_permission(self,request,view):return permit(request.user,"reply_ticket")

def admin(view):return view.as_view(admin=True,permission_classes=[IsAuthenticated])
urlpatterns=[path('reply-templates/',v.ReplyTemplates.as_view()),path('uploads/',v.Uploads.as_view(permission_classes=[SupportUploadPermission])),path('uploads/<uuid:pk>/complete/',v.CompleteUpload.as_view(permission_classes=[SupportUploadPermission])),path('help/images/',v.HelpImages.as_view()),path('help/images/<uuid:pk>/complete/',v.HelpImageComplete.as_view()),path('help/images/<uuid:pk>/url/',admin(v.HelpImageURL)),path('config/',admin(v.Configuration)),path('help/categories/',admin(v.Categories)),
 path('help/articles/',admin(v.Articles)),path('help/articles/<uuid:pk>/',admin(v.ArticleDetail)),
 path('help/articles/<uuid:pk>/versions/',v.Versions.as_view()),
 path('help/articles/<uuid:pk>/<str:action>/',admin(v.ArticleDetail)),
 path('tickets/',admin(v.Tickets)),path('tickets/<uuid:pk>/',admin(v.Detail)),
 path('tickets/<uuid:pk>/messages/',admin(v.Messages)),path('tickets/<uuid:pk>/actions/',admin(v.Actions)),
 path('tickets/<uuid:pk>/read/',admin(v.Read)),path('tickets/<uuid:pk>/assign/',v.Assign.as_view()),
 path('tickets/<uuid:pk>/redactions/',v.Redact.as_view()),path('tickets/<uuid:pk>/audit/',v.Audits.as_view()),
 path('operators/',v.Operators.as_view()),path('attachments/<uuid:pk>/url/',admin(v.AttachmentURL))]
