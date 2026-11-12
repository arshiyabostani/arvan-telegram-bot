"""User-facing strings (English and Persian).

``Translator`` HTML-escapes every format argument, so handlers cannot forget to
escape user-controlled data. Templates may contain Telegram HTML tags.
"""

from __future__ import annotations

import html

EN: dict[str, str] = {
    "rate_limited": "Slow down a little.",
    "session_expired": "This session expired. Send /start to begin again.",
    "flow_expired": "That action expired. Start again from the menu.",
    "read_only": "The bot is in read-only mode. This action is disabled.",
    "domain_not_allowed": "This domain is not allowed for the bot.",
    "unexpected_error": "Something went wrong. Check the bot logs.",
    "api_error": "Arvan API error: {detail}",
    "invalid_input": "Invalid input: {detail}\nTry again or /cancel.",
    "text_hint": "Send /start to open the menu.",
    "help": (
        "<b>Arvan CDN bot</b>\n/start  choose a domain\n/cancel  abort the current action\n/help  show this message"
    ),
    "home": "<b>ArvanCloud CDN</b>\nChoose a domain:",
    "home_empty": "No domains found for this API key.",
    "menu": "Domain: <b>{domain}</b>\nWhat do you want to do?",
    "btn_records": "DNS records",
    "btn_add": "Add record",
    "btn_purge_all": "Purge all cache",
    "btn_purge_urls": "Purge URLs",
    "btn_info": "Domain info",
    "btn_back": "Back",
    "btn_domains": "Domains",
    "btn_cancel": "Cancel",
    "btn_yes_delete": "Yes, delete",
    "btn_yes_purge": "Yes, purge",
    "btn_create": "Create",
    "btn_cloud_on": "Turn cloud on",
    "btn_cloud_off": "Turn cloud off",
    "btn_delete": "Delete",
    "btn_cloud_yes": "Proxied (cloud)",
    "btn_cloud_no": "DNS only",
    "records": "DNS records of <b>{domain}</b> ({count})\n🟠 proxied by Arvan, ⚪ DNS only",
    "record": (
        "<b>{name}</b>.{domain}\nType: <code>{type}</code>\nValue: <code>{value}</code>\n"
        "TTL: <code>{ttl}</code>\nCloud: {cloud}\nID: <code>{id}</code>"
    ),
    "cloud_on": "on",
    "cloud_off": "off",
    "delete_confirm": "Delete <b>{desc}</b>? This cannot be undone.",
    "deleted": "Record deleted.",
    "add_type": "Choose the record type:",
    "add_name": "Send the record name (<code>@</code> for the zone apex):",
    "add_value_a": "Send an IPv4 address, for example <code>203.0.113.10</code>",
    "add_value_aaaa": "Send an IPv6 address, for example <code>2001:db8::1</code>",
    "add_value_cname": "Send the target host, for example <code>target.example.com</code>",
    "add_value_aname": "Send the target host, for example <code>target.example.com</code>",
    "add_value_txt": "Send the text value.",
    "add_value_mx": "Send priority and host, for example <code>10 mail.example.com</code>",
    "add_value_ns": "Send the name server host, for example <code>ns1.example.com</code>",
    "add_ttl": "Choose a TTL:",
    "add_cloud": "Route this record through the Arvan CDN?",
    "add_confirm": (
        "Create this record?\n<b>{name}</b>.{domain}  <code>{type}</code>\n"
        "Value: <code>{value}</code>\nTTL: <code>{ttl}</code>\nCloud: {cloud}"
    ),
    "created": "Record created.",
    "cancelled": "Cancelled.",
    "purge_all_confirm": (
        "Purge the whole cache of <b>{domain}</b>? Load on your origin can spike while the cache refills."
    ),
    "purge_ok": "Purge request accepted.",
    "purge_urls_prompt": (
        "Send the URLs to purge, one per line. Only URLs on <b>{domain}</b> and its "
        "subdomains are accepted (max {max})."
    ),
    "purge_urls_ok": "Purge request accepted for {count} URL(s).",
    "info_line": "• {label}: <code>{value}</code>",
    "info_status": "Status",
    "info_plan": "Plan level",
    "info_type": "Type",
    "info_ns": "Arvan name servers",
}

