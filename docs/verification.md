# 作品資料庫驗證紀錄

## 2026-09-20：將部落格試用版介面回寫套件

基準為已發佈的 tabular 0.7.0 與 OSM 0.16.1；本次只修改 tabular 的選用檢視。
下方 2026-09-18／19 的紀錄是歷史資料，當時的發佈前提不代表目前狀態。
目前發佈及部落格升級步驟見 [發布流程](releasing.md)。

| 檢查 | 結果 |
| --- | --- |
| `uv run poe lint` | Ruff、mypy 通過 |
| `uv run poe cover` | 251 項通過，覆蓋率 90% |
| `npm test` | 4 項通過 |
| `npm run test:browser`，使用實際 OSM checkout | 34 項通過 |
| `uv build` 及解壓 wheel 後產站 | wheel、sdist 成功；確認 import 來自 wheel，公開 JS 包含 core 與 views |
| 兩站實際產站，比對既有表格 HTML | main-blog 4 頁／8 張、entertainment-blog 20 頁／32 張，正規化預覽 URL 後全部相同 |
| 作品排名資料與評論連結 | 中文、日文頁各 712 筆資料與 702 個評論連結皆與基準相同 |

瀏覽器測試新增桌面展開／手機收合、`True`／`False` 初始設定、680／681px 邊界、
手動切換後搜尋／排序／縮放保留選擇、同頁多個檢視、無篩選欄位，以及重新初始化。
使用不同欄位順序的人員資料確認手機標題先顯示、欄位名稱與值可區分、長值及連結清單不溢出；
另驗證一般文章清單、提示框維持主題樣式。Attila 的 `details[class]` 提示框規則已納入 fixture，
檢視說明在深淺色與展開／收合時都不會誤用提示框的邊框、文字色或間距。

entertainment-blog 的實際主題與內容另產至暫存目錄，只在產物移除頁面專用的篩選腳本及共用樣式覆寫。
中文、日文排名頁均驗證桌面與手機篩選預設、手動選擇保留、原文名稱搜尋、排序、鍵盤操作及停用 JavaScript。
360／390px 的全部 712 筆欄位均無橫向溢出，手機欄位標籤採 15px 粗體、全形冒號且沒有額外縮排；
1440px 維持表格。人工檢查手機截圖；main-blog 的 CV 與 coworking 頁另確認排序、群組收合、
主題載入正常，而且沒有引入選用檢視的資源。

本次未改動兩站原始檔或已安裝相依，亦未發佈套件。產站驗證省略大量圖片複製及 SEO 報表，
不涵蓋正式部署、Pagefind 重建或地圖底圖。上述結果來自本機 Python 3.14 與 Chromium，並非遠端 CI 結果。
瀏覽器 fixture 伺服器加大連線佇列，避免平行載入資源時被 stdlib 預設佇列重設連線；
若預設的 8765 已有舊預覽服務，可使用 `TABULAR_TEST_PORT=8773 npm run test:browser`。

全庫 Python formatter 與 `git diff --check` 通過。提交時一併納入 formatter 對原有
`tabular.py` 與 `test_tabular.py` 的純排版修正，沒有修改邏輯；Python 回歸測試再次通過。
未重跑完整 `poe ci`，以上個別檢查不代表該命令已通過。

## 2026-09-18／19：初版與舊入口整合（歷史紀錄）

驗證日期：2026-09-18。本機 Python 3.14、Chromium；CI 另設定 Python 3.11–3.14 與 Chromium。CI 設定已加入，本紀錄不代表遠端 CI 已執行。

| 檢查 | 結果 |
| --- | --- |
| tabular `uv run poe lint` | Ruff、mypy 通過 |
| tabular `uv run poe cover` | 155 項通過，覆蓋率 89% |
| OSM `uv run poe lint` | Ruff、mypy 通過 |
| OSM Python 回歸測試 | 352 項通過 |
| `npm test` | 4 項狀態邏輯測試通過 |
| `npm run test:browser`，使用實際 OSM checkout | 26 項通過 |
| `uv build` | wheel、sdist 建置成功，包含共用 JS／CSS |
| 從解壓後 wheel 的程式碼產站 | 確認 import 來自 wheel；頁面自動引入資源，core／views 正確組成公開 JS |
| 只啟用 OSM、同時啟用兩個 plugin | 實際 Pelican 產站通過；地圖 shortcode、GeoJSON、地點表格與共用資源正常產生 |

瀏覽器測試涵蓋複合搜尋／篩選、範圍錯誤、空結果、型別排序、URL 還原與導覽、詳情、同頁多表、群組收合與計數、OSM 標籤／地圖連結／照片燈箱、重複初始化，以及停用 JavaScript 的內容可讀性。地圖資料與 markup 經產站驗證，未另做 Leaflet 底圖的瀏覽器視覺測試。

