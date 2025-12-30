from django.urls import path
from .views import TotalSalesView, SalesReportView, MachinesTotalSalesView

urlpatterns = [
    path('total-sales/', TotalSalesView.as_view(), name='total-sales'),
    path('machines-total-sales/', MachinesTotalSalesView.as_view(), name='machines-total-sales'),
    path('sales-report/', SalesReportView.as_view(), name='sales-report'),
]
