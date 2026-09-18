from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PATH = str(BASE_DIR / "content")
THEME = str(BASE_DIR / "theme")
AUTHOR = "Reading notes"
SITENAME = "故事收藏室"
SITEURL = ""
DEFAULT_LANG = "zh-TW"
TIMEZONE = "Asia/Taipei"
PLUGINS = ["pelican.plugins.tabular"]
PAGE_PATHS = ["pages"]
ARTICLE_PATHS = ["posts"]
STATIC_PATHS = []
DIRECT_TEMPLATES = []
PAGE_URL = "{slug}.html"
PAGE_SAVE_AS = "{slug}.html"
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None

TABULAR_VIEWS = {
    "works": {
        "messages": {
            "search": "搜尋作品",
            "empty": "沒有符合條件的作品。",
            "legend": "評分說明",
        },
        "fields": ["title", "format", "genres", "creator", "rating"],
        "field_labels": {
            "title": "名稱",
            "format": "形式",
            "genres": "類型",
            "creator": "創作者",
            "rating": "評分",
            "publisher": "出版／製作",  # noqa: RUF001 - Traditional Chinese punctuation
            "status": "進度",
            "released_at": "發行年份",
            "completed_at": "閱畢年份",
            "note": "簡評",
        },
        "field_types": {
            "rating": "number",
            "released_at": "date",
            "completed_at": "date",
        },
        "search_fields": ["title", "creator", "publisher", "format", "note"],
        "sort_fields": ["title", "rating", "released_at", "completed_at"],
        "sort_by": "released_at",
        "sort_order": "desc",
        "display": {
            "layout": "responsive",
            "title_field": "title",
            "meta_fields": ["format", "genres", "creator", "rating"],
            "detail_fields": [
                "status",
                "publisher",
                "released_at",
                "completed_at",
                "note",
            ],
            "legend_fields": ["rating"],
        },
        "filters": {
            "format": {
                "options": [
                    {"value": "anime", "label": "動畫", "tone": "violet"},
                    {"value": "novel", "label": "小說", "tone": "green"},
                    {"value": "film", "label": "電影", "tone": "rose"},
                    {"value": "manga", "label": "漫畫", "tone": "amber"},
                ]
            },
            "status": {
                "options": [
                    {"value": "ongoing", "label": "正在看", "tone": "amber"},
                    {"value": "completed", "label": "已看完", "tone": "green"},
                    {"value": "planned", "label": "想看", "tone": "blue"},
                    {"value": "on_hold", "label": "暫停"},
                    {"value": "dropped", "label": "棄坑"},
                ]
            },
            "rating": {
                "options": [
                    {
                        "value": 5,
                        "label": "★★★★★",
                        "description": "值得一看再看",
                        "tone": "amber",
                    },
                    {
                        "value": 4,
                        "label": "★★★★",
                        "description": "喜歡，推薦",  # noqa: RUF001 - Traditional Chinese punctuation
                        "tone": "blue",
                    },
                    {"value": 3, "label": "★★★", "description": "有喜歡的部分"},
                    {"value": None, "label": "—", "description": "尚未評分"},
                ]
            },
            "genres": {"match": "all"},
            "released_at": {"control": "year_range"},
            "completed_at": {"control": "year_range"},
        },
        "presets": [
            {"label": "正在看", "filters": {"status": ["ongoing"]}},
            {"label": "想看", "filters": {"status": ["planned"]}},
        ],
        "query_sync": True,
        "updated_at": "2026-09-18",
    }
}