FA: dict[str, str] = {
    "rate_limited": "لطفاً کمی آهسته‌تر.",
    "session_expired": "نشست منقضی شده. برای شروع دوباره /start را بفرستید.",
    "flow_expired": "این عملیات منقضی شده. از منو دوباره شروع کنید.",
    "read_only": "ربات در حالت فقط‌خواندنی است و این عملیات غیرفعال است.",
    "domain_not_allowed": "این دامنه برای ربات مجاز نیست.",
    "unexpected_error": "خطای غیرمنتظره. لاگ ربات را بررسی کنید.",
    "api_error": "خطای API آروان: {detail}",
    "invalid_input": "ورودی نامعتبر: {detail}\nدوباره بفرستید یا /cancel.",
    "text_hint": "برای باز کردن منو /start را بفرستید.",
    "help": ("<b>ربات CDN آروان</b>\n/start  انتخاب دامنه\n/cancel  لغو عملیات جاری\n/help  نمایش این راهنما"),
    "home": "<b>ArvanCloud CDN</b>\nیک دامنه انتخاب کنید:",
    "home_empty": "با این کلید API دامنه‌ای پیدا نشد.",
    "menu": "دامنه: <b>{domain}</b>\nچه کاری انجام بدهم؟",
    "btn_records": "رکوردهای DNS",
    "btn_add": "افزودن رکورد",
    "btn_purge_all": "پاک‌کردن کل کش",
    "btn_purge_urls": "پاک‌کردن کش URL",
    "btn_info": "اطلاعات دامنه",
    "btn_back": "بازگشت",
    "btn_domains": "لیست دامنه‌ها",
    "btn_cancel": "انصراف",
    "btn_yes_delete": "بله، حذف شود",
    "btn_yes_purge": "بله، پاک شود",
    "btn_create": "ساخت رکورد",
    "btn_cloud_on": "روشن‌کردن کلود",
    "btn_cloud_off": "خاموش‌کردن کلود",
    "btn_delete": "حذف",
    "btn_cloud_yes": "پشت CDN (کلود)",
    "btn_cloud_no": "فقط DNS",
    "records": "رکوردهای DNS دامنه <b>{domain}</b> ({count})\n🟠 پشت CDN آروان، ⚪ فقط DNS",
    "record": (
        "<b>{name}</b>.{domain}\nنوع: <code>{type}</code>\nمقدار: <code>{value}</code>\n"
        "TTL: <code>{ttl}</code>\nکلود: {cloud}\nشناسه: <code>{id}</code>"
    ),
    "cloud_on": "روشن",
    "cloud_off": "خاموش",
    "delete_confirm": "رکورد <b>{desc}</b> حذف شود؟ این کار قابل بازگشت نیست.",
    "deleted": "رکورد حذف شد.",
    "add_type": "نوع رکورد را انتخاب کنید:",
    "add_name": "نام رکورد را بفرستید (برای ریشه دامنه <code>@</code>):",
    "add_value_a": "یک آدرس IPv4 بفرستید، مثلاً <code>203.0.113.10</code>",
    "add_value_aaaa": "یک آدرس IPv6 بفرستید، مثلاً <code>2001:db8::1</code>",
    "add_value_cname": "هاست مقصد را بفرستید، مثلاً <code>target.example.com</code>",
    "add_value_aname": "هاست مقصد را بفرستید، مثلاً <code>target.example.com</code>",
    "add_value_txt": "متن رکورد را بفرستید.",
    "add_value_mx": "اولویت و هاست را بفرستید، مثلاً <code>10 mail.example.com</code>",
    "add_value_ns": "هاست نیم‌سرور را بفرستید، مثلاً <code>ns1.example.com</code>",
    "add_ttl": "TTL را انتخاب کنید:",
    "add_cloud": "این رکورد از CDN آروان عبور کند؟",
    "add_confirm": (
        "این رکورد ساخته شود؟\n<b>{name}</b>.{domain}  <code>{type}</code>\n"
        "مقدار: <code>{value}</code>\nTTL: <code>{ttl}</code>\nکلود: {cloud}"
    ),
    "created": "رکورد ساخته شد.",
    "cancelled": "لغو شد.",
    "purge_all_confirm": ("کل کش <b>{domain}</b> پاک شود؟ تا پر شدن دوباره‌ی کش ممکن است فشار روی سرور اصلی زیاد شود."),
    "purge_ok": "درخواست پاک‌سازی ثبت شد.",
    "purge_urls_prompt": (
        "URLهایی که باید پاک شوند را بفرستید (هر خط یکی). فقط URLهای <b>{domain}</b> و "
        "زیردامنه‌هایش پذیرفته می‌شود (حداکثر {max})."
    ),
    "purge_urls_ok": "درخواست پاک‌سازی برای {count} URL ثبت شد.",
    "info_line": "• {label}: <code>{value}</code>",
    "info_status": "وضعیت",
    "info_plan": "پلن",
    "info_type": "نوع",
    "info_ns": "نیم‌سرورهای آروان",
}

CATALOGS = {"en": EN, "fa": FA}


class Translator:
    def __init__(self, language: str) -> None:
        self._catalog = CATALOGS[language]

    def __call__(self, key: str, **values: object) -> str:
        template = self._catalog.get(key) or EN[key]
        return template.format(**{k: html.escape(str(v)) for k, v in values.items()})
