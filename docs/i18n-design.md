# tabular／OSM i18n 設計草案

狀態：提案，尚未實作。盤點基準為已發佈的 tabular 0.8.0 與 OSM 0.16.1。

目標是讓同一份資料與設定能服務不同語言的頁面，同時保留單語使用方式。
每個欄位預設只顯示目前語言的內容；原文別名可以另列為搜尋來源，不自動增加雙語副標題。

## 現有入口與缺口

依使用者入口往內追查，這次需要涵蓋下列路徑，不能只改 database view。

| 入口 | 目前的語言來源／處理 | 需要改善的地方 |
| --- | --- | --- |
| tabular 一般表格 | `_resolve_settings()` 以 `DEFAULT_LANG` 選計數文字；欄位標籤為字串 | `_process_article()` 沒有將個別文章的 `Lang` 傳入；與 view 應共用語言處理 |
| tabular named view | `views.py` 的 Python 字典提供英／繁中／日文，再把訊息放入 JSON | 語言只取第一段，`zh-Hans` 也會套繁中；缺少統一的格式驗證與複數處理 |
| OSM 地點表格 | Python 讀文章 `Lang`，支援 `x-osm-list-i18n.title` | 規則與 tabular 分開；欄位標籤支援翻譯不代表地點資料也支援 |
| OSM 地圖、popup 與圖層 | schema 標籤在 Python 決定；部分 JS 訊息讀 `<html lang>`，caption 的 `and N more` 仍為固定英文 | 同一元件可能混用兩種語言；圖層選單仍寫死「作品：」「全部」「清除篩選」 |
| OSM 照片燈箱與控制項 | JS 直接建立控制項 | `Close`、`Previous`、`Next`、照片替代文字等未完整經過翻譯層 |
| 排序、搜尋與日期 | 共用 JS 的 `localeCompare()` 未指定語言；Python 使用字串排序與 `strftime()` | 互動排序依瀏覽器環境；初始輸出、搜尋正規化和顯示格式需要分別訂契約 |
| 子站與全站搜尋 | Pelican i18n_subsites、blog 的 `.ja-data` 產生器、Pagefind | 需同時驗證 HTML、GeoJSON、URL、引用資料與搜尋索引，不只是畫面上的字 |

相關實作位置：tabular 的 `tabular.py`、`views.py`、`core.py`、`rendering.py`、
`static/js/tabular-core.js` 與 `tabular-views.js`；OSM 的 `osm.py` 與 `static/js/osm-map.js`。
entertainment-blog 目前在 `build_story_database.py` 選翻譯，再由 `build_ja_data.py` 複製／改寫資料。
OSM 文件舊列的 `osmLink`、`googleLink`、`urlLinkLabel` 並未用於目前輸出，
不能將它們當成已有效的翻譯介面；遷移時需區分有效 override 與歷史殘留設定。

## 1. 先建立共用的語言脈絡

建議在 tabular 提供小型公開 i18n 模組，由既有相依它的 OSM 使用。
共用語言正規化、翻譯選擇、訊息格式驗證與 LocalizedText 型別；各套件仍維護自己的訊息目錄。
目前沒有必要再拆第三個套件，也不需要讓 tabular 依賴 OSM。

每個元件在產站時決定語言，優先序為：

1. 呼叫端／shortcode／view 明確指定的語言。
2. 文章或頁面的 `Lang`。
3. 該次產站有效的 `DEFAULT_LANG`。
4. `en`。

