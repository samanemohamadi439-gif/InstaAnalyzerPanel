
import re
import time
from io import BytesIO
from datetime import datetime
from html.parser import HTMLParser
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="تحلیل پیج‌های اینستاگرام",
    page_icon="📊",
    layout="wide"
)

st.title("📊 تحلیل پیج‌های عمومی اینستاگرام")
st.caption(
    "دریافت اطلاعات عمومی پروفایل و خروجی اکسل؛ "
    "بدون ورود به حساب کاربری"
)


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return

        item = dict(attrs)
        key = item.get("property") or item.get("name")
        value = item.get("content")

        if key and value:
            self.meta[key.lower()] = value


def normalize_username(value):
    value = str(value).strip()

    if "instagram.com/" in value.lower():
        value = re.split(
            r"instagram\.com/",
            value,
            flags=re.I
        )[-1].split("?")[0].strip("/")

    value = value.lstrip("@").strip()

    if re.fullmatch(r"[A-Za-z0-9._]{1,30}", value):
        return value

    return None


def parse_number(value):
    value = value.strip().replace(",", "")
    match = re.fullmatch(
        r"([\d.]+)\s*([KMB]?)",
        value,
        flags=re.I
    )

    if not match:
        return None

    number = float(match.group(1))
    suffix = match.group(2).upper()

    multiplier = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
    }[suffix]

    return int(number * multiplier)


def guess_category(text):
    text = text.lower()

    categories = {
        "فروشگاه": [
            "shop", "store", "boutique", "فروشگاه", "خرید"
        ],
        "زیبایی و آرایش": [
            "beauty", "makeup", "cosmetic", "آرایش", "زیبایی"
        ],
        "ورزش و تناسب اندام": [
            "fitness", "gym", "sport", "workout", "ورزش"
        ],
        "غذا و رستوران": [
            "food", "cafe", "restaurant", "pizza", "رستوران", "غذا"
        ],
        "سفر و گردشگری": [
            "travel", "tour", "hotel", "trip", "سفر", "گردشگری"
        ],
        "آموزش": [
            "academy", "education", "learn", "آموزش", "دانشگاه"
        ],
        "رسانه و سرگرمی": [
            "media", "news", "official", "entertainment", "خبر"
        ],
    }

    for category, keywords in categories.items():
        if any(word in text for word in keywords):
            return category

    return "نامشخص"


def analyze_profile(username):
    url = f"https://www.instagram.com/{username}/"

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    with urlopen(request, timeout=25) as response:
        html = response.read().decode(
            "utf-8", errors="ignore"
        )

    parser = MetaParser()
    parser.feed(html)
    meta = parser.meta

    title = meta.get("og:title", "")
    description = meta.get("og:description", "")
    image = meta.get("og:image", "")

    # مثال: 49K Followers, 989 Following, 2,508 Posts
    pattern = (
        r"([\d,.]+[KMB]?)\s+Followers.*?"
        r"([\d,.]+[KMB]?)\s+Following.*?"
        r"([\d,.]+[KMB]?)\s+Posts"
    )

    match = re.search(
        pattern, description, flags=re.I | re.S
    )

    followers = following = posts = None

    if match:
        followers = parse_number(match.group(1))
        following = parse_number(match.group(2))
        posts = parse_number(match.group(3))

    return {
        "نام کاربری": username,
        "لینک پیج": url,
        "نام نمایشی": title,
        "فالوورها": followers,
        "فالووینگ": following,
        "تعداد پست": posts,
        "دسته‌بندی تخمینی": guess_category(
            username + " " + title + " " + description
        ),
        "لینک عکس پروفایل": image,
        "وضعیت": (
            "اطلاعات دریافت شد"
            if title or description
            else "اطلاعات ناقص"
        ),
        "زمان بررسی": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }


pasted = st.text_area(
    "نام کاربری یا لینک پیج‌ها را وارد کن؛ هر خط یک پیج",
    placeholder="@username\nhttps://www.instagram.com/username/",
    height=160,
)

uploaded = st.file_uploader(
    "یا فایل CSV دارای ستون username را بارگذاری کن",
    type=["csv"],
)

batch_size = st.selectbox(
    "تعداد پیج در هر اجرا",
    [10, 25, 50, 100],
    index=1,
)

if st.button("شروع تحلیل", type="primary"):
    usernames = []

    if pasted.strip():
        usernames.extend(pasted.splitlines())

    if uploaded is not None:
        try:
            csv_data = pd.read_csv(uploaded)

            column = (
                "username"
                if "username" in csv_data.columns
                else csv_data.columns[0]
            )

            usernames.extend(
                csv_data[column].dropna().astype(str).tolist()
            )
        except Exception as error:
            st.error(f"خواندن CSV ناموفق بود: {error}")

    cleaned = []
    for value in usernames:
        username = normalize_username(value)
        if username and username not in cleaned:
            cleaned.append(username)

    if not cleaned:
        st.warning("حداقل یک نام کاربری معتبر وارد کن.")
    else:
        cleaned = cleaned[:batch_size]
        results = []
        progress = st.progress(0)
        status = st.empty()

        for index, username in enumerate(cleaned, start=1):
            status.write(
                f"در حال بررسی {index} از {len(cleaned)}: "
                f"{username}"
            )

            try:
                results.append(analyze_profile(username))
            except Exception as error:
                results.append({
                    "نام کاربری": username,
                    "لینک پیج":
                        f"https://www.instagram.com/{username}/",
                    "وضعیت": f"خطا یا محدودیت دسترسی: {error}",
                    "زمان بررسی": datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                })

            progress.progress(index / len(cleaned))

            if index < len(cleaned):
                time.sleep(1.2)

        df = pd.DataFrame(results)

        st.subheader("نتیجه تحلیل")
        st.dataframe(df, use_container_width=True)

        excel_buffer = BytesIO()

        with pd.ExcelWriter(
            excel_buffer, engine="openpyxl"
        ) as writer:
            df.to_excel(
                writer, index=False, sheet_name="Profiles"
            )

        st.download_button(
            "📥 دانلود خروجی اکسل",
            data=excel_buffer.getvalue(),
            file_name="instagram_profiles.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

st.divider()
st.caption(
    "توجه: این ابزار از اطلاعات عمومی صفحه استفاده می‌کند. "
    "اینستاگرام ممکن است درخواست‌ها را محدود کند یا بعضی "
    "اطلاعات را ارائه ندهد. دسته‌بندی تخمینی است و ممکن "
    "است اطلاعات ناقص یا گرد شده باشند."
)