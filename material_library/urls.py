from django.urls import path
from . import views
urlpatterns = [
 path('available/',views.Available.as_view()),
 path('items/',views.Items.as_view()),
 path('categories/',views.Categories.as_view()),
 path('libraries/',views.Libraries.as_view()),
 path('libraries/<uuid:pk>/items/',views.Items.as_view()),
 path('<str:target>/<uuid:pk>/favorite/',views.Favorite.as_view()),
 path('revisions/<int:pk>/download/',views.Download.as_view()),
 path('manage/<uuid:template>/',views.Manage.as_view()),
]
