from django.urls import path
from . import views

urlpatterns = [
    # Company Management
    path('', views.CompanyListView.as_view(), name='company-list'),
    path('<int:pk>/', views.CompanyDetailView.as_view(), name='company-detail'),
    path('<int:pk>/update/', views.CompanyUpdateView.as_view(), name='company-update'),
    
    # My Companies
    path('my-companies/', views.MyCompaniesView.as_view(), name='my-companies'),
    
    # Company Actions
    path('<int:company_id>/dashboard/', views.company_dashboard, name='company-dashboard'),
    path('<int:company_id>/verify/', views.verify_company, name='verify-company'),
    path('<int:company_id>/deactivate/', views.deactivate_company, name='deactivate-company'),
]
