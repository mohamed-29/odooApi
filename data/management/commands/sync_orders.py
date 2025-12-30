# data/management/commands/sync_xy_orders.py
import os
import time
import hashlib
import requests
from decimal import Decimal
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction, connection

from data.models import xy_account as XYAccount, machine as Machine, Order  # adjust app label if different


# -----------------------------
# XY API client (login + orders)   (unchanged from previous message)
# -----------------------------
class XYApiClient:
    BASE_URL = "https://xcx.xynetweb.com"
    HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.xynetweb.com",
        "Referer": "https://www.xynetweb.com/",
        "Content-Type": "application/json;charset=UTF-8",
    }

    def __init__(self, username, password, logger):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.session_key = None
        self.logger = logger

    @staticmethod
    def _md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    def _get_check_code(self):
        url = f"{self.BASE_URL}/sram/comm/login/getCheckCode"
        r = self.session.get(url, timeout=10)
        r.raise_for_status()
        j = r.json()
        return j.get("data")

    def authenticate(self) -> bool:
        if self.session_key:
            return True
        try:
            check_code = self._get_check_code()
        except Exception as e:
            self.logger(f"[AUTH] getCheckCode failed: {e}")
            return False

        try:
            i1 = self._md5(self.username + self.password)
            hashed_password = self._md5(self.username + i1 + str(check_code))
            url = f"{self.BASE_URL}/sram/comm/login/onLogin"
            payload = {
                "password": hashed_password,
                "account": self.username,
                "checkCode": str(check_code),
                "language": "en",
                "channel": "1",
            }
            r = self.session.post(url, json=payload, timeout=15)
            r.raise_for_status()
            data = r.json()
            if data.get("code") == "H0000" and data.get("data", {}).get("session_key"):
                self.session_key = data["data"]["session_key"]
                self.session.headers.update({"Authorization": self.session_key})
                self.logger(f"[AUTH] OK for {self.username}")
                return True
            self.logger(f"[AUTH] Failed: {data.get('msg')} (code={data.get('code')})")
            return False
        except Exception as e:
            self.logger(f"[AUTH] onLogin failed: {e}")
            return False

    def query_orders(self, start: str, end: str, page_num=1, page_size=100, shbh=None, userid=None):
        """
        Returns (rows, total).
        Raises Exception if all retries fail.
        """
        max_retries = 5
        base_delay = 5  # seconds
        
        for attempt in range(1, max_retries + 1):
            if not self.authenticate():
                self.logger(f"[ORDERS] Auth failed, retrying... ({attempt}/{max_retries})")
                time.sleep(base_delay * attempt)
                continue
                
            url = f"{self.BASE_URL}/service-order/ddxx/queryDdxx"
            payload = {
                "jyz": -1, "ycd": -1, "orderBy": "cjsj desc",
                "pageNum": page_num, "pageSize": page_size,
                "shmc": "", "zjzt": "", "ywlx": "", "queryType": 0,
                "dsfshdh": "", "dsfjybh": "", "zfzt": "", "zffs": "", "zfzh": "",
                "chzt": "", "starttime": start, "endtime": end,
                "spxx": "", "language": "en", "channel": "1",
            }
            if shbh:
                payload["shbh"] = shbh
            if userid:
                payload["userid"] = userid
                
            try:
                r = self.session.post(url, json=payload, timeout=60)
                r.raise_for_status()
                data = r.json() or {}
                
                if data.get("code") != "H0000":
                    msg = data.get("msg")
                    code = data.get("code")
                    self.logger(f"[ORDERS] API error: {msg} (code={code}). Retrying... ({attempt}/{max_retries})")
                    time.sleep(base_delay * attempt)
                    continue

                block = data.get("data") or {}
                rows = block.get("data") or block.get("list") or []
                total = block.get("total") or len(rows)
                # drop summary row ""
                rows = [r for r in rows if r.get("shmc") != "本页小计"]
                return rows, int(total)

            except Exception as e:
                self.logger(f"[ORDERS] Request failed: {e}. Retrying... ({attempt}/{max_retries})")
                time.sleep(base_delay * attempt)
        
        raise Exception(f"Failed to query orders after {max_retries} attempts")