新增的相容性測試確認：只載入舊 OSM URL 即可操作表格，而且沒有載入資料庫控制項；保留隱藏筆數的設定；共用核心不因載入順序而重複初始化。Attila fixture 使用附 MIT 授權的實際文章 CSS 規則，涵蓋主站／子站、兩站品牌色、手機／桌面、鍵盤及系統／手動深淺色；淺色群組背景、sticky 儲存格背景和排序圖示有實際 CSS 值的斷言。

兩個部落格的實際內容、設定與已安裝 Attila 也已產站：main-blog 3 個含表格頁面、6 張表格；entertainment-blog 22 個含表格頁面、50 張表格（含子站）。與已安裝 tabular 0.5.0／OSM 0.16.0 比對，正規化本機預覽 URL 後，表格 HTML 全部相同；沒有加入新檢視或其資源標籤。另用 Chromium 檢查 CV、coworking、作品排名、演唱會、舞台劇、影廳偏好與日文排名頁的既有互動及 theme CSS 載入。

實際部落格驗證只把輸出、快取與預覽 URL 指向 `/tmp`；停用 SEO 報表及大量圖片複製，未修改部落格原始內容、設定或 theme。此驗證不涵蓋完整部署、Pagefind 索引及全部圖片／地圖底圖。一般 CI 使用可重現的 fixture，不要求私有部落格 checkout。

修正有效性也以暫存產站副本驗證：移除 17 個淺色預設變數，兩個配色測試皆失敗（群組背景變成透明）；移除舊 OSM JS 內的共用核心，舊入口測試失敗（排序按鈕未初始化）。恢復產物後逐檔 SHA-256 相符，對應三項測試通過。測試期間沒有修改來源檔。

360、768、1280px 寬度各以深淺色驗證，截圖儲存在 `test-results/database-{width}-{scheme}.png`。人工檢查了手機淺色與桌面深色截圖；其他尺寸由測試檢查橫向溢出、可見結果與詳情。`test-results/` 為產物，不納入版本控制；CI 會上傳測試產物。

合成資料效能量測：

| 筆數 | HTML 大小（未壓縮） | 導覽至初始化完成 | 搜尋狀態更新 |
| --- | --- | --- | --- |
| 1,000 | 372,099 bytes | 69 ms | 1.1 ms |
| 5,000 | 1,876,099 bytes | 372 ms | 4.1 ms |

這是本機單次量測，使用簡化的三欄資料。初始化數字包含頁面導覽；搜尋數字量測同步事件處理，不含下一次畫面繪製。結果不代表所有裝置或完整作品資料的效能上限。

重現範例與瀏覽器驗證：

```sh
uv sync --group dev
npm ci
npx playwright install chromium
npm run example
uv run python scripts/build_browser_fixtures.py --osm-source ../pelican-osm
npm test
npm run test:browser
```

沒有 sibling OSM checkout 時，省略 `--osm-source` 即使用版本控制中的 OSM HTML fixture；此時照片燈箱測試會跳過。正式相依關係為 `pelican-osm → pelican-tabular`，tabular 的執行期與一般 CI 都不需要 OSM。

發布尚未進行。OSM 使用暫時的本機 uv source override；CI 已明確 checkout 兩個 repo，並以真正 OSM 資源執行上述瀏覽器測試。此 CI 需要 tabular 變更先合併；遠端執行尚未驗證。

發布前須先讓 tabular 0.6.0 可由套件索引安裝，再移除 OSM source override 並更新 lockfile。OSM 發布 workflow 新增 `uv sync --locked --no-sources --no-dev`，確認 registry 相依與 lockfile 正確後才進行建置發布。這個發布前提仍未完成，不能將目前狀態視為已可直接發布 OSM。

提交前另確認兩個 repo 都會在 `main` 更新後自動升版。tabular 開發分支因此保留 0.5.0，由合併後的 Commitizen 流程產生 0.6.0；前述共同開發的打包驗證使用暫時的 0.6.0 metadata。OSM 的暫時 sibling lock 仍記錄 0.6.0，須等 tabular 發布後換成 registry lock；目前不能將該 lock 與版本仍為 0.5.0 的 feature checkout 視為一致的相依環境。操作順序見 [發布流程](releasing.md)。

2026-09-19 提交檢查：tabular 的 lock 一致性、所有本次改動檔案的 prek hooks、155 項 Python 測試再次通過。全庫 `poe ci` 的 EOF hook 會修改既有 `tests/test_tabular/test_render_table_html_regression.html` 的末尾換行，因此未宣稱該完整命令通過；此既有 fixture 已逐位元組恢復，未納入改動。兩個 commit 的 Commitizen 檢查通過，唯讀 `cz bump --get-next --yes` 分別回報 0.6.0 與 0.16.1。
