# data/signals.py
import requests
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order

# Static destination
base = "https://vooapp-qas-26188372.dev.odoo.com/"
direction = "/vending/create_order_by_name"
api_key = "96afae44eba442fd8f3878c0ca9847212e0441c09861a7da749c9af4227ec110"

@receiver(post_save, sender=Order)
def send_order_webhook(sender, instance: Order, created: bool, **kwargs):
    """Send order data as JSON to a fixed test endpoint whenever created or updated."""
    print("OK")
    url = base.rstrip("/") + direction

    data = {
        "uuid": instance.uuid,
        "machine_number": instance.machine.number,
        "pos_id": 1,
        "product_name": "Gift Card",
        "delivery_state": instance.delivery_state,
        "purchase_date": instance.payment_time.strftime('%Y-%m-%d %H:%M:%S') if instance.payment_time else None,

        # "purchase_date": instance.payment_time.isoformat() if instance.payment_time else None,
        "price": float(instance.payment_amount or 0),
        "payment_method_id": 2,
        "created": created,
    }

    if instance.machine.number == "2501000832":
        try:
            headers = {
                "Authorization": f"{api_key}",
                "Content-Type": "application/json",
            }
            response = requests.post(url, json=data, headers=headers, timeout=10)

            response.raise_for_status() # Raise an exception for HTTP errors
            print(f"[WEBHOOK SUCCESS] Status: {response.status_code}, Response: {response.text}")
        except Exception as e:
            print(f"[WEBHOOK ERROR] {e}")