# -----------------------------
# Helpers (UPDATED)
# -----------------------------
def _parse_decimal(v, default=Decimal("0")) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return default

def _parse_dt_strict_zfsj(zfsj: str):
    """
    Strictly parse zfsj as the payment_time.
    If zfsj is missing or bad -> return None (we'll skip the row).
    """
    if not zfsj:
        return None
    s = str(zfsj).split(".")[0]
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return timezone.make_aware(dt, timezone.get_current_timezone())

def _extract_slot(row):
    ext2 = row.get("extend2")
    if isinstance(ext2, str) and ":" in ext2:
        return ext2.split(":", 1)[1].strip()
    return None

def _extract_product_name(row):
    ext2 = row.get("extend2")
    if isinstance(ext2, str) and ":" in ext2:
        return ext2.split(":", 1)[0].strip()
    return "Unknown"

def _payment_type(zffs):
    s = (zffs or "").lower()
    if s == "unionpay":
        return "card"
    return "cash" if s else None

def _payment_status(showzfzt, zfzt):
    if str(showzfzt).lower() == "paid":
        return "paid"
    if str(zfzt) in ("1", "paid"):
        return "paid"
    return "pending"

def _seven_day_chunks(start_dt, end_dt):
    """Yield (chunk_start, chunk_end) pairs covering [start_dt, end_dt), each <= 7 days,
    starting from end_dt and going backwards to start_dt."""
    cur = end_dt
    while cur > start_dt:
        prev = max(cur - timedelta(days=7), start_dt)
        yield (prev, cur)
        cur = prev


def _three_months_ago():
    # simple 90-day window
    return timezone.now() - timedelta(days=30)


