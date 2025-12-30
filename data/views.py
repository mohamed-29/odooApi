from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum
from .models import Order, machine
from .serializers import OrderSerializer
from datetime import datetime

# Create your views here.

class TotalSalesView(APIView):
    def get(self, request):
        machine_number = request.query_params.get('machine_number')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not all([machine_number, start_date, end_date]):
            return Response(
                {"error": "machine_number, start_date, and end_date are required parameters."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Look up machine by number assuming 'number' field
            # The model has 'number' field.
            # Convert strings to date objects if necessary or rely on Django's field lookup
            
            # Using __date range or simple range depending on if input is datetime or date
            # Assuming input is YYYY-MM-DD
            
            sales = Order.objects.filter(
                machine__number=machine_number,
                payment_time__date__gte=start_date,
                payment_time__date__lte=end_date,
            ).aggregate(total_sales=Sum('payment_amount'))

            total = sales['total_sales'] or 0.00

            return Response({"machine_number": machine_number, "total_sales": total})

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MachinesTotalSalesView(APIView):
    def get(self, request):
        machine_numbers_param = request.query_params.get('machine_numbers')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not all([machine_numbers_param, start_date, end_date]):
            return Response(
                {"error": "machine_numbers (comma separated), start_date, and end_date are required parameters."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            machine_numbers = [num.strip() for num in machine_numbers_param.split(',')]
            
            sales = Order.objects.filter(
                machine__number__in=machine_numbers,
                payment_time__date__gte=start_date,
                payment_time__date__lte=end_date,
                payment_status='paid'
            ).aggregate(total_sales=Sum('payment_amount'))

            total = sales['total_sales'] or 0.00

            return Response({"machine_numbers": machine_numbers, "total_sales": total})

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SalesReportView(ListAPIView):
    serializer_class = OrderSerializer

    def get_queryset(self):
        machine_number = self.request.query_params.get('machine_number')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if not all([machine_number, start_date, end_date]):
            return Order.objects.none()

        return Order.objects.filter(
            machine__number=machine_number,
            payment_time__date__gte=start_date,
            payment_time__date__lte=end_date
        ).order_by('-payment_time')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists() and not all([request.query_params.get('machine_number'), request.query_params.get('start_date'), request.query_params.get('end_date')]):
             return Response(
                {"error": "machine_number, start_date, and end_date are required parameters."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