這個選擇保留目前 OSM 以文章語言為主的行為。若未翻譯文章出現在其他語言子站，
預設元件跟文章語言走；站方可明確指定要跟子站語言走。
Pelican 的文章翻譯與多語子站是不同機制，子站還會改寫 `DEFAULT_LANG`，因此不能只讀一次全域設定。
參考 [Pelican 文章翻譯](https://docs.getpelican.com/en/latest/content.html#translations)
及 [i18n_subsites](https://github.com/pelican-plugins/i18n-subsites)。

將所選語言和已解析的訊息放入元件資料，HTML 設定正確的 `lang`，需要時處理 `dir`。
JS 以元件資料為準；只有處理舊 markup 時才退回 `<html lang>`。
不要依讀者瀏覽器偏好，讓同一個網址突然換成另一種語言。
同一頁兩張不同語言的表／地圖，以及共用的照片燈箱，都要使用觸發元件的語言。

### 語言比對與缺漏翻譯

- 內部採標準語言標籤；既有 `zh-tw` 大小寫及設定中的 `zh_TW` 輸入可在邊界正規化。
- 保留地區與字形資訊。`zh-TW`／`zh-Hant` 與 `zh-CN`／`zh-Hans` 不應全部裁成 `zh`。
- 完整匹配優先，再選相容的字形／基礎語言資源。UI 最後退回英文。
- 資料內容的缺譯，退回資料原本的來源文字；不要把 UI 的英文 fallback 當成資料語言。
- 歷史上 `zh` 代表繁中的行為需列為相容政策，與標準的 likely-subtag 推論分開。
  可先保留裸 `zh` 的舊行為，但明確的 `zh-Hans` 不再透過它誤用繁中；這項改變應列入版本說明。
- 回退到其他語言的資料值，保留實際來源語言，供輸出 `lang` 與無障礙用途使用。

這裡要區分語言比對、likely subtags 和翻譯資源繼承；它們不是同一件事。
例如 Unicode 提供 `zh-TW` 對應繁中字形的資訊，但不能把所有中文都視為繁中。
參考 [Unicode LDML](https://www.unicode.org/reports/tr35/#Likely_Subtags)。

## 2. 將介面訊息集中維護

tabular 與 OSM 各維護自己的 catalog，以共用 helper 解析；Python 與 JS 不再各寫一份翻譯。
產站時只帶入元件需要的語言／訊息。catalog 格式優先考慮有型別驗證的 JSON，
保留未來由 gettext 等翻譯工具匯入的空間，不先打造大型翻譯工具鏈。

範圍包含可見文字、空結果、載入失敗、計數、範圍錯誤、按鈕提示、ARIA label、照片替代文字、
全螢幕／重設／燈箱控制與地圖 caption。開發者的建置診斷可繼續用英文，與讀者介面分開。
OSM 圖層欄位名稱應從設定／schema 取得；通用預設用「圖層」，不能寫死「作品」。

計數採完整句子的範本，避免把數字、名詞與標點硬接起來。複數形式使用 CLDR 的分類，
Python 可用 Babel，前端可用 `Intl.PluralRules`；對兩端共同支援的語言建立相同測例，
不要自行假設所有語言只有單數／複數。Babel 也能產生不依賴外部 JS 函式庫的複數規則，
若需要完全一致的規則版本，可以在打包時產生靜態 helper，避免執行期 `eval`。
參考 [Babel plural API](https://babel.pocoo.org/en/latest/api/plural.html)。

現有 `messages`、計數 template 和 `window.OSM_I18N` 都應保留 adapter；
空字串用來隱藏計數的語意仍要保留。若使用者提供的範本缺少必要 placeholder、型別錯誤或語言標籤無效，
在建置時指出設定路徑。正常的缺譯可以回退，套件內建 catalog 的漏鍵則由測試攔下。

## 3. 欄位標籤與選項文字先支援 LocalizedText

建議對明確的「顯示文字」設定支援 `str | dict[locale, str]`，保留原本字串寫法。
以下是提案語法，0.8.0 尚不支援：

```python
TABULAR_VIEWS = {
    "works": {
        "fields": ["title", "category"],
        "field_labels": {
            "title": {"zh-TW": "作品名稱", "ja": "作品名"},
            "category": {"zh-TW": "分類", "ja": "分類"},
        },
        "filters": {
            "category": {
                "options": [
                    {
                        "value": "anime",
                        "label": {"zh-TW": "動畫", "ja": "アニメ"},
                    }
                ]
            }
        },
    }
}
```

同樣適用於選項 description、preset label 等欄位；訊息的複數結構要使用有明確型別的節點，
不要與語言 map 混淆。翻譯只改 label，`anime` 等選項值、資料 ID、URL 查詢值保持不變。
不同語言的群組與篩選也應以同一個穩定值識別。

OSM 現有的 `x-osm-list-i18n.title` 接到同一個 resolver，保留舊語法與既有優先序：
schema 的語言標籤 → schema `title` → `OSM_LIST_FIELD_LABELS` → 欄位 key。
popup 與 table 最終應讀到同一份解析結果；舊 JS override 的相容優先序需用測試固定。

## 4. 資料翻譯另作可選層

資料翻譯不應要求所有使用者重寫 YAML，也不能把任意 dict 都猜成翻譯。
建議新增明確啟用的 record translation 區塊，並宣告哪些欄位可翻譯；舊 scalar、
link dict、list 與地點 ref 的意義不變。示意格式：

```yaml
- id: a-silent-voice-film
  title: 聲之形
  title_native: 聲の形
  category: anime
  translations:
    ja:
      title: 聲の形
```

設定需明確指定 translation 欄位與可翻譯欄位，例如 `title`／`note`／`name`。
`translations` 僅在啟用這項功能時解讀；若原資料已有同名欄位，應能另選名稱。
這是顯示投影，不覆寫快取中的原資料，也不允許翻譯區塊修改 ID、座標或原始數值。
對 enum 等可篩選欄位，優先翻譯 option label，避免把 canonical value 改成另一種文字。

對現有 `title_native`／`name_ja` 等欄位提供明確的欄位映射遷移方式。
不要把「原名」一律推定成日文；語言應由作者指定，作品或地點也可能有其他原文語言。
每格仍只顯示一種語言；別名搜尋採明確列出的欄位，不自動將所有翻譯或隱藏欄位公開。

引用先以 ID 解析，再套翻譯。OSM 的 fragment、marker、照片索引和表格回鏈都維持相同 ID，
舊的名稱式 fragment 保留來源名稱 alias，不能因顯示譯名而失效。
GeoJSON 若包含翻譯後的文字，輸出路徑與快取必須區分語言，避免子站覆蓋主站。

## 5. 格式、排序、搜尋與子站一致性

- 語言／訊息／URL 等解析結果屬於單一元件／產站脈絡，不放在會被下一個子站改寫的全域物件。
  原始檔可共用唯讀快取，翻譯投影依 locale、資料根目錄及需要的 URL 脈絡區分。
- 日期與數值維持原型別，顯示格式另處理。原有明確指定的 `date_format` 繼續優先，
  不使用 process-wide 的 `locale.setlocale()` 切換整個產站程式。
- 前端文字排序明確傳入元件 locale 的 `Intl.Collator`；數字、日期與 Tier 排名仍按原型別／sort key。
  初始 Python 字串排序不等於語言定序，不能宣稱與瀏覽器完全一致。
  第一期保留既有初始排序；若需要無 JS 也有完全一致的語言排序，第二期須決定共用 collation backend
  或建置時提供明確的 sort key，另列相容性與相依成本。
- 搜尋對資料與輸入使用一致的 Unicode 正規化／大小寫策略。是否忽略全半形須明訂，
  不擅自做簡繁轉換、翻譯或羅馬字轉寫；可用別名提供作者想支援的搜尋方式。
- Pagefind 讀到的是產生後的 HTML；可見名稱需在 HTML 就是正確語言，不能只在 JS 啟動後換字。
  資料庫的別名搜尋與全站 Pagefind 是不同入口，各自驗證、各自決定是否索引別名。

瀏覽器的語言排序、數字與日期格式工具見 [ECMA-402](https://tc39.es/ecma402/)。

## 建議實作順序

1. **語言脈絡與完整介面翻譯**：共用 resolver、component locale、catalog、OSM 遺漏文字、
   placeholder／複數驗證與舊設定 adapter。先讓現有單語資料在各種頁面都使用正確介面語言。
2. **標籤與資料翻譯**：LocalizedText、可選的 record translation、ref／GeoJSON 語言投影，
   再將 entertainment-blog 的語言分支和 `.ja-data` 中可被取代的部分逐步移除。
   顯示格式與需要完全一致的文字定序在此階段另作明確決定。
3. **消費端遷移與回歸**：兩個 blog、三種語言、舊表格和新 view、地圖與燈箱一起驗證，
   不要求所有頁面改用新 view。屆時若 OSM 使用新增的共用 API，先發佈 tabular，再提高 OSM 的最低相依並發佈。

必要驗收包含：文章 `Lang` 不同於 `DEFAULT_LANG`；同頁不同語言元件；
zh-TW／zh-Hant／zh-Hans／ja-JP／未知語言；缺譯與空字串；0／1／2／多筆計數；
舊 override 優先序；翻譯中的 HTML 特殊字元；無 JS 與 JS 啟動後文字一致；
中日頁的同一筆資料 ID／URL filter value 不變；子站反覆產生不污染快取；
OSM 圖層選單超過 10 層時也走翻譯；popup、照片燈箱及 Pagefind 都讀到正確語言。
