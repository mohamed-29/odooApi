from django.db import models
from django.utils import timezone


# Create your models here.

class xy_account(models.Model):
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    shbh = models.CharField(max_length=255, null=True, blank=True)
    userid = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.username
    


class machine (models.Model):
    name = models.CharField(max_length=100)
    number = models.CharField(max_length=100)
    is_online = models.BooleanField(default=False)
    is_broken = models.BooleanField(default=False)
    last_online = models.DateTimeField(null=True, blank=True)
    last_order = models.DateTimeField(null=True, blank=True)
    last_update = models.DateTimeField(auto_now_add=True)
    xy_account = models.ForeignKey(xy_account, on_delete=models.CASCADE, null=True, blank=True)


    def __str__(self):
        return self.name
    


class Order(models.Model):
    # ---- Source identity (SIMPLE) ----
    uuid = models.CharField(max_length=64, unique=True, db_index=True)  # required now
    provider = models.CharField(max_length=50, default="xy", db_index=True)
    source_order_no = models.CharField(max_length=128, null=True, blank=True, db_index=True)

    # ---- Business fields ----
    machine = models.ForeignKey(machine, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=255, default="Unknown")
    slot_number = models.CharField(max_length=50, null=True, blank=True)
    payment_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_time = models.DateTimeField(db_index=True)
    payment_type = models.CharField(max_length=20, null=True, blank=True)
    payment_status = models.CharField(max_length=20, default="paid")
    delivery_state = models.CharField(max_length=64, null=True, blank=True)

    # Debug / re-mapping
    source_payload = models.JSONField(null=True, blank=True)

    # Outbound sync tracking
    sync_status = models.CharField(max_length=20, default="pending", db_index=True)
    sync_endpoint = models.CharField(max_length=255, default="orders-receiver")
    external_id = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    last_sync_error = models.TextField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)

    # housekeeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["provider", "source_order_no"]),
            models.Index(fields=["payment_time"]),
            models.Index(fields=["sync_status"]),
        ]