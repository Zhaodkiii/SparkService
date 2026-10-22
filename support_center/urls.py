from django.urls import path
from . import views as v
urlpatterns=[
 path('help/images/<uuid:pk>/url/',v.HelpImageURL.as_view()),path('submission/',v.Submission.as_view()),path('config/',v.Configuration.as_view()),path('help/categories/',v.Categories.as_view()),
 path('help/articles/',v.Articles.as_view()),path('help/articles/<uuid:pk>/',v.ArticleDetail.as_view()),
 path('tickets/',v.Tickets.as_view()),path('tickets/<uuid:pk>/',v.Detail.as_view()),
 path('tickets/<uuid:pk>/messages/',v.Messages.as_view()),path('tickets/<uuid:pk>/actions/',v.Actions.as_view()),
 path('tickets/<uuid:pk>/read/',v.Read.as_view()),path('summary/',v.Summary.as_view()),
 path('uploads/',v.Uploads.as_view()),path('uploads/<uuid:pk>/complete/',v.CompleteUpload.as_view()),
 path('uploads/<uuid:pk>/',v.CompleteUpload.as_view()),path('attachments/<uuid:pk>/url/',v.AttachmentURL.as_view())]