# -----------------------------
# Command (UPDATED)
# -----------------------------
class Command(BaseCommand):
    help = "Fetch XY orders using provider uuid. Uses zfsj only. Splits into 7-day windows from oldest non-broken machine last_order to now. Auto-mark broken machines."

    def add_arguments(self, parser):
        parser.add_argument("--page-size", type=int, default=100, help="Page size (default 100)")
        parser.add_argument("--once", action="store_true", help="Run once and exit (no loop)")
        parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
        parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")

    def handle(self, *args, **opts):
        page_size = int(opts.get("page_size") or 100)
        loop_forever = not opts.get("once")
        start_arg = opts.get("start")
        end_arg = opts.get("end")

        self.stdout.write(self.style.SUCCESS("--- XY Orders sync (7-day chunks, zfsj-only) ---"))

        def log(msg):  # tiny logger
            self.stdout.write(f"  {msg}")

        while True:
            try:
                self._run_cycle(page_size, log, start_arg, end_arg)
                self.stdout.write(self.style.SUCCESS("[OK] cycle complete"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"[ERR] {e}"))
            finally:
                connection.close()

            if loop_forever:
                time.sleep(30)
            else:
                break

    def _mark_broken_flags(self, account):
        """
        Mark machines as broken if last_order < now-90d OR last_order is NULL.
        If you prefer NULL to be considered 'not broken', tweak here.
        """
        cutoff = _three_months_ago()
        qs = Machine.objects.filter(xy_account=account)
        updated_broken = 0
        updated_ok = 0
        for m in qs:
            was_broken = getattr(m, "is_broken", False)
            is_broken = (m.last_order is None) or (m.last_order < cutoff)
            if is_broken != was_broken:
                m.is_broken = is_broken
                m.save(update_fields=["is_broken"])
                updated_broken += 1 if is_broken else 0
                updated_ok += 0 if is_broken else 1
        return updated_broken, updated_ok

    def _compute_window(self, account, start_str=None, end_str=None):
        """
        If start_str/end_str provided, use them.
        Else start at OLDEST last_order among NON-broken machines.
        """
        tz_now = timezone.now()
        
        # 1. End date
        if end_str:
             try:
                dt_input = datetime.strptime(end_str, "%Y-%m-%d")
                # Make end of that day
                end_dt = timezone.make_aware(dt_input, timezone.get_current_timezone()) + timedelta(days=1)
             except ValueError:
                 end_dt = tz_now
        else:
            end_dt = tz_now.replace(second=0, microsecond=0) + timedelta(minutes=(60*24)+1)

        # 2. Start date
        if start_str:
            try:
                dt_input = datetime.strptime(start_str, "%Y-%m-%d")
                start_dt = timezone.make_aware(dt_input, timezone.get_current_timezone())
                return start_dt, end_dt
            except ValueError:
                pass

        # Auto calc logic
        non_broken = Machine.objects.filter(xy_account=account, is_broken=False).exclude(last_order__isnull=True)
        if non_broken.exists():
            oldest = non_broken.order_by("last_order").first().last_order
            if oldest > tz_now: # guard future
                 oldest = tz_now - timedelta(days=1)
            start_dt = oldest
        else:
            start_dt = tz_now - timedelta(days=90)

        return start_dt, end_dt

    @transaction.atomic
    def _upsert_row(self, row, acc):
        # 1) Strict payment time from zfsj (skip if missing)
        payment_time = _parse_dt_strict_zfsj(row.get("zfsj"))
        if payment_time is None:
            # temporary debug print
            # remove later if noisy
            self.stdout.write("    [SKIP] No zfsj in row with ddbh={}".format(row.get("ddbh")))
            return None, False

        # 2) Required unique key: provider UUID (simple)
        provider_uuid = row.get("uuid") or row.get("dsfjybh") or row.get("dsfshdh") or row.get("ddbh")
        if not provider_uuid:
            return None, False

        # 3) Extract fields
        machine_number = str(row.get("jqbh") or "")
        product_name = _extract_product_name(row)
        slot_number = _extract_slot(row)

        from decimal import Decimal
        payment_amount = _parse_decimal(row.get("zfje") or row.get("ddzj") or row.get("spzj") or Decimal("0"))
        payment_type = _payment_type(row.get("zffs"))
        payment_status = _payment_status(row.get("showzfzt"), row.get("zfzt"))
        source_order_no = row.get("ddbh") or row.get("dsfjybh") or row.get("dsfshdh")

        DELIVERY_STATE_MAP = {
            0: "Shipment Not Notified",
            1: "Shipment Notified",
            2: "Shipment Result Not Received",
            3: "Partial shipment",
            4: "Goods Shipped",
            5: "Shipment failed",
            6: "Notification Shipment Failure",
            7: "Shipment Timeout",
        }
        raw_chzt = row.get("chzt")
        try:
            chzt_int = int(raw_chzt)
        except (TypeError, ValueError):
            chzt_int = None
        delivery_state = DELIVERY_STATE_MAP.get(chzt_int, "Unknown")

        # 4) Machine upkeep (last_order + auto-unbreak)
        if machine_number:
            m, _ = Machine.objects.get_or_create(
                number=machine_number,
                defaults={"name": row.get("jqmc") or machine_number,"xy_account": acc}
            )
            if not m.name and row.get("jqmc"):
                m.name = row["jqmc"]
                m.save(update_fields=["name"])
            if not m.last_order or payment_time > m.last_order:
                m.last_order = payment_time
                m.save(update_fields=["last_order"])
            if getattr(m, "is_broken", False):
                m.is_broken = False
                m.save(update_fields=["is_broken"])

        # 5) SIMPLE idempotent upsert by uuid
        # Only create if it doesn't exist, do not update existing records
        obj, created = Order.objects.get_or_create(
            uuid=str(provider_uuid),
            defaults={
                "provider": "xy",
                "source_order_no": str(source_order_no) if source_order_no else None,
                "machine": Machine.objects.get(number=machine_number) if machine_number else None,
                "product_name": product_name,
                "slot_number": slot_number,
                "payment_amount": payment_amount,
                "payment_time": payment_time,
                "payment_type": payment_type,
                "payment_status": payment_status,
                "delivery_state": delivery_state,
                "source_payload": row,
                "sync_status": "pending",
            },
        ) 
        return obj, created
    def _run_cycle(self, page_size, log, start_str=None, end_str=None):
        accounts = XYAccount.objects.all()
        if not accounts.exists():
            log("[WARN] No XY accounts configured.")
            return

        for acc in accounts:
            log(f"[ACCOUNT] {acc.username}")

            # 1) mark broken flags first
            broken_upd, ok_upd = self._mark_broken_flags(acc)
            if broken_upd or ok_upd:
                log(f"[MACHINES] broken updated: {broken_upd}, un-broken updated: {ok_upd}")

            # 2) compute window 
            start_dt, end_dt = self._compute_window(acc, start_str, end_str)
            log(f"[WINDOW] {start_dt} → {end_dt} (split by 7 days)")

            client = XYApiClient(acc.username, acc.password, log)
            acc_shbh = (acc.shbh or "").strip()
            acc_userid = (acc.userid or "").strip()

            # 3) iterate 7-day chunks
            for chunk_start, chunk_end in _seven_day_chunks(start_dt, end_dt):
                s = chunk_start.strftime("%Y-%m-%d %H:%M:%S")
                e = chunk_end.strftime("%Y-%m-%d %H:%M:%S")
                log(f"[CHUNK] {s} → {e}")

                page = 1
                while True:
                    try:
                        rows, total = client.query_orders(s, e, page_num=page, page_size=page_size, shbh=acc_shbh, userid=acc_userid)
                        
                        # AGGRESSIVE RETRY FOR EMPTY RESULTS
                        # The user suspects API returns 0 rows due to load, even if data exists.
                        # We retry 5 times with increasing backoff if we get 0 rows but page < total? 
                        # Or just if we get 0 rows at all? 
                        # "if success and no data try 5 times"
                        if not rows:
                           max_empty_retries = 5
                           for attempt in range(1, max_empty_retries + 1):
                               delay = attempt * 5 if attempt < 3 else 30 # 5, 10, 30, 30, 30
                               log(f"       [EMPTY RETRY] Got 0 rows. Retrying {attempt}/{max_empty_retries} in {delay}s...")
                               time.sleep(delay)
                               
                               # Retry the query
                               r_rows, r_total = client.query_orders(s, e, page_num=page, page_size=page_size, shbh=acc_shbh, userid=acc_userid)
                               if r_rows:
                                   rows = r_rows
                                   total = r_total
                                   log(f"       [EMPTY RETRY SUCCESS] Got {len(rows)} rows on attempt {attempt}")
                                   break
                           else:
                               log("       [EMPTY RETRY GAVE UP] Still 0 rows.")

                    except Exception as err:
                        log(f"[CHUNK ERR] {err}. Moving to next chunk/cycle.")
                        break # Stop pagination for this chunk if we fully fail, move to next

                    log(f"[PAGE] page={page} got={len(rows)} total={total}")
                    if rows:
                        uuid_ex = rows[0].get('uuid') or rows[0].get('dsfjybh') or "N/A"
                        log(f"       first uuid={uuid_ex} jqbh={rows[0].get('jqbh')} zfsj={rows[0].get('zfsj')}")

                    if not rows:
                        break

                    for r in rows:
                        try:
                            _, _ = self._upsert_row(r, acc)
                        except Exception as ex:
                            self.stderr.write(self.style.ERROR(f"    [ROW ERR] {ex} | payload={str(r)[:300]}"))

                    if page * page_size >= total:
                        break
                    page += 1
                    time.sleep(2) # mild polite delay between pages
