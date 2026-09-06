from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from services.store import companies


class GraphData:
    @staticmethod
    def distribution(field, label):
        rows = companies()
        yes = sum(bool(c.get(field)) for c in rows)
        return {"labels": [label+"あり", label+"なし"], "data": [yes, len(rows)-yes]}

    @staticmethod
    def email_distribution():
        return GraphData.distribution("email", "Email")

    @staticmethod
    def inquiry_distribution():
        return GraphData.distribution("inquiry_url", "問い合わせURL")

    @staticmethod
    def phone_distribution():
        return GraphData.distribution("phone", "電話")

    @staticmethod
    def daily_scrape_counts():
        def local_day(value):
            try:
                date = datetime.fromisoformat(value.replace("/", "-"))
                if date.tzinfo:
                    date = date.astimezone(ZoneInfo("Asia/Tokyo"))
                return date.strftime("%Y-%m-%d")
            except ValueError:
                return value[:10]
        counts = Counter(local_day(c.get("created_at", "")) for c in companies())
        return {"labels": sorted(counts), "data": [counts[k] for k in sorted(counts)]}
