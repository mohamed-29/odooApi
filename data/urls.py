from django.urls import path
from .views import TotalSalesView, SalesReportView

urlpatterns = [
    path('total-sales/', TotalSalesView.as_view(), name='total-sales'),
    path('sales-report/', SalesReportView.as_view(), name='sales-report'),
]
