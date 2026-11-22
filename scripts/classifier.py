#!/usr/bin/env python3
"""Deterministic keyword classifier for Ovasta complaint texts (tickets and low-rating comments).

Used by build_data.py for tickets / ratings that have no manual label in complaints_classified.json.
Same text in -> same label out. No network, no model.

Categories (same as the manual labels): delay, courier, quality, missing_wrong, pricing, app, other.
Rules
  * text is normalised (Arabic letter variants, tashkeel/tatweel removed, repeated letters collapsed,
    Arabic-Indic digits -> Latin, lower case)
  * each category has weighted keyword stems; the score is the sum of the weights of the stems found
  * the highest score wins; a tie between two categories is resolved only by the fixed pairs in
    TIE_BREAK (e.g. a late order that also mentions the courier counts as delay, like the manual labels);
    any other tie, or no keyword at all, goes to "other" (tag "unclear")
  * empty / test / punctuation-only text -> other with tag "empty" (excluded from type shares)
"""
import re

CATS = ["delay", "courier", "quality", "missing_wrong", "pricing", "app", "other"]

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_TASHKEEL = re.compile(r"[\u064B-\u065F\u0670\u0640]")

def normalize(text):
    s = (text or "").lower().translate(_AR_DIGITS)
    s = _TASHKEEL.sub("", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"), ("ة", "ه"), ("ى", "ي"), ("ئ", "ي"), ("ؤ", "و"),
                 ("ڤ", "ف"), ("گ", "ك"), ("’", ""), ("‎", ""), ("‏", "")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1{2,}", r"\1", s)          # اوووي -> اوي, جداااا -> جدا
    s = re.sub(r"\s+", " ", s).strip()
    return s

# (stem, weight). Stems are matched as substrings of the normalised text.
KW = {
    "delay": [("اتاخر", 3), ("اتخر", 2), ("تاخير", 3), ("تاخر", 3), ("متاخر", 3), ("بيتاخر", 3), ("هيتاخر", 3), ("بتتاخر", 3),
              ("ساعه ونص", 3), ("ساعتين", 3), ("ساعتان", 3), ("بقالي ساعه", 3), ("بقاله ساعه", 3), ("من ساعه", 2),
              ("ساعه الا", 2), ("نص ساعه", 2), ("موصلش", 3), ("ما وصلش", 3), ("ماوصلش", 3), ("موصلتش", 3),
              ("لم يصل", 3), ("لم يصلني", 3), ("لسه موصل", 3), ("لسه ما وصل", 3), ("لسه مجاش", 3), ("مجاش لحد", 3),
              ("لحد دلوقتي", 2), ("لحد الان", 2), ("هيطول", 3), ("بيطول", 3), ("يطول", 2), ("وقت طويل", 3),
              ("فاضل قد اي", 2), ("فاضل اد اي", 2), ("بطيء", 2), ("بطء", 2), ("late", 3), ("delay", 3), ("slow", 2),
              ("مستني الاوردر", 2), ("استني", 1), ("منتظر", 1), ("قدامه", 3), ("فين طلبي", 3), ("فين الاوردر", 3),
              ("اسرع", 3), ("وقت كبير", 3), ("اخد وقت", 3), ("فوق ساعه", 3), ("اكتر من ساعه", 3), ("سريع", 2), ("طول جدا", 3)],
    "courier": [("اسلوب", 3), ("المعامله", 2), ("معامله المندوب", 3), ("قليل الادب", 3), ("مش محترم", 3), ("وقح", 3),
                ("صوته عالي", 3), ("صوتة عالي", 3), ("متبعتوليش", 3), ("محدش يبعت", 3), ("يبعتوا تاني", 2),
                ("ما يجيش تاني", 3), ("رفض التسليم", 3), ("رفض يطلع", 3), ("مش راضي يطلع", 3), ("بيبحلق", 3),
                ("السواق", 2), ("المندوب", 1), ("مندوب", 1), ("الطيار", 1), ("الدليفري", 1), ("الدليفرى", 1),
                ("دلفيري", 1), ("عامل التوصيل", 1), ("تليفونه مقفول", 2), ("تلفونه مقفول", 2), ("رقم المندوب", 1),
                ("مش بيرد", 1), ("مبيردش", 1), ("rude", 3), ("driver", 1), ("courier", 1)],
    "quality": [("بايظ", 3), ("بايز", 3), ("فاسد", 3), ("معفن", 3), ("دود", 2), ("منتهي الصلاحيه", 3), ("صلاحيه", 2),
                ("بارد", 3), ("سخن", 2), ("محروق", 3), ("مش مستوي", 3), ("ناشف", 3), ("مش مقرمش", 2), ("طعمه", 2), ("دبلان", 3), ("الاكل سي", 3), ("مش كويس", 1),
                ("ريحه", 2), ("ريحتها", 2), ("بايت", 2), ("مكسور", 3), ("اتكسر", 3), ("ضارب", 3), ("مش طازه", 3),
                ("مش حلو", 2), ("مش مظبوط", 2), ("وحشه", 1), ("تعبان", 2), ("الجوده", 2), ("جوده", 2), ("شعر", 2),
                ("صغير جدا", 2), ("مهري", 3), ("quality", 3), ("spoiled", 3), ("cold", 2), ("expired", 3)],
    "missing_wrong": [("ناقص", 3), ("نقص", 2), ("ناقصه", 3), ("مش كامل", 3), ("غير كامل", 3), ("غلط", 3), ("خطا", 1),
                      ("لخبطه", 3), ("غير المطلوب", 3), ("غير اللي", 3), ("حاجه تاني", 2), ("بدل", 2), ("يبدل", 2),
                      ("جالي واحد", 3), ("جابلي", 1), ("جايبلي", 1), ("جالي", 1), ("مجاليش", 3), ("مجابش", 3),
                      ("نسيتو", 3), ("نسي", 2), ("الكميات", 2), ("اتكررت", 2), ("مش موجود في الاوردر", 3),
                      ("بيلغو اصناف", 3), ("wrong", 3), ("missing", 3),
                      ("مجاش", 2), ("ماجاش", 2), ("مجتش", 3), ("مجوش", 3), ("متجيش", 3), ("مجبليش", 3), ("بتنسوا", 3),
                      ("بتتغير", 2), ("بيغيرو", 3), ("عكس", 2), ("وجت ", 2), ("جاب من", 2), ("اقل من", 2), ("الحجم", 1),
                      ("كنت طالب", 2), ("ما بتوصلش", 2)],
    "pricing": [("سعر", 2), ("اسعار", 3), ("السعر", 2), ("غالي", 3), ("اغلي", 3), ("فلوس", 2), ("فلوسه", 2),
                ("الحساب", 1), ("محسوب", 2), ("حسبتوه", 3), ("حاسب", 1), ("فاتوره", 3), ("مبلغ", 2), ("خصم", 2),
                ("الباقي", 2), ("فكه", 2), ("محفظه", 3), ("المحفظه", 3), ("فودافون كاش", 3), ("انستا", 3),
                ("اينستا", 3), ("فيزا", 3), ("visa", 3), ("apple pay", 3), ("ابل باي", 3), ("الدفع", 3), ("ادفع", 3),
                ("ايداع", 3), ("رسوم", 3), ("سعر التوصيل", 4), ("التوصيل غالي", 4), ("مصاريف", 3), ("جنيه", 1),
                ("price", 3), ("expensive", 3), ("pay", 2), ("cash", 2), ("اجمالي", 3), ("دفعت", 2), ("دفعه", 2),
                ("باقي", 2), ("رصيد", 2), ("اخد مني", 3)],
    "app": [("الابلكيشن", 1), ("ابلكيشن", 1), ("الابليكشن", 1), ("الابلكشن", 1), ("التطبيق", 1), ("البرنامج", 1),
            ("الحساب بتاعي", 3), ("الاكونت", 3), ("اكونت", 3), ("اسجل", 3), ("تسجيل الدخول", 3), ("افعل", 3), ("تفعيل", 3),
            ("الغاء الحساب", 4), ("رقم التليفون", 2), ("اغير رقم", 3), ("كود", 2), ("otp", 3), ("login", 3),
            ("العنوان", 3), ("عنواني", 3), ("اللوكيشن", 3), ("لوكيشن", 3), ("الموقع", 2), ("نقلت", 2),
            ("في توصيل ل", 3), ("بتوصلو", 2), ("الخدمه واقفه", 3), ("واقفه ليه", 3), ("مفيش استلام", 3), ("مقفول", 1),
            ("الغي الاوردر", 4), ("الغاء الطلب", 4), ("الغاء الاوردر", 4), ("الغي الطلب", 4), ("اكنسل", 4), ("كنسل", 2),
            ("cancel", 3), ("اذود", 3), ("ازود", 2), ("اضيف", 2), ("ادمج", 3), ("تعديل الطلب", 3), ("اعدل", 3),
            ("مش عايز يطلب", 3), ("مش راضي يكمل", 3), ("يقفل", 2), ("بيقفل", 2), ("مش شغال", 2), ("الدعم", 2),
            ("app", 2), ("account", 3), ("address", 3), ("مش عارف اطلب", 3), ("فيه توصيل", 3), ("في توصيل", 3),
            ("التوصيل متاح", 3), ("توصيل خارج", 3), ("بنوصلش", 3), ("الغي", 3), ("يتلغي", 3), ("اتلغي", 2), ("مش عاوز يجمع", 3),
            ("الاسم", 2), ("اظيف", 3), ("رقم تليفوني", 3), ("معلق", 2)],
    "other": [("يتواصل", 2), ("اتواصل", 2), ("خدمه العملاء", 1), ("منتجاتي", 4), ("كرهتوني", 2)],
}
# Tie-break pairs that the manual labels resolve the same way every time (winner first).
TIE_BREAK = {frozenset(("delay", "courier")): "delay", frozenset(("delay", "missing_wrong")): "delay",
             frozenset(("missing_wrong", "pricing")): "missing_wrong", frozenset(("quality", "missing_wrong")): "missing_wrong",
             frozenset(("delay", "quality")): "delay", frozenset(("pricing", "courier")): "pricing",
             frozenset(("app", "delay")): "delay"}

OTHER_HINTS = [("contact", ("يتواصل", "اتواصل", "تواصل", "كلموني", "كلمني", "محتاج استفسر", "استفسار", "خدمه العملاء")),
               ("job", ("شغل", "اقدم", "وظيفه", "مركبتي", "موتسيكل")),
               ("praise", ("شكرا", "ممتاز", "جميل", "تحفه", "برافو", "احسن")),
               ("neg", ("سيء", "سيي", "زفت", "زافت", "وحش", "اسوا", "صفر", "حرام"))]
_EMPTY = re.compile(r"^[\W\d_]*$")
_PRICE_NUM = re.compile(r"(?:^|\s)ب ?\d+|\d+ ?(?:جنيه|ج\b)")

def classify(text):
    """Return (primary, tag, scores). tag is 'empty' for blank/test text, 'unclear' for no or ambiguous match."""
    s = normalize(text).replace("[رقم]", " ").replace("[email]", " ").strip()
    if not s or _EMPTY.match(s) or s in ("test", "testing", "تجربه", "تست", "تم", "ok", "اوك"):
        return "other", "empty", {}
    padded = " " + s + " "
    scores = {c: sum(w for k, w in kws if k in padded) for c, kws in KW.items()}
    scores["pricing"] += 2 * len(_PRICE_NUM.findall(s))
    scores = {c: v for c, v in scores.items() if v > 0}
    if not scores or (scores.get("other") and len(scores) == 1):
        for tag, keys in OTHER_HINTS:
            if any(k in s for k in keys): return "other", tag, {}
        return "other", "unclear", {}
    best = max(scores.values())
    top = sorted(c for c, v in scores.items() if v == best)
    if len(top) == 1:
        if top[0] == "other":
            for tag, keys in OTHER_HINTS:
                if any(k in s for k in keys): return "other", tag, scores
            return "other", "unclear", scores
        return top[0], None, scores
    if len(top) == 2 and frozenset(top) in TIE_BREAK:
        return TIE_BREAK[frozenset(top)], None, scores
    return "other", "unclear", scores

if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        print(classify(line.strip())[:2], line.strip()[:80])
