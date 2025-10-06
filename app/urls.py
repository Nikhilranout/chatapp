from django.urls import path
from .views import*


urlpatterns = [
    path('',home,name="home"),
    path("chat/", chat, name="chat"),
    path('signup/',signup,name="signup"),
    path('login/',login,name="login"),
    path('logout/', logoutuser, name="logout"),
    path('user/',user,name='user')
]
